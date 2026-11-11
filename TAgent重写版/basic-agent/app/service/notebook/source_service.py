"""来源业务：创建（文本 / 上传 / 网址）、后台处理、状态、重试、下载、删除、重新嵌入。

处理流程同原版 source 图：抽取 → 存正文 → 分块建索引（可选向量）→ 跑选中的变换生成洞察。
"""

from __future__ import annotations

import logging
import pathlib
import shutil
from dataclasses import dataclass, field
from typing import BinaryIO
from urllib.parse import urlsplit

from app.errors.notebook import ExtractionFailed, InvalidInput, NotebookError, NotFound, UnsupportedType
from app.infra.notebook.extractor import Extraction, extract_file, fetch_url, is_supported_file
from app.infra.notebook.url_guard import validate_url
from app.repository.notebook.notebooks import NotebookRepository
from app.repository.notebook.sources import PLACEHOLDER_TITLE, SORT_COLUMNS, SourceRepository
from app.service.notebook.formatting import source_list_out, source_out
from app.service.notebook.indexing import Indexer
from app.service.notebook.insight_service import InsightService, find_transformation
from app.service.notebook.jobs import JobRunner
from app.service.notebook.notebook_service import notebook_id_or_404, remove_uploaded_files
from app.util.notebook.ids import normalize
from app.util.notebook.timefmt import fmt

log = logging.getLogger(__name__)

STATUS_MESSAGES = {
    "completed": "Source processing completed successfully",
    "failed": "Source processing failed",
    "running": "Source processing in progress",
    "queued": "Source processing queued",
    "new": "Source processing queued",
}


@dataclass
class SourceInput:
    type: str
    notebook_ids: list[str] = field(default_factory=list)
    url: str | None = None
    content: str | None = None
    title: str | None = None
    file_path: str | None = None
    upload_name: str | None = None
    upload_stream: BinaryIO | None = None
    transformations: list[str] = field(default_factory=list)
    embed: bool = False
    delete_source: bool = False
    async_processing: bool = False


def source_id_or_404(raw: str) -> str:
    source_id = normalize("source", raw)
    if not source_id:
        raise NotFound("Source not found")
    return source_id


def _first_line_title(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip(" #*-\t")
        if line:
            return line[:80]
    return None


def _url_title(url: str) -> str:
    parts = urlsplit(url)
    return (parts.netloc + parts.path).rstrip("/")[:200] or url[:200]


class SourceService:
    def __init__(self, sources: SourceRepository, notebooks: NotebookRepository, indexer: Indexer,
                 insights: InsightService, jobs: JobRunner, *, upload_dir: pathlib.Path, allow_private_urls: bool):
        self.sources = sources
        self.notebooks = notebooks
        self.indexer = indexer
        self.insights = insights
        self.jobs = jobs
        self.upload_dir = upload_dir
        self.allow_private_urls = allow_private_urls

    # ---- 查询 ----
    def list(self, *, notebook_id: str | None, limit: int, offset: int, sort_by: str, sort_order: str) -> list[dict]:
        if sort_by not in SORT_COLUMNS:
            raise InvalidInput(f"sort_by 只能是 {', '.join(SORT_COLUMNS)}")
        if sort_order not in {"asc", "desc"}:
            raise InvalidInput("sort_order 只能是 asc 或 desc")
        if notebook_id:
            notebook_id = notebook_id_or_404(notebook_id)
            if not self.notebooks.get(notebook_id):
                raise NotFound("Notebook not found")
        rows = self.sources.list(
            notebook_id=notebook_id, limit=limit, offset=offset, sort_by=sort_by, descending=sort_order == "desc"
        )
        return [source_list_out(row, self.upload_dir) for row in rows]

    def _get_row(self, raw_id: str) -> dict:
        row = self.sources.get(source_id_or_404(raw_id))
        if not row:
            raise NotFound("Source not found")
        return row

    def get(self, raw_id: str) -> dict:
        row = self._get_row(raw_id)
        self.sources.mark_viewed(row["id"])
        return source_out(row, self.upload_dir)

    def status(self, raw_id: str) -> dict:
        row = self._get_row(raw_id)
        status = row.get("job_status")
        if not row.get("job_id"):
            return {"status": None, "message": "Legacy source (completed before async processing)",
                    "processing_info": None, "command_id": None}
        if not status:
            return {"status": "unknown", "message": "Source processing status unknown",
                    "processing_info": None, "command_id": row["job_id"]}
        info = {**(self._progress(row) or {})}
        return {
            "status": status,
            "message": STATUS_MESSAGES.get(status, f"Source processing status: {status}"),
            "processing_info": info,
            "command_id": row["job_id"],
        }

    def _progress(self, row: dict) -> dict | None:
        job = self.jobs.jobs.get(row["job_id"]) if row.get("job_id") else None
        if not job:
            return None
        return {
            "status": job["status"],
            "started_at": fmt(job.get("started_at")),
            "completed_at": fmt(job.get("completed_at")),
            "error": job.get("error"),
            "result": job.get("result"),
        }

    def download_path(self, raw_id: str) -> tuple[pathlib.Path, str]:
        row = self._get_row(raw_id)
        raw = row.get("asset_file_path")
        if not raw:
            raise NotFound("This source has no downloadable file")
        path = pathlib.Path(raw).resolve()
        if not path.is_relative_to(self.upload_dir.resolve()) or not path.is_file():
            raise NotFound("File not found on server")
        return path, path.name

    # ---- 创建 ----
    def _notebook_ids(self, raw_ids: list[str]) -> list[str]:
        out: list[str] = []
        for raw in raw_ids:
            notebook_id = normalize("notebook", raw)
            if not notebook_id or not self.notebooks.get(notebook_id):
                raise NotFound(f"Notebook {raw} not found")
            if notebook_id not in out:
                out.append(notebook_id)
        return out

    def save_upload(self, filename: str, stream: BinaryIO) -> pathlib.Path:
        """只取文件名本身（防路径穿越），重名加「 (n)」，用独占方式创建保证不覆盖别人的文件。"""
        name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip().replace("\x00", "")
        if not name or name in {".", ".."}:
            raise InvalidInput("文件名不对")
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        stem, suffix = pathlib.Path(name).stem or "file", pathlib.Path(name).suffix
        for counter in range(0, 1000):
            candidate = self.upload_dir / (name if counter == 0 else f"{stem} ({counter}){suffix}")
            try:
                with open(candidate, "xb") as handle:
                    shutil.copyfileobj(stream, handle, length=1024 * 1024)
                return candidate
            except FileExistsError:
                continue
        raise InvalidInput("同名文件太多，请改个名字再上传")

    def _inside_uploads(self, raw: str) -> pathlib.Path:
        path = pathlib.Path(raw).expanduser().resolve()
        if not path.is_relative_to(self.upload_dir.resolve()):
            raise InvalidInput("file_path 必须在上传目录里")
        if not path.is_file():
            raise InvalidInput("file_path 指向的文件不存在")
        return path

    def create(self, data: SourceInput) -> dict:
        notebook_ids = self._notebook_ids(data.notebook_ids)
        transformations = [find_transformation(raw)["id"] for raw in data.transformations]
        saved_upload: pathlib.Path | None = None
        plan: dict = {"kind": data.type, "embed": data.embed, "transformations": transformations}

        if data.type == "link":
            if not data.url or not data.url.strip():
                raise InvalidInput("URL is required for link type")
            plan["url"] = validate_url(data.url, allow_private=self.allow_private_urls)
        elif data.type == "upload":
            if data.upload_stream is not None:
                if not is_supported_file(data.upload_name or ""):
                    raise UnsupportedType("不支持这种文件类型（支持 txt/md/csv/json/xml/html/pdf/docx）")
                saved_upload = self.save_upload(data.upload_name or "", data.upload_stream)
                plan["file_path"] = str(saved_upload)
            elif data.file_path:
                path = self._inside_uploads(data.file_path)
                if not is_supported_file(path.name):
                    raise UnsupportedType("不支持这种文件类型（支持 txt/md/csv/json/xml/html/pdf/docx）")
                plan["file_path"] = str(path)
            else:
                raise InvalidInput("File upload or file_path is required for upload type")
            plan["delete_source"] = data.delete_source
        elif data.type == "text":
            if not data.content or not data.content.strip():
                raise InvalidInput("Content is required for text type")
            plan["content"] = data.content
        else:
            raise InvalidInput("type 只能是 link / upload / text")

        title = (data.title or "").strip()[:500] or None
        source_id = self.sources.create(
            title=title or PLACEHOLDER_TITLE,
            asset_url=plan.get("url"),
            asset_file_path=plan.get("file_path"),
            notebook_ids=notebook_ids,
        )
        plan["source_id"] = source_id
        job_id = self.jobs.jobs.create("process_source", {k: v for k, v in plan.items() if k != "content"})
        self.sources.set_job(source_id, job_id)
        self.jobs.start(job_id, lambda jid: self._process(jid, plan))

        if data.async_processing:
            row = self.sources.get(source_id) or {}
            out = source_out(row, self.upload_dir)
            out.update(status="new", command_id=job_id, processing_info={"async": True, "queued": True})
            return out

        job = self.jobs.wait(job_id)
        if not job or job["status"] != "completed":
            error = (job or {}).get("error") or "处理超时，请改用异步处理或稍后重试"
            if job and job["status"] == "failed":
                _, paths = self.sources.delete(source_id)
                remove_uploaded_files(paths, self.upload_dir)
            raise InvalidInput(f"Failed to process source: {error}")
        return source_out(self.sources.get(source_id) or {}, self.upload_dir)

    def _extract(self, plan: dict) -> Extraction:
        kind = plan["kind"]
        if kind == "link":
            extraction = fetch_url(plan["url"], allow_private=self.allow_private_urls)
            return Extraction(title=extraction.title or _url_title(plan["url"]), content=extraction.content)
        if kind == "upload":
            return extract_file(pathlib.Path(plan["file_path"]))
        content = plan.get("content") or ""
        return Extraction(title=_first_line_title(content), content=content.strip())

    def _process(self, job_id: str, plan: dict) -> dict:
        source_id = plan["source_id"]
        if not self.sources.exists(source_id):
            raise NotFound(f"来源 {source_id} 已被删除")
        extraction = self._extract(plan)
        if not extraction.content.strip():
            raise ExtractionFailed("没能从这个来源抽取出任何文字（内容为空、打不开或格式不支持）。")
        if plan.get("delete_source") and plan.get("file_path"):
            remove_uploaded_files([plan["file_path"]], self.upload_dir)
        if not self.sources.save_extraction(source_id, full_text=extraction.content, extracted_title=extraction.title):
            raise NotFound(f"来源 {source_id} 已被删除")
        indexed = self.indexer.index_source(source_id, embed=bool(plan.get("embed")))
        insights, errors = 0, []
        for transformation_id in plan.get("transformations") or []:
            try:
                if self.insights.run_transformation(source_id, find_transformation(transformation_id)):
                    insights += 1
            except NotebookError as exc:
                log.warning("来源 %s 跑变换 %s 失败：%s", source_id, transformation_id, exc.detail)
                errors.append(f"{transformation_id}: {exc.detail}")
        return {
            "success": True,
            "source_id": source_id,
            "chunks": indexed["chunks"],
            "embedded_chunks": indexed["embedded_chunks"],
            "insights_created": insights,
            "transformation_errors": errors,
        }

    # ---- 修改 / 重试 / 删除 / 嵌入 ----
    def update(self, raw_id: str, fields: dict) -> dict:
        source_id = source_id_or_404(raw_id)
        fields = {key: value for key, value in fields.items() if value is not None}
        if "title" in fields:
            fields["title"] = str(fields["title"]).strip()[:500]
            if not fields["title"]:
                raise InvalidInput("Title cannot be empty")
        if "topics" in fields:
            fields["topics"] = [str(t).strip() for t in fields["topics"] if str(t).strip()][:50]
        if not self.sources.update_meta(source_id, fields):
            raise NotFound("Source not found")
        row = self.sources.get(source_id, full=False) or {}
        if "title" in fields:
            self.indexer.index.index_source_title(source_id, row.get("title"))
        return source_list_out(row, self.upload_dir)

    def retry(self, raw_id: str) -> dict:
        row = self._get_row(raw_id)
        source_id = row["id"]
        if self.jobs.is_active(row.get("job_id")):
            raise InvalidInput("Source is already processing")
        if not row.get("notebooks"):
            raise InvalidInput("Source is not linked to any notebook")
        plan: dict = {"source_id": source_id, "embed": True, "transformations": []}
        if row.get("asset_url"):
            plan.update(kind="link", url=row["asset_url"])
        elif row.get("asset_file_path"):
            plan.update(kind="upload", file_path=row["asset_file_path"])
        elif (row.get("full_text") or "").strip():
            plan.update(kind="text", content=row["full_text"])
        else:
            raise InvalidInput("Source has no content to reprocess")
        job_id = self.jobs.jobs.create("process_source", {k: v for k, v in plan.items() if k != "content"})
        self.sources.set_job(source_id, job_id)
        self.jobs.start(job_id, lambda jid: self._process(jid, plan))
        out = source_out(self.sources.get(source_id) or row, self.upload_dir)
        out.update(status="queued", command_id=job_id)
        return out

    def delete(self, raw_id: str) -> dict:
        source_id = source_id_or_404(raw_id)
        found, paths = self.sources.delete(source_id)
        if not found:
            raise NotFound("Source not found")
        remove_uploaded_files([p for p in paths if not self.sources.file_in_use_elsewhere(p, source_id)], self.upload_dir)
        return {"message": "Source deleted successfully"}

    def embed(self, raw_id: str, *, async_processing: bool) -> dict:
        source_id = source_id_or_404(raw_id)
        if not self.sources.exists(source_id):
            raise NotFound("Source not found")
        self.indexer.require_embedding()
        if async_processing:
            command_id = self.jobs.submit(
                "embed_source", {"source_id": source_id},
                lambda _job: {"source_id": source_id, "embedded_chunks": self.indexer.embed_source(source_id)},
            )
            return {"success": True, "message": "Embedding started", "command_id": command_id}
        count = self.indexer.embed_source(source_id)
        return {"success": True, "message": "Source embedded successfully", "chunks_created": count}

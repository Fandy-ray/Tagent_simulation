"""笔记本业务：校验参数、组织级联删除、删除后清理上传文件。"""

from __future__ import annotations

import logging
import pathlib

from app.errors.notebook import InvalidInput, NotFound
from app.repository.notebook.notebooks import ORDER_COLUMNS, NotebookRepository
from app.repository.notebook.sources import SourceRepository
from app.service.notebook.formatting import notebook_out
from app.util.notebook.ids import normalize
from app.util.notebook.timefmt import fmt

log = logging.getLogger(__name__)


def remove_uploaded_files(paths: list[str], upload_dir: pathlib.Path) -> None:
    """只删上传目录里的文件；路径不在上传目录里（被人改过库）就不碰。"""
    root = upload_dir.resolve()
    for raw in paths:
        try:
            path = pathlib.Path(raw).resolve()
            if path.is_relative_to(root) and path.is_file():
                path.unlink()
        except OSError as exc:
            log.warning("删除上传文件失败：%s", exc)


def notebook_id_or_404(raw: str) -> str:
    notebook_id = normalize("notebook", raw)
    if not notebook_id:
        raise NotFound("Notebook not found")
    return notebook_id


class NotebookService:
    def __init__(self, notebooks: NotebookRepository, sources: SourceRepository, upload_dir: pathlib.Path):
        self.notebooks = notebooks
        self.sources = sources
        self.upload_dir = upload_dir

    def list(self, *, archived: bool | None, order_by: str) -> list[dict]:
        parts = (order_by or "updated desc").strip().lower().split()
        field = parts[0] if parts else "updated"
        direction = parts[1] if len(parts) > 1 else "desc"
        if field not in ORDER_COLUMNS or direction not in {"asc", "desc"} or len(parts) > 2:
            raise InvalidInput("order_by 只能是 name/created/updated 加 asc/desc")
        rows = self.notebooks.list(archived=archived, order_field=field, descending=direction == "desc")
        return [notebook_out(row) for row in rows]

    def get(self, raw_id: str) -> dict:
        notebook_id = notebook_id_or_404(raw_id)
        row = self.notebooks.get(notebook_id)
        if not row:
            raise NotFound("Notebook not found")
        self.notebooks.mark_viewed(notebook_id)
        return notebook_out(row)

    def create(self, name: str, description: str) -> dict:
        name = (name or "").strip()
        if not name:
            raise InvalidInput("Notebook name cannot be empty")
        return notebook_out(self.notebooks.create(name, description or ""))

    def update(self, raw_id: str, fields: dict) -> dict:
        notebook_id = notebook_id_or_404(raw_id)
        if "name" in fields:
            if fields["name"] is None:
                fields.pop("name")
            elif not str(fields["name"]).strip():
                raise InvalidInput("Notebook name cannot be empty")
            else:
                fields["name"] = str(fields["name"]).strip()
        if fields.get("archived") is None:
            fields.pop("archived", None)
        if "description" in fields and fields["description"] is None:
            fields.pop("description")
        row = self.notebooks.update(notebook_id, fields)
        if not row:
            raise NotFound("Notebook not found")
        return notebook_out(row)

    def recently_viewed(self, limit: int) -> list[dict]:
        rows = self.notebooks.recently_viewed(limit)
        return [
            {"type": row["type"], "id": row["id"], "title": row["title"], "last_viewed_at": fmt(row["last_viewed_at"])}
            for row in rows
        ]

    def delete_preview(self, raw_id: str) -> dict:
        preview = self.notebooks.delete_preview(notebook_id_or_404(raw_id))
        if not preview:
            raise NotFound("Notebook not found")
        return preview

    def delete(self, raw_id: str, *, delete_exclusive_sources: bool) -> dict:
        notebook_id = notebook_id_or_404(raw_id)
        result = self.notebooks.delete(notebook_id, delete_exclusive_sources=delete_exclusive_sources)
        if result is None:
            raise NotFound("Notebook not found")
        remove_uploaded_files(result.pop("file_paths"), self.upload_dir)
        result.pop("shared_source_count", None)
        return {"message": "Notebook deleted successfully", **result}

    def _pair(self, raw_notebook: str, raw_source: str) -> tuple[str, str]:
        notebook_id = notebook_id_or_404(raw_notebook)
        if not self.notebooks.get(notebook_id):
            raise NotFound("Notebook not found")
        source_id = normalize("source", raw_source)
        if not source_id or not self.sources.exists(source_id):
            raise NotFound("Source not found")
        return notebook_id, source_id

    def add_source(self, raw_notebook: str, raw_source: str) -> dict:
        notebook_id, source_id = self._pair(raw_notebook, raw_source)
        created = self.notebooks.link_source(notebook_id, source_id)
        message = "Source linked to notebook successfully" if created else "Source is already linked to this notebook"
        return {"message": message}

    def remove_source(self, raw_notebook: str, raw_source: str) -> dict:
        notebook_id, source_id = self._pair(raw_notebook, raw_source)
        self.notebooks.unlink_source(notebook_id, source_id)
        return {"message": "Source removed from notebook successfully"}

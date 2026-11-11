"""洞察与内置变换：对来源跑一个变换（调模型）得到一条洞察；洞察可以删、可以存成笔记。"""

from __future__ import annotations

from app.errors.notebook import InvalidInput, NotFound
from app.infra.notebook.llm_client import LLMClient
from app.prompts.notebook.transformations import BUILTIN_TRANSFORMATIONS, transformation_messages
from app.repository.notebook.notebooks import NotebookRepository
from app.repository.notebook.notes import NoteRepository
from app.repository.notebook.sources import SourceRepository
from app.service.notebook.formatting import insight_out, note_out
from app.service.notebook.indexing import Indexer
from app.service.notebook.jobs import JobRunner
from app.service.notebook.notebook_service import notebook_id_or_404
from app.util.notebook.ids import normalize

MAX_INPUT_CHARS = 60000
_BY_ID = {item["id"]: item for item in BUILTIN_TRANSFORMATIONS}
_CREATED = "2026-11-11 00:00:00+00:00"


def transformation_out(item: dict) -> dict:
    return {**item, "model_id": None, "created": _CREATED, "updated": _CREATED}


def find_transformation(raw_id: str) -> dict:
    transformation_id = normalize("transformation", raw_id)
    item = _BY_ID.get(transformation_id or "")
    if not item:
        raise NotFound(f"Transformation {raw_id} not found")
    return item


class InsightService:
    def __init__(self, sources: SourceRepository, notes: NoteRepository, notebooks: NotebookRepository,
                 indexer: Indexer, jobs: JobRunner, llm: LLMClient):
        self.sources = sources
        self.notes = notes
        self.notebooks = notebooks
        self.indexer = indexer
        self.jobs = jobs
        self.llm = llm

    # ---- 变换（只读） ----
    def list_transformations(self) -> list[dict]:
        return [transformation_out(item) for item in BUILTIN_TRANSFORMATIONS]

    def get_transformation(self, raw_id: str) -> dict:
        return transformation_out(find_transformation(raw_id))

    # ---- 生成洞察 ----
    def run_transformation(self, source_id: str, transformation: dict) -> dict | None:
        source = self.sources.get(source_id)
        if not source:
            raise NotFound("Source not found")
        text = (source.get("full_text") or "").strip()
        if not text:
            raise InvalidInput("这个来源还没有正文，无法生成洞察")
        output = self.llm.complete(transformation_messages(transformation["prompt"], text[:MAX_INPUT_CHARS]))
        insight = self.sources.create_insight(source_id, transformation["title"], output)
        if insight:
            self.indexer.index_insight(insight)
        return insight

    def create_insight(self, raw_source_id: str, raw_transformation_id: str) -> dict:
        source_id = normalize("source", raw_source_id)
        if not source_id or not self.sources.exists(source_id):
            raise NotFound("Source not found")
        transformation = find_transformation(raw_transformation_id)

        def work(_job_id: str) -> dict:
            insight = self.run_transformation(source_id, transformation)
            return {"success": True, "source_id": source_id, "insight_id": insight["id"] if insight else None}

        command_id = self.jobs.submit(
            "run_transformation", {"source_id": source_id, "transformation_id": transformation["id"]}, work
        )
        return {
            "status": "pending",
            "message": "Insight generation started",
            "source_id": source_id,
            "transformation_id": transformation["id"],
            "command_id": command_id,
        }

    # ---- 洞察本身 ----
    def list_for_source(self, raw_source_id: str) -> list[dict]:
        source_id = normalize("source", raw_source_id)
        if not source_id or not self.sources.exists(source_id):
            raise NotFound("Source not found")
        return [insight_out(row) for row in self.sources.list_insights(source_id)]

    def _insight_or_404(self, raw_id: str) -> dict:
        insight_id = normalize("source_insight", raw_id)
        row = self.sources.get_insight(insight_id) if insight_id else None
        if not row:
            raise NotFound("Insight not found")
        return row

    def get(self, raw_id: str) -> dict:
        return insight_out(self._insight_or_404(raw_id))

    def delete(self, raw_id: str) -> dict:
        row = self._insight_or_404(raw_id)
        self.sources.delete_insight(row["id"])
        return {"message": "Insight deleted successfully"}

    def save_as_note(self, raw_id: str, notebook_id: str | None) -> dict:
        row = self._insight_or_404(raw_id)
        if notebook_id:
            notebook_id = notebook_id_or_404(notebook_id)
            if not self.notebooks.get(notebook_id):
                raise NotFound("Notebook not found")
        source = self.sources.get(row["source_id"], full=False)
        title = f"{row['insight_type']}（来自 {source.get('title') or '来源'}）" if source else row["insight_type"]
        note = self.notes.create(title=title[:200], content=row["content"], note_type="ai", notebook_id=notebook_id)
        self.indexer.index_note(note["id"], embed=False)
        command_id = self.jobs.submit(
            "embed_note", {"note_id": note["id"]},
            lambda _job: {"note_id": note["id"], "embedded": self.indexer.index_note(note["id"], embed=True)},
        )
        return note_out(note, command_id=command_id)

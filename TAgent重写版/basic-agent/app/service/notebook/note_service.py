"""笔记业务：校验、AI 笔记自动起标题、保存后建全文索引（同步）和向量（后台）。"""

from __future__ import annotations

import logging

from app.errors.notebook import InvalidInput, NotebookError, NotFound
from app.infra.notebook.llm_client import LLMClient
from app.prompts.notebook.chat import NOTE_TITLE
from app.repository.notebook.notebooks import NotebookRepository
from app.repository.notebook.notes import NoteRepository
from app.service.notebook.formatting import note_out
from app.service.notebook.indexing import Indexer
from app.service.notebook.jobs import JobRunner
from app.service.notebook.notebook_service import notebook_id_or_404
from app.util.notebook.ids import normalize

log = logging.getLogger(__name__)

NOTE_TYPES = {"human", "ai"}
MAX_TITLE = 200


def fallback_title(content: str) -> str:
    first = next((line.strip(" #*-\t") for line in content.splitlines() if line.strip(" #*-\t")), "")
    return (first[:30] + "…") if len(first) > 30 else (first or "Untitled")


def note_id_or_404(raw: str) -> str:
    note_id = normalize("note", raw)
    if not note_id:
        raise NotFound("Note not found")
    return note_id


class NoteService:
    def __init__(self, notes: NoteRepository, notebooks: NotebookRepository, indexer: Indexer,
                 jobs: JobRunner, llm: LLMClient):
        self.notes = notes
        self.notebooks = notebooks
        self.indexer = indexer
        self.jobs = jobs
        self.llm = llm

    def list(self, notebook_id: str | None) -> list[dict]:
        if notebook_id:
            notebook_id = notebook_id_or_404(notebook_id)
            if not self.notebooks.get(notebook_id):
                raise NotFound("Notebook not found")
        return [note_out(row) for row in self.notes.list(notebook_id)]

    def get(self, raw_id: str) -> dict:
        row = self.notes.get(note_id_or_404(raw_id))
        if not row:
            raise NotFound("Note not found")
        return note_out(row)

    def _generate_title(self, content: str) -> str:
        try:
            title = self.llm.complete(
                [{"role": "user", "content": NOTE_TITLE.format(content=content[:4000])}], temperature=0.2, max_tokens=60
            )
            title = title.strip().strip("\"'“”《》").splitlines()[0].strip()
            return title[:MAX_TITLE] or fallback_title(content)
        except NotebookError as exc:
            log.info("AI 笔记起标题失败，改用第一行：%s", exc.detail)
            return fallback_title(content)

    def _embed_later(self, note_id: str) -> str:
        return self.jobs.submit(
            "embed_note", {"note_id": note_id},
            lambda _job: {"note_id": note_id, "embedded": self.indexer.index_note(note_id, embed=True)},
        )

    def create(self, *, title: str | None, content: str, note_type: str | None, notebook_id: str | None) -> dict:
        note_type = note_type or "human"
        if note_type not in NOTE_TYPES:
            raise InvalidInput("Invalid note_type. Must be 'human' or 'ai'")
        if not content or not content.strip():
            raise InvalidInput("Note content cannot be empty")
        if notebook_id:
            notebook_id = notebook_id_or_404(notebook_id)
            if not self.notebooks.get(notebook_id):
                raise NotFound("Notebook not found")
        title = (title or "").strip()[:MAX_TITLE] or None
        if not title and note_type == "ai":
            title = self._generate_title(content)
        row = self.notes.create(title=title, content=content, note_type=note_type, notebook_id=notebook_id)
        self.indexer.index_note(row["id"], embed=False)
        return note_out(row, command_id=self._embed_later(row["id"]))

    def update(self, raw_id: str, fields: dict) -> dict:
        note_id = note_id_or_404(raw_id)
        fields = {key: value for key, value in fields.items() if value is not None}
        if "note_type" in fields and fields["note_type"] not in NOTE_TYPES:
            raise InvalidInput("Invalid note_type. Must be 'human' or 'ai'")
        if "content" in fields and not fields["content"].strip():
            raise InvalidInput("Note content cannot be empty")
        if "title" in fields:
            fields["title"] = fields["title"].strip()[:MAX_TITLE]
        row = self.notes.update(note_id, fields)
        if not row:
            raise NotFound("Note not found")
        command_id = None
        if "title" in fields or "content" in fields:
            self.indexer.index_note(note_id, embed=False)
            command_id = self._embed_later(note_id)
        return note_out(row, command_id=command_id)

    def embed(self, raw_id: str) -> dict:
        note_id = note_id_or_404(raw_id)
        if not self.notes.get(note_id):
            raise NotFound("Note not found")
        self.indexer.require_embedding()
        embedded = self.indexer.index_note(note_id, embed=True)
        message = "Note embedded successfully" if embedded else "Note has no content to embed"
        return {"success": embedded, "message": message, "chunks_created": 1 if embedded else 0}

    def delete(self, raw_id: str) -> dict:
        if not self.notes.delete(note_id_or_404(raw_id)):
            raise NotFound("Note not found")
        return {"message": "Note deleted successfully"}

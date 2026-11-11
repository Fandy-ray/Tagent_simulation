"""建索引：分块 → 全文索引 → 向量。来源处理、笔记保存、洞察生成都走这里。

嵌入模型不可用时只建全文索引，不算失败（原版没配嵌入模型时也是照样能存来源）。
"""

from __future__ import annotations

import logging

from app.errors.notebook import InvalidInput
from app.rag.notebook.chunking import split_text
from app.rag.notebook.embedder import Embedder
from app.rag.notebook.vectors import to_blob
from app.repository.notebook.notes import NoteRepository
from app.repository.notebook.search_index import SearchIndexRepository
from app.repository.notebook.sources import SourceRepository

log = logging.getLogger(__name__)


class Indexer:
    def __init__(self, sources: SourceRepository, notes: NoteRepository, index: SearchIndexRepository,
                 embedder: Embedder):
        self.sources = sources
        self.notes = notes
        self.index = index
        self.embedder = embedder

    def require_embedding(self) -> None:
        if not self.embedder.available():
            raise InvalidInput(f"没有可用的嵌入模型：{self.embedder.unavailable_reason()}")

    def _embed(self, texts: list[str]) -> list[bytes] | None:
        if not texts or not self.embedder.available():
            return None
        try:
            return [to_blob(vector) for vector in self.embedder.embed(texts)]
        except Exception as exc:  # noqa: BLE001 - 嵌入失败不影响全文检索
            log.warning("向量化失败：%s", exc)
            return None

    def index_source(self, source_id: str, *, embed: bool) -> dict:
        source = self.sources.get(source_id)
        if not source:
            return {"chunks": 0, "embedded_chunks": 0}
        chunks = self.sources.replace_chunks(source_id, split_text(source.get("full_text")))
        self.index.index_source(source_id, source.get("title"), chunks)
        embedded = self.embed_chunks(chunks) if embed else 0
        return {"chunks": len(chunks), "embedded_chunks": embedded}

    def embed_chunks(self, chunks: list[tuple[int, str]]) -> int:
        blobs = self._embed([content for _, content in chunks])
        if not blobs:
            return 0
        self.sources.set_chunk_embeddings([(chunk_id, blob) for (chunk_id, _), blob in zip(chunks, blobs)])
        return len(blobs)

    def embed_source(self, source_id: str) -> int:
        """「重新嵌入」按钮：分块还在就只补向量，没有分块（老数据或从没处理过）就整套重建。"""
        chunks = self.sources.chunks(source_id)
        if not chunks:
            return self.index_source(source_id, embed=True)["embedded_chunks"]
        return self.embed_chunks(chunks)

    def index_note(self, note_id: str, *, embed: bool = True) -> bool:
        note = self.notes.get(note_id)
        if not note:
            return False
        self.index.index_note(note_id, note.get("title"), note.get("content"))
        if not embed:
            return False
        text = "\n".join(part for part in (note.get("title"), note.get("content")) if part)
        blobs = self._embed([text]) if text.strip() else None
        if blobs:
            self.notes.set_embedding(note_id, blobs[0])
            return True
        return False

    def index_insight(self, insight: dict) -> None:
        self.index.index_insight(insight["id"], insight["source_id"], insight["content"])
        blobs = self._embed([insight["content"]])
        if blobs:
            self.sources.set_insight_embedding(insight["id"], blobs[0])

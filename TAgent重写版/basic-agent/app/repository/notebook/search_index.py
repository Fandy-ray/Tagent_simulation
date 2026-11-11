"""检索用的数据：全文索引（FTS5）的读写，以及向量矩阵的原始数据。

全文索引每一行对应「某条内容的某个字段」：
  kind=source_title / source_chunk  item_id=来源 id      parent_id=来源 id
  kind=insight                       item_id=洞察 id      parent_id=来源 id
  kind=note_title / note_content     item_id=笔记 id      parent_id=笔记 id
search_fts 只存切好的词（tokens），别的信息放 fts_rows，两张表按 rowid 对上。
"""

from __future__ import annotations

from app.rag.notebook.tokenize import index_tokens
from app.rag.notebook.vectors import VectorRow
from app.repository.notebook.cleanup import batches, delete_fts, marks
from app.repository.notebook.database import Database

SOURCE_KINDS = ("source_title", "source_chunk", "insight")
NOTE_KINDS = ("note_title", "note_content")


def _insert(conn, kind: str, item_id: str, parent_id: str, text: str | None, ref: int | None = None) -> None:
    tokens = index_tokens(text)
    if not tokens:
        return
    cursor = conn.execute(
        "INSERT INTO fts_rows (kind, item_id, parent_id, ref) VALUES (?, ?, ?, ?)", (kind, item_id, parent_id, ref)
    )
    conn.execute("INSERT INTO search_fts (rowid, tokens) VALUES (?, ?)", (cursor.lastrowid, tokens))


class SearchIndexRepository:
    def __init__(self, db: Database):
        self.db = db

    # ---- 写 ----
    def index_source(self, source_id: str, title: str | None, chunks: list[tuple[int, str]]) -> None:
        with self.db.transaction() as conn:
            if not conn.execute("SELECT 1 FROM sources WHERE id = ?", (source_id,)).fetchone():
                return  # 处理途中来源被删了
            delete_fts(conn, parent_ids=[source_id], kinds=("source_title", "source_chunk"))
            _insert(conn, "source_title", source_id, source_id, title)
            for chunk_id, content in chunks:
                _insert(conn, "source_chunk", source_id, source_id, content, chunk_id)

    def index_source_title(self, source_id: str, title: str | None) -> None:
        with self.db.transaction() as conn:
            delete_fts(conn, parent_ids=[source_id], kinds=("source_title",))
            _insert(conn, "source_title", source_id, source_id, title)

    def index_insight(self, insight_id: str, source_id: str, content: str) -> None:
        with self.db.transaction() as conn:
            delete_fts(conn, item_ids=[insight_id])
            _insert(conn, "insight", insight_id, source_id, content)

    def index_note(self, note_id: str, title: str | None, content: str | None) -> None:
        with self.db.transaction() as conn:
            if not conn.execute("SELECT 1 FROM notes WHERE id = ?", (note_id,)).fetchone():
                return
            delete_fts(conn, item_ids=[note_id])
            _insert(conn, "note_title", note_id, note_id, title)
            _insert(conn, "note_content", note_id, note_id, content)

    # ---- 读 ----
    def text_hits(self, match: str, *, kinds: tuple[str, ...], notebook_ids: list[str] | None,
                  limit: int) -> list[dict]:
        """BM25 越小越相关；这里取负号，回「分数越大越相关」。"""
        if not kinds:
            return []
        params: list = [match, *kinds]
        scope = ""
        if notebook_ids is not None:
            scope = (
                f" AND (r.parent_id IN (SELECT source_id FROM source_notebooks WHERE notebook_id IN ({marks(notebook_ids)}))"
                f" OR r.parent_id IN (SELECT note_id FROM note_notebooks WHERE notebook_id IN ({marks(notebook_ids)})))"
            )
            params += [*notebook_ids, *notebook_ids]
        sql = (
            "SELECT r.rowid AS rowid, r.kind, r.item_id, r.parent_id, r.ref, -bm25(search_fts) AS score "
            "FROM search_fts JOIN fts_rows r ON r.rowid = search_fts.rowid "
            f"WHERE search_fts MATCH ? AND r.kind IN ({marks(list(kinds))}){scope} "
            "ORDER BY bm25(search_fts) LIMIT ?"
        )
        return [dict(row) for row in self.db.connection().execute(sql, [*params, limit])]

    def row_tokens(self, rowids: list[int]) -> dict[int, set[str]]:
        out: dict[int, set[str]] = {}
        for batch in batches(str(r) for r in rowids):
            rows = self.db.connection().execute(
                f"SELECT rowid, tokens FROM search_fts WHERE rowid IN ({marks(batch)})", [int(r) for r in batch]
            )
            for row in rows:
                out[int(row[0])] = set((row[1] or "").split())
        return out

    def scope_members(self, notebook_ids: list[str]) -> tuple[set[str], set[str]]:
        conn = self.db.connection()
        sources = {
            row[0]
            for row in conn.execute(
                f"SELECT source_id FROM source_notebooks WHERE notebook_id IN ({marks(notebook_ids)})", notebook_ids
            )
        }
        notes = {
            row[0]
            for row in conn.execute(
                f"SELECT note_id FROM note_notebooks WHERE notebook_id IN ({marks(notebook_ids)})", notebook_ids
            )
        }
        return sources, notes

    def vector_rows(self) -> list[tuple[VectorRow, bytes]]:
        conn = self.db.connection()
        out: list[tuple[VectorRow, bytes]] = []
        for row in conn.execute("SELECT source_id, content, embedding FROM chunks WHERE embedding IS NOT NULL"):
            out.append((VectorRow("chunk", row[0], row[0], row[1]), row[2]))
        for row in conn.execute("SELECT id, source_id, content, embedding FROM insights WHERE embedding IS NOT NULL"):
            out.append((VectorRow("insight", row[0], row[1], row[2]), row[3]))
        for row in conn.execute("SELECT id, content, embedding FROM notes WHERE embedding IS NOT NULL"):
            out.append((VectorRow("note", row[0], row[0], row[1] or ""), row[2]))
        return out

    def titles(self, *, source_ids: set[str], note_ids: set[str], insight_ids: set[str]) -> dict[str, str]:
        conn = self.db.connection()
        out: dict[str, str] = {}
        for batch in batches(sorted(source_ids)):
            for row in conn.execute(f"SELECT id, title FROM sources WHERE id IN ({marks(batch)})", batch):
                out[row[0]] = row[1] or ""
        for batch in batches(sorted(note_ids)):
            for row in conn.execute(f"SELECT id, title FROM notes WHERE id IN ({marks(batch)})", batch):
                out[row[0]] = row[1] or ""
        for batch in batches(sorted(insight_ids)):
            for row in conn.execute(
                f"SELECT i.id, i.insight_type, s.title FROM insights i JOIN sources s ON s.id = i.source_id "
                f"WHERE i.id IN ({marks(batch)})",
                batch,
            ):
                out[row[0]] = f"{row[1]} - {row[2] or ''}"
        return out

    def hit_texts(self, hits: list[dict], *, max_chars: int) -> dict[str, str]:
        """给问答拼上下文：命中的分块原文、洞察、笔记正文；只命中来源标题的取第一块。"""
        conn = self.db.connection()
        out: dict[str, str] = {}
        for hit in hits:
            key, kind = hit["item_id"], hit["kind"]
            if kind == "source_chunk" and hit.get("ref") is not None:
                row = conn.execute("SELECT content FROM chunks WHERE id = ?", (hit["ref"],)).fetchone()
            elif kind == "source_title":
                row = conn.execute(
                    "SELECT content FROM chunks WHERE source_id = ? ORDER BY ord LIMIT 1", (key,)
                ).fetchone()
            elif kind == "insight":
                row = conn.execute("SELECT content FROM insights WHERE id = ?", (key,)).fetchone()
            else:
                row = conn.execute("SELECT content FROM notes WHERE id = ?", (key,)).fetchone()
            text = (row[0] if row else "") or ""
            if not text:
                continue
            joined = (out.get(key, "") + "\n\n" + text).strip() if key in out else text
            out[key] = joined[:max_chars]
        return out

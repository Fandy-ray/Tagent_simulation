"""来源仓储：来源本身、分块（含向量）、洞察、和笔记本的关联。"""

from __future__ import annotations

import json

from app.repository.notebook.cleanup import delete_fts, marks, purge_sources
from app.repository.notebook.database import Database
from app.util.notebook.ids import new_id
from app.util.notebook.timefmt import now_ms

PLACEHOLDER_TITLE = "Processing..."

_LIST_COLUMNS = """
    s.id, s.title, s.topics, s.asset_url, s.asset_file_path, s.job_id, s.created, s.updated,
    (SELECT COUNT(*) FROM insights i WHERE i.source_id = s.id) AS insights_count,
    (SELECT COUNT(*) FROM chunks c WHERE c.source_id = s.id AND c.embedding IS NOT NULL) AS embedded_chunks,
    j.status AS job_status, j.started_at AS job_started_at, j.completed_at AS job_completed_at,
    j.error AS job_error, j.result AS job_result
"""

SORT_COLUMNS = {
    "type": "CASE WHEN s.asset_file_path IS NOT NULL THEN 0 WHEN s.asset_url IS NOT NULL THEN 1 ELSE 2 END",
    "title": "COALESCE(s.title, '') COLLATE NOCASE",
    "created": "s.created",
    "updated": "s.updated",
    "insights_count": "insights_count",
    "embedded": "(embedded_chunks > 0)",
}


def _row(row) -> dict:
    data = dict(row)
    try:
        data["topics"] = json.loads(data.get("topics") or "[]")
    except ValueError:
        data["topics"] = []
    return data


class SourceRepository:
    def __init__(self, db: Database):
        self.db = db

    # ---- 来源 ----
    def list(self, *, notebook_id: str | None, limit: int, offset: int, sort_by: str, descending: bool) -> list[dict]:
        where = "WHERE s.id IN (SELECT source_id FROM source_notebooks WHERE notebook_id = ?)" if notebook_id else ""
        params: list = [notebook_id] if notebook_id else []
        direction = "DESC" if descending else "ASC"
        sql = (
            f"SELECT {_LIST_COLUMNS} FROM sources s LEFT JOIN jobs j ON j.id = s.job_id {where} "
            f"ORDER BY {SORT_COLUMNS[sort_by]} {direction}, s.id {direction} LIMIT ? OFFSET ?"
        )
        return [_row(row) for row in self.db.connection().execute(sql, [*params, limit, offset])]

    def get(self, source_id: str, *, full: bool = True) -> dict | None:
        extra = ", s.full_text" if full else ""
        row = self.db.connection().execute(
            f"SELECT {_LIST_COLUMNS}{extra} FROM sources s LEFT JOIN jobs j ON j.id = s.job_id WHERE s.id = ?",
            (source_id,),
        ).fetchone()
        if not row:
            return None
        data = _row(row)
        data["notebooks"] = self.notebooks_of(source_id)
        return data

    def exists(self, source_id: str) -> bool:
        return bool(self.db.connection().execute("SELECT 1 FROM sources WHERE id = ?", (source_id,)).fetchone())

    def notebooks_of(self, source_id: str) -> list[str]:
        rows = self.db.connection().execute(
            "SELECT notebook_id FROM source_notebooks WHERE source_id = ? ORDER BY created", (source_id,)
        )
        return [row[0] for row in rows]

    def create(self, *, title: str | None, asset_url: str | None, asset_file_path: str | None,
               notebook_ids: list[str]) -> str:
        now = now_ms()
        source_id = new_id("source")
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO sources (id, title, asset_url, asset_file_path, created, updated) VALUES (?, ?, ?, ?, ?, ?)",
                (source_id, title, asset_url, asset_file_path, now, now),
            )
            for notebook_id in notebook_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO source_notebooks (source_id, notebook_id, created) VALUES (?, ?, ?)",
                    (source_id, notebook_id, now),
                )
                conn.execute("UPDATE notebooks SET updated = ? WHERE id = ?", (now, notebook_id))
        return source_id

    def set_job(self, source_id: str, job_id: str | None) -> None:
        with self.db.transaction() as conn:
            conn.execute("UPDATE sources SET job_id = ? WHERE id = ?", (job_id, source_id))

    def update_meta(self, source_id: str, fields: dict) -> bool:
        sets, values = [], []
        if "title" in fields:
            sets.append("title = ?")
            values.append(fields["title"])
        if "topics" in fields:
            sets.append("topics = ?")
            values.append(json.dumps(fields["topics"] or [], ensure_ascii=False))
        with self.db.transaction() as conn:
            if sets:
                cursor = conn.execute(
                    f"UPDATE sources SET {', '.join(sets)}, updated = ? WHERE id = ?", [*values, now_ms(), source_id]
                )
                return bool(cursor.rowcount)
            return bool(conn.execute("SELECT 1 FROM sources WHERE id = ?", (source_id,)).fetchone())

    def save_extraction(self, source_id: str, *, full_text: str, extracted_title: str | None) -> dict | None:
        """写正文；标题只在空着或还是占位符时用抽取出来的（保留用户自己起的标题，同原版）。"""
        with self.db.transaction() as conn:
            row = conn.execute("SELECT title FROM sources WHERE id = ?", (source_id,)).fetchone()
            if not row:
                return None
            title = row[0]
            if extracted_title and (not title or title == PLACEHOLDER_TITLE):
                title = extracted_title.strip()[:500]
            conn.execute(
                "UPDATE sources SET full_text = ?, title = ?, updated = ? WHERE id = ?",
                (full_text, title, now_ms(), source_id),
            )
        return self.get(source_id)

    def mark_viewed(self, source_id: str) -> None:
        with self.db.transaction() as conn:
            conn.execute("UPDATE sources SET last_viewed_at = ? WHERE id = ?", (now_ms(), source_id))

    def delete(self, source_id: str) -> tuple[bool, list[str]]:
        with self.db.transaction() as conn:
            if not conn.execute("SELECT 1 FROM sources WHERE id = ?", (source_id,)).fetchone():
                return False, []
            paths = purge_sources(conn, [source_id])
        self.db.bump_vectors()
        return True, paths

    def file_in_use_elsewhere(self, file_path: str, source_id: str) -> bool:
        row = self.db.connection().execute(
            "SELECT 1 FROM sources WHERE asset_file_path = ? AND id != ? LIMIT 1", (file_path, source_id)
        ).fetchone()
        return bool(row)

    # ---- 分块 ----
    def replace_chunks(self, source_id: str, chunks: list[str]) -> list[tuple[int, str]]:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
            out = []
            for order, content in enumerate(chunks):
                cursor = conn.execute(
                    "INSERT INTO chunks (source_id, ord, content) VALUES (?, ?, ?)", (source_id, order, content)
                )
                out.append((int(cursor.lastrowid), content))
        self.db.bump_vectors()
        return out

    def chunks(self, source_id: str) -> list[tuple[int, str]]:
        rows = self.db.connection().execute(
            "SELECT id, content FROM chunks WHERE source_id = ? ORDER BY ord", (source_id,)
        )
        return [(int(row[0]), row[1]) for row in rows]

    def set_chunk_embeddings(self, pairs: list[tuple[int, bytes]]) -> None:
        with self.db.transaction() as conn:
            conn.executemany("UPDATE chunks SET embedding = ? WHERE id = ?", [(blob, cid) for cid, blob in pairs])
        self.db.bump_vectors()

    # ---- 洞察 ----
    def list_insights(self, source_id: str) -> list[dict]:
        rows = self.db.connection().execute(
            "SELECT id, source_id, insight_type, content, created, updated FROM insights "
            "WHERE source_id = ? ORDER BY created DESC, id",
            (source_id,),
        )
        return [dict(row) for row in rows]

    def get_insight(self, insight_id: str) -> dict | None:
        row = self.db.connection().execute(
            "SELECT id, source_id, insight_type, content, created, updated FROM insights WHERE id = ?", (insight_id,)
        ).fetchone()
        return dict(row) if row else None

    def create_insight(self, source_id: str, insight_type: str, content: str) -> dict | None:
        now = now_ms()
        insight_id = new_id("source_insight")
        with self.db.transaction() as conn:
            if not conn.execute("SELECT 1 FROM sources WHERE id = ?", (source_id,)).fetchone():
                return None
            conn.execute(
                "INSERT INTO insights (id, source_id, insight_type, content, created, updated) VALUES (?, ?, ?, ?, ?, ?)",
                (insight_id, source_id, insight_type, content, now, now),
            )
        return self.get_insight(insight_id)

    def set_insight_embedding(self, insight_id: str, blob: bytes) -> None:
        with self.db.transaction() as conn:
            conn.execute("UPDATE insights SET embedding = ? WHERE id = ?", (blob, insight_id))
        self.db.bump_vectors()

    def delete_insight(self, insight_id: str) -> bool:
        with self.db.transaction() as conn:
            delete_fts(conn, item_ids=[insight_id])
            cursor = conn.execute("DELETE FROM insights WHERE id = ?", (insight_id,))
        self.db.bump_vectors()
        return bool(cursor.rowcount)

    def insights_for(self, source_ids: list[str]) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        if not source_ids:
            return out
        rows = self.db.connection().execute(
            f"SELECT id, source_id, insight_type, content FROM insights WHERE source_id IN ({marks(source_ids)}) "
            "ORDER BY created",
            source_ids,
        )
        for row in rows:
            out.setdefault(row["source_id"], []).append(dict(row))
        return out

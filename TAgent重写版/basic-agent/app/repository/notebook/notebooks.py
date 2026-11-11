"""笔记本仓储：增删改查、来源关联、删除预览与级联删除、最近浏览。"""

from __future__ import annotations

from app.repository.notebook.cleanup import marks, purge_notes, purge_sources
from app.repository.notebook.database import Database
from app.util.notebook.ids import new_id
from app.util.notebook.timefmt import now_ms

_COUNTS = (
    "(SELECT COUNT(*) FROM source_notebooks sn WHERE sn.notebook_id = n.id) AS source_count, "
    "(SELECT COUNT(*) FROM note_notebooks nn WHERE nn.notebook_id = n.id) AS note_count"
)
ORDER_COLUMNS = {"name": "n.name COLLATE NOCASE", "created": "n.created", "updated": "n.updated"}


class NotebookRepository:
    def __init__(self, db: Database):
        self.db = db

    def list(self, *, archived: bool | None, order_field: str, descending: bool) -> list[dict]:
        where = "" if archived is None else "WHERE n.archived = ?"
        params = [] if archived is None else [1 if archived else 0]
        direction = "DESC" if descending else "ASC"
        sql = (
            f"SELECT n.*, {_COUNTS} FROM notebooks n {where} "
            f"ORDER BY {ORDER_COLUMNS[order_field]} {direction}, n.id {direction}"
        )
        return [dict(row) for row in self.db.connection().execute(sql, params)]

    def get(self, notebook_id: str) -> dict | None:
        row = self.db.connection().execute(
            f"SELECT n.*, {_COUNTS} FROM notebooks n WHERE n.id = ?", (notebook_id,)
        ).fetchone()
        return dict(row) if row else None

    def existing(self, notebook_ids: list[str]) -> set[str]:
        if not notebook_ids:
            return set()
        rows = self.db.connection().execute(
            f"SELECT id FROM notebooks WHERE id IN ({marks(notebook_ids)})", notebook_ids
        )
        return {row[0] for row in rows}

    def create(self, name: str, description: str) -> dict:
        now = now_ms()
        notebook_id = new_id("notebook")
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO notebooks (id, name, description, archived, created, updated) VALUES (?, ?, ?, 0, ?, ?)",
                (notebook_id, name, description, now, now),
            )
        return self.get(notebook_id) or {}

    def update(self, notebook_id: str, fields: dict) -> dict | None:
        allowed = {key: fields[key] for key in ("name", "description", "archived") if key in fields}
        if allowed:
            if "archived" in allowed:
                allowed["archived"] = 1 if allowed["archived"] else 0
            sets = ", ".join(f"{key} = ?" for key in allowed)
            with self.db.transaction() as conn:
                conn.execute(
                    f"UPDATE notebooks SET {sets}, updated = ? WHERE id = ?",
                    [*allowed.values(), now_ms(), notebook_id],
                )
        return self.get(notebook_id)

    def mark_viewed(self, notebook_id: str) -> None:
        with self.db.transaction() as conn:
            conn.execute("UPDATE notebooks SET last_viewed_at = ? WHERE id = ?", (now_ms(), notebook_id))

    def recently_viewed(self, limit: int) -> list[dict]:
        rows = self.db.connection().execute(
            """
            SELECT 'notebook' AS type, id, name AS title, last_viewed_at FROM notebooks
             WHERE last_viewed_at IS NOT NULL
            UNION ALL
            SELECT 'source' AS type, id, COALESCE(title, '') AS title, last_viewed_at FROM sources
             WHERE last_viewed_at IS NOT NULL
            ORDER BY last_viewed_at DESC LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in rows]

    def link_source(self, notebook_id: str, source_id: str) -> bool:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO source_notebooks (source_id, notebook_id, created) VALUES (?, ?, ?)",
                (source_id, notebook_id, now_ms()),
            )
            if cursor.rowcount:
                conn.execute("UPDATE notebooks SET updated = ? WHERE id = ?", (now_ms(), notebook_id))
            return bool(cursor.rowcount)

    def unlink_source(self, notebook_id: str, source_id: str) -> bool:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM source_notebooks WHERE source_id = ? AND notebook_id = ?", (source_id, notebook_id)
            )
            if cursor.rowcount:
                conn.execute("UPDATE notebooks SET updated = ? WHERE id = ?", (now_ms(), notebook_id))
            return bool(cursor.rowcount)

    def _source_split(self, conn, notebook_id: str) -> tuple[list[str], list[str]]:
        """(只属于这个笔记本的来源, 还挂在别的笔记本上的来源)。"""
        rows = conn.execute(
            """
            SELECT sn.source_id,
                   (SELECT COUNT(*) FROM source_notebooks o WHERE o.source_id = sn.source_id) AS links
              FROM source_notebooks sn WHERE sn.notebook_id = ?
            """,
            (notebook_id,),
        ).fetchall()
        exclusive = [row[0] for row in rows if row[1] <= 1]
        shared = [row[0] for row in rows if row[1] > 1]
        return exclusive, shared

    def delete_preview(self, notebook_id: str) -> dict | None:
        conn = self.db.connection()
        notebook = self.get(notebook_id)
        if not notebook:
            return None
        exclusive, shared = self._source_split(conn, notebook_id)
        return {
            "notebook_id": notebook_id,
            "notebook_name": notebook["name"],
            "note_count": notebook["note_count"],
            "exclusive_source_count": len(exclusive),
            "shared_source_count": len(shared),
        }

    def delete(self, notebook_id: str, *, delete_exclusive_sources: bool) -> dict | None:
        """级联顺序同原版：删笔记 → 处理来源（删独占的或只解除关联）→ 删聊天会话 → 删笔记本。"""
        with self.db.transaction() as conn:
            if not conn.execute("SELECT 1 FROM notebooks WHERE id = ?", (notebook_id,)).fetchone():
                return None
            note_ids = [
                row[0] for row in conn.execute("SELECT note_id FROM note_notebooks WHERE notebook_id = ?", (notebook_id,))
            ]
            purge_notes(conn, note_ids)
            exclusive, shared = self._source_split(conn, notebook_id)
            deleted_sources = exclusive if delete_exclusive_sources else []
            file_paths = purge_sources(conn, deleted_sources)
            unlinked = conn.execute(
                "DELETE FROM source_notebooks WHERE notebook_id = ?", (notebook_id,)
            ).rowcount
            chats = conn.execute(
                "DELETE FROM chat_sessions WHERE kind = 'notebook' AND target_id = ?", (notebook_id,)
            ).rowcount
            conn.execute("DELETE FROM notebooks WHERE id = ?", (notebook_id,))
        self.db.bump_vectors()
        return {
            "deleted_notes": len(note_ids),
            "deleted_sources": len(deleted_sources),
            "unlinked_sources": unlinked,
            "deleted_chat_sessions": chats,
            "file_paths": file_paths,
            "shared_source_count": len(shared),
        }

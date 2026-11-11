"""笔记仓储。笔记通过 note_notebooks 挂到笔记本上（原版的 artifact 关系）。"""

from __future__ import annotations

from app.repository.notebook.cleanup import purge_notes
from app.repository.notebook.database import Database
from app.util.notebook.ids import new_id
from app.util.notebook.timefmt import now_ms

_COLUMNS = "n.id, n.title, n.content, n.note_type, n.created, n.updated"


class NoteRepository:
    def __init__(self, db: Database):
        self.db = db

    def list(self, notebook_id: str | None) -> list[dict]:
        if notebook_id:
            rows = self.db.connection().execute(
                f"SELECT {_COLUMNS} FROM notes n JOIN note_notebooks nn ON nn.note_id = n.id "
                "WHERE nn.notebook_id = ? ORDER BY n.updated DESC, n.id",
                (notebook_id,),
            )
        else:
            rows = self.db.connection().execute(f"SELECT {_COLUMNS} FROM notes n ORDER BY n.updated DESC, n.id")
        return [dict(row) for row in rows]

    def get(self, note_id: str) -> dict | None:
        row = self.db.connection().execute(f"SELECT {_COLUMNS} FROM notes n WHERE n.id = ?", (note_id,)).fetchone()
        return dict(row) if row else None

    def notebooks_of(self, note_id: str) -> list[str]:
        rows = self.db.connection().execute(
            "SELECT notebook_id FROM note_notebooks WHERE note_id = ? ORDER BY created", (note_id,)
        )
        return [row[0] for row in rows]

    def create(self, *, title: str | None, content: str, note_type: str, notebook_id: str | None) -> dict:
        now = now_ms()
        note_id = new_id("note")
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO notes (id, title, content, note_type, created, updated) VALUES (?, ?, ?, ?, ?, ?)",
                (note_id, title, content, note_type, now, now),
            )
            if notebook_id:
                conn.execute(
                    "INSERT OR IGNORE INTO note_notebooks (note_id, notebook_id, created) VALUES (?, ?, ?)",
                    (note_id, notebook_id, now),
                )
                conn.execute("UPDATE notebooks SET updated = ? WHERE id = ?", (now, notebook_id))
        return self.get(note_id) or {}

    def update(self, note_id: str, fields: dict) -> dict | None:
        allowed = {key: fields[key] for key in ("title", "content", "note_type") if key in fields}
        with self.db.transaction() as conn:
            if not conn.execute("SELECT 1 FROM notes WHERE id = ?", (note_id,)).fetchone():
                return None
            if allowed:
                sets = ", ".join(f"{key} = ?" for key in allowed)
                conn.execute(f"UPDATE notes SET {sets}, updated = ? WHERE id = ?", [*allowed.values(), now_ms(), note_id])
                if "content" in allowed:
                    conn.execute("UPDATE notes SET embedding = NULL WHERE id = ?", (note_id,))
        if "content" in allowed:
            self.db.bump_vectors()
        return self.get(note_id)

    def delete(self, note_id: str) -> bool:
        with self.db.transaction() as conn:
            if not conn.execute("SELECT 1 FROM notes WHERE id = ?", (note_id,)).fetchone():
                return False
            purge_notes(conn, [note_id])
        self.db.bump_vectors()
        return True

    def set_embedding(self, note_id: str, blob: bytes | None) -> None:
        with self.db.transaction() as conn:
            conn.execute("UPDATE notes SET embedding = ? WHERE id = ?", (blob, note_id))
        self.db.bump_vectors()

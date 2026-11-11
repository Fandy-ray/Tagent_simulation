"""聊天会话与消息。原版把消息存在 LangGraph 的检查点里，这里直接存表。

会话分两种：kind='notebook'（笔记本聊天栏）、kind='source'（来源详情里的聊天）。
"""

from __future__ import annotations

from app.repository.notebook.database import Database
from app.util.notebook.ids import new_id
from app.util.notebook.timefmt import now_ms

_SESSION = (
    "s.id, s.kind, s.target_id, s.title, s.model_override, s.created, s.updated, "
    "(SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id) AS message_count"
)


class ChatRepository:
    def __init__(self, db: Database):
        self.db = db

    def create_session(self, *, kind: str, target_id: str, title: str, model_override: str | None) -> dict:
        now = now_ms()
        session_id = new_id("chat_session")
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO chat_sessions (id, kind, target_id, title, model_override, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, kind, target_id, title, model_override, now, now),
            )
        return self.get_session(session_id) or {}

    def list_sessions(self, kind: str, target_id: str) -> list[dict]:
        rows = self.db.connection().execute(
            f"SELECT {_SESSION} FROM chat_sessions s WHERE s.kind = ? AND s.target_id = ? "
            "ORDER BY s.updated DESC, s.id",
            (kind, target_id),
        )
        return [dict(row) for row in rows]

    def get_session(self, session_id: str) -> dict | None:
        row = self.db.connection().execute(
            f"SELECT {_SESSION} FROM chat_sessions s WHERE s.id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_session(self, session_id: str, fields: dict) -> dict | None:
        allowed = {key: fields[key] for key in ("title", "model_override") if key in fields}
        with self.db.transaction() as conn:
            if allowed:
                sets = ", ".join(f"{key} = ?" for key in allowed)
                conn.execute(
                    f"UPDATE chat_sessions SET {sets}, updated = ? WHERE id = ?",
                    [*allowed.values(), now_ms(), session_id],
                )
        return self.get_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        with self.db.transaction() as conn:
            return bool(conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,)).rowcount)

    def messages(self, session_id: str) -> list[dict]:
        rows = self.db.connection().execute(
            "SELECT id, role, content, created FROM chat_messages WHERE session_id = ? ORDER BY seq",
            (session_id,),
        )
        return [dict(row) for row in rows]

    def append(self, session_id: str, items: list[tuple[str, str]]) -> list[dict]:
        """追加若干条 (role, content)，回新加的消息。会话不存在（中途被删）就什么都不写。"""
        now = now_ms()
        added = []
        with self.db.transaction() as conn:
            if not conn.execute("SELECT 1 FROM chat_sessions WHERE id = ?", (session_id,)).fetchone():
                return []
            seq = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM chat_messages WHERE session_id = ?", (session_id,)
            ).fetchone()[0]
            for role, content in items:
                seq += 1
                message_id = new_id("msg")
                conn.execute(
                    "INSERT INTO chat_messages (id, session_id, seq, role, content, created) VALUES (?, ?, ?, ?, ?, ?)",
                    (message_id, session_id, seq, role, content, now),
                )
                added.append({"id": message_id, "role": role, "content": content, "created": now})
            conn.execute("UPDATE chat_sessions SET updated = ? WHERE id = ?", (now, session_id))
        return added

"""后台任务记录（取代 surreal-commands 的 command 表），前端轮询它看来源处理到哪了。

状态：queued → running → completed / failed。
"""

from __future__ import annotations

import json

from app.repository.notebook.database import Database
from app.util.notebook.ids import new_id
from app.util.notebook.timefmt import now_ms

MAX_ERROR = 2000


class JobRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, name: str, args: dict) -> str:
        now = now_ms()
        job_id = new_id("command")
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO jobs (id, name, status, args, created, updated) VALUES (?, ?, 'queued', ?, ?, ?)",
                (job_id, name, json.dumps(args, ensure_ascii=False), now, now),
            )
        return job_id

    def mark_running(self, job_id: str) -> None:
        now = now_ms()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'running', started_at = ?, updated = ?, error = NULL WHERE id = ?",
                (now, now, job_id),
            )

    def mark_completed(self, job_id: str, result: dict) -> None:
        now = now_ms()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'completed', result = ?, completed_at = ?, updated = ? WHERE id = ?",
                (json.dumps(result, ensure_ascii=False), now, now, job_id),
            )

    def mark_failed(self, job_id: str, error: str) -> None:
        now = now_ms()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'failed', error = ?, completed_at = ?, updated = ? WHERE id = ?",
                ((error or "未知错误")[:MAX_ERROR], now, now, job_id),
            )

    def get(self, job_id: str) -> dict | None:
        row = self.db.connection().execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        for key in ("args", "result"):
            try:
                data[key] = json.loads(data[key]) if data.get(key) else None
            except ValueError:
                data[key] = None
        return data

    def fail_unfinished(self, reason: str) -> int:
        """服务重启时，上次没跑完的任务不会再有人接手：标成失败，用户可以点重试。"""
        now = now_ms()
        with self.db.transaction() as conn:
            return conn.execute(
                "UPDATE jobs SET status = 'failed', error = ?, completed_at = ?, updated = ? "
                "WHERE status IN ('queued', 'running')",
                (reason, now, now),
            ).rowcount

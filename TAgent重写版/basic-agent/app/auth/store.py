"""SurrealDB 持久化。只连接 TAgent 专用 namespace/database。

运行进程使用数据库级账号；建表由 tools/init_auth_db.py 单独执行。
所有查询变量均绑定，不拼接来自 HTTP 的字符串。
"""

from __future__ import annotations

import threading
from typing import Any

from surrealdb import Surreal


class IdentityStore:
    def __init__(self, url: str, namespace: str, database: str, username: str, password: str):
        if not all((url, namespace, database)) or (
            not url.startswith("mem://") and not all((username, password))
        ):
            raise ValueError("TAgent identity database configuration is incomplete")
        self.url = url
        self.namespace = namespace
        self.database = database
        self.username = username
        self.password = password
        self._local = threading.local()
        self._connections: list[Any] = []
        self._lock = threading.Lock()

    def _db(self):
        db = getattr(self._local, "db", None)
        if db is None:
            db = Surreal(self.url)
            try:
                db.connect()
                if not self.url.startswith("mem://"):
                    db.signin({
                        "username": self.username,
                        "password": self.password,
                        "namespace": self.namespace,
                        "database": self.database,
                    })
                db.use(self.namespace, self.database)
            except Exception:
                db.close()
                raise
            self._local.db = db
            with self._lock:
                self._connections.append(db)
        return db

    def query(self, statement: str, variables: dict[str, Any] | None = None):
        # surrealdb Python SDK 2.x 的 query 返回第一条语句的结果。
        try:
            return self._db().query(statement, variables or {})
        except Exception:
            db = getattr(self._local, "db", None)
            if db is not None:
                try:
                    db.close()
                finally:
                    self._local.db = None
            raise

    def first(self, statement: str, variables: dict[str, Any] | None = None):
        result = self.query(statement, variables)
        if isinstance(result, list):
            return result[0] if result else None
        return result

    def close(self) -> None:
        with self._lock:
            connections, self._connections = self._connections, []
        for db in connections:
            try:
                db.close()
            except Exception:
                pass

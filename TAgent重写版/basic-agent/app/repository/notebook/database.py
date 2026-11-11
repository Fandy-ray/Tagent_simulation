"""SQLite 连接与迁移，写法照 tagent 的 learning_store.py：

- 每个线程一个连接（waitress 多线程 + 后台任务线程），isolation_level=None 自己管事务；
- WAL、busy_timeout，读写互不阻塞；
- MIGRATIONS 按顺序追加，PRAGMA user_version 记到第几条；BEGIN IMMEDIATE 之后再读版本，
  两个进程同时启动也不会把同一条迁移跑两遍。

表和原版 SurrealDB 的对应：notebooks↔notebook、sources↔source、notes↔note、
source_notebooks↔reference、note_notebooks↔artifact、chunks↔source_embedding、
insights↔source_insight、chat_sessions/chat_messages↔chat_session + LangGraph 检查点、
jobs↔surreal-commands 的 command。全文索引 search_fts + fts_rows 取代 BM25 索引。
"""

from __future__ import annotations

import contextlib
import pathlib
import sqlite3
import threading

MIGRATIONS: list[str] = [
    """
    CREATE TABLE notebooks (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        archived INTEGER NOT NULL DEFAULT 0,
        created INTEGER NOT NULL,
        updated INTEGER NOT NULL,
        last_viewed_at INTEGER
    );
    CREATE TABLE sources (
        id TEXT PRIMARY KEY,
        title TEXT,
        topics TEXT NOT NULL DEFAULT '[]',
        full_text TEXT,
        asset_url TEXT,
        asset_file_path TEXT,
        job_id TEXT,
        created INTEGER NOT NULL,
        updated INTEGER NOT NULL,
        last_viewed_at INTEGER
    );
    CREATE TABLE source_notebooks (
        source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
        notebook_id TEXT NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
        created INTEGER NOT NULL,
        PRIMARY KEY (source_id, notebook_id)
    );
    CREATE INDEX idx_source_notebooks_notebook ON source_notebooks(notebook_id);
    CREATE TABLE notes (
        id TEXT PRIMARY KEY,
        title TEXT,
        content TEXT,
        note_type TEXT NOT NULL DEFAULT 'human',
        embedding BLOB,
        created INTEGER NOT NULL,
        updated INTEGER NOT NULL
    );
    CREATE TABLE note_notebooks (
        note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
        notebook_id TEXT NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
        created INTEGER NOT NULL,
        PRIMARY KEY (note_id, notebook_id)
    );
    CREATE INDEX idx_note_notebooks_notebook ON note_notebooks(notebook_id);
    CREATE TABLE chunks (
        id INTEGER PRIMARY KEY,
        source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
        ord INTEGER NOT NULL,
        content TEXT NOT NULL,
        embedding BLOB
    );
    CREATE INDEX idx_chunks_source ON chunks(source_id, ord);
    CREATE TABLE insights (
        id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
        insight_type TEXT NOT NULL,
        content TEXT NOT NULL,
        embedding BLOB,
        created INTEGER NOT NULL,
        updated INTEGER NOT NULL
    );
    CREATE INDEX idx_insights_source ON insights(source_id);
    CREATE TABLE chat_sessions (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('notebook', 'source')),
        target_id TEXT NOT NULL,
        title TEXT NOT NULL,
        model_override TEXT,
        created INTEGER NOT NULL,
        updated INTEGER NOT NULL
    );
    CREATE INDEX idx_chat_sessions_target ON chat_sessions(kind, target_id, updated);
    CREATE TABLE chat_messages (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
        seq INTEGER NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('human', 'ai')),
        content TEXT NOT NULL,
        created INTEGER NOT NULL
    );
    CREATE INDEX idx_chat_messages_session ON chat_messages(session_id, seq);
    CREATE TABLE jobs (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        status TEXT NOT NULL,
        args TEXT NOT NULL DEFAULT '{}',
        result TEXT,
        error TEXT,
        created INTEGER NOT NULL,
        updated INTEGER NOT NULL,
        started_at INTEGER,
        completed_at INTEGER
    );
    CREATE TABLE fts_rows (
        rowid INTEGER PRIMARY KEY,
        kind TEXT NOT NULL,
        item_id TEXT NOT NULL,
        parent_id TEXT NOT NULL,
        ref INTEGER
    );
    CREATE INDEX idx_fts_rows_item ON fts_rows(item_id);
    CREATE INDEX idx_fts_rows_parent ON fts_rows(parent_id);
    CREATE VIRTUAL TABLE search_fts USING fts5(tokens, tokenize = 'unicode61');
    """,
]


def _statements(script: str) -> list[str]:
    return [part.strip() for part in script.split(";") if part.strip()]


class Database:
    def __init__(self, path: pathlib.Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            pathlib.Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._connections: list[tuple[threading.Thread, sqlite3.Connection]] = []
        self._connections_lock = threading.Lock()
        # 向量写入版本号：仓储改动任何向量（含删来源/笔记/洞察）都加一，向量矩阵缓存据此失效
        self._vector_version = 0
        self._version_lock = threading.Lock()
        self.migrate()

    def connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False, timeout=30)
            conn.row_factory = sqlite3.Row
            for pragma in (
                "PRAGMA journal_mode=WAL",
                "PRAGMA synchronous=NORMAL",
                "PRAGMA busy_timeout=30000",
                "PRAGMA foreign_keys=ON",
                "PRAGMA temp_store=MEMORY",
                "PRAGMA cache_size=-16000",
            ):
                conn.execute(pragma)
            self._local.conn = conn
            with self._connections_lock:
                self._connections.append((threading.current_thread(), conn))
        return conn

    @contextlib.contextmanager
    def transaction(self):
        conn = self.connection()
        if conn.in_transaction:  # 嵌套调用：并进外层事务
            yield conn
            return
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")

    def migrate(self) -> None:
        conn = self.connection()
        with self.transaction():
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            for index in range(version, len(MIGRATIONS)):
                for statement in _statements(MIGRATIONS[index]):
                    conn.execute(statement)
            if version < len(MIGRATIONS):
                conn.execute(f"PRAGMA user_version = {len(MIGRATIONS)}")

    @property
    def vector_version(self) -> int:
        return self._vector_version

    def bump_vectors(self) -> None:
        with self._version_lock:
            self._vector_version += 1

    def ping(self) -> bool:
        try:
            self.connection().execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def close(self) -> None:
        """只关本线程和已经结束的线程的连接：别的线程可能还在用自己的连接（比如没跑完的后台任务），
        从外面关掉会让 sqlite 崩溃（实测段错误）。剩下的连接随线程结束被回收。"""
        me = threading.current_thread()
        with self._connections_lock:
            keep = []
            for thread, conn in self._connections:
                if thread is me or not thread.is_alive():
                    try:
                        conn.close()
                    except sqlite3.Error:
                        pass
                else:
                    keep.append((thread, conn))
            self._connections = keep
        self._local = threading.local()

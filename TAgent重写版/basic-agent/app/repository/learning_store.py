"""学习记录的持久化存储（SQLite）：答疑对话、论文批改、整卷作答与成绩。

为什么是 SQLite（选型与压测见 TAgent重写版/文档/数据库方案选型与压测报告.md）：
- 崩溃测试里已确认的写入零丢失、成批事务不会只进去半批；
- 就在应用进程里，单机读写比服务端库快 2~6 倍，不多一个要起、要守的服务；
- Python 自带，macOS / Windows / Linux 一样用，不依赖 Docker。

几条约定：
- **每个线程一个连接**（sqlite3 连接不能跨线程共用），WAL 模式下读写互不阻塞；
- **记录是尽力而为**：由调用方包一层 try/except（见 app/api/learner.py），存不进去只记日志，
  绝不能因此让答疑、批改失败；所以这里的忙等待也设得短（默认 2 秒），宁可丢一条记录也不卡住用户；
- 表结构用 PRAGMA user_version 记版本，启动时按顺序升级；
- 时间一律存毫秒时间戳（整数），JSON 一律存文本（SQLite 自带 JSON 函数能查）。
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def now_ms() -> int:
    return int(time.time() * 1000)


DAY_MS = 86_400_000
# 统计结果最多用这么久：本进程的写入会立刻让它作废，这个上限只防别的进程（导入脚本之类）写了库
STATS_MAX_AGE_S = 30.0
# 最多记住多少项：键里带着日期和学生编号（每个学生的记录各算一项，里面有整段回答），
# 不设上限的话后端连着跑一学期会越攒越多
STATS_MAX_ENTRIES = 256


class _StatsMemo:
    """管理后台读的东西（看板、按模型统计、全班概览、学生记录、反馈、库信息）记住结果，直到库里的记录有变化。

    统计一次要扫一段索引（一学期几万条记录时 5~40 毫秒），几个人同时开着看板、或者一个人来回切时间范围，
    每次都重算就会排队。全班概览、反馈列表单次虽只要一两毫秒，并发时却慢得不成比例（实测 50 路连发时
    概览从 1.8 毫秒涨到 500 毫秒）：SQLite 每取一行都放开一次 GIL 再抢回来，线程一多每次都要排队。
    这里按「本进程写过几次」记：版本号没变就直接给上次的结果——和重算出来的一模一样，不是「差不多」；
    同一项同时有几个请求，只算一次，其余的等它。
    """

    def __init__(
        self, *, max_age_s: float = STATS_MAX_AGE_S, max_entries: int = STATS_MAX_ENTRIES, clock=time.monotonic
    ):
        self.max_age_s = max_age_s
        self.max_entries = max_entries
        self._clock = clock
        self._lock = threading.Lock()
        self._key_locks: dict[tuple, threading.Lock] = {}
        self._entries: OrderedDict[tuple, tuple[int, float, Any]] = OrderedDict()
        self.version = 0

    def bump(self) -> None:
        with self._lock:
            self.version += 1

    def get(self, key: tuple, compute):
        with self._lock:
            key_lock = self._key_locks.setdefault(key, threading.Lock())
        with key_lock:
            with self._lock:
                version = self.version
                hit = self._entries.get(key)
                if hit is not None and hit[0] == version and self._clock() - hit[1] < self.max_age_s:
                    self._entries.move_to_end(key)
                    return hit[2]
            value = compute()
            with self._lock:
                # 算的过程中又有了写入，记下的是旧版本号，下一次自然重算
                self._entries[key] = (version, self._clock(), value)
                self._entries.move_to_end(key)
                while len(self._entries) > self.max_entries:
                    old, _ = self._entries.popitem(last=False)
                    self._key_locks.pop(old, None)
            return value


def _writes_records(method):
    """写学习记录的方法：写完（成不成都算）让记住的统计作废。"""

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        finally:
            self._stats.bump()

    return wrapper


def _memoized_stats(method):
    """按参数和今天的日期记住统计结果（过了午夜「最近 N 天」的窗口就挪了）。"""

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        key = (method.__name__, args, tuple(sorted(kwargs.items())), datetime.now().astimezone().date())
        return self._stats.get(key, lambda: method(self, *args, **kwargs))

    return wrapper


class _DayWindow:
    """最近 days 个自然日（本机时区）：起点、每天的标签，以及 SQL 里「这一行算哪一天」的写法。

    每天都正好 24 小时（窗口没跨夏令时切换，中国大陆一直如此）时直接拿毫秒数整除，
    不然才用 SQLite 的 'localtime' 换算——那个每一行都要调一次系统时区函数，3 万行要多花十几毫秒。
    """

    def __init__(self, days: int):
        today = datetime.now().astimezone().date()
        dates = [today - timedelta(days=offset) for offset in range(max(days, 1) - 1, -1, -1)]
        starts = [
            int(datetime(d.year, d.month, d.day).astimezone().timestamp() * 1000)
            for d in [*dates, today + timedelta(days=1)]
        ]
        self.since = starts[0]
        self.labels = [d.isoformat() for d in dates]
        self.uniform = all(later - earlier == DAY_MS for earlier, later in zip(starts, starts[1:]))

    def expr(self, column: str) -> str:
        if self.uniform:
            return f"(({column} - {self.since}) / {DAY_MS})"
        return f"date({column} / 1000, 'unixepoch', 'localtime')"

    def label(self, value) -> str | None:
        """SQL 里算出来的那一天 → 日期标签。窗口外的（时钟往回拨过）返回 None"""
        if not self.uniform:
            return value
        return self.labels[value] if isinstance(value, int) and 0 <= value < len(self.labels) else None


# 每一项是把库从 N-1 版升到 N 版的语句；只能往后追加，不能改已经发布的。
# 升级时按分号切成单条、包在一个事务里执行（失败整版回滚），所以语句和注释里都别出现分号。
MIGRATIONS: list[str] = [
    """
    CREATE TABLE students (
        id            TEXT PRIMARY KEY,           -- 前端生成的匿名设备编号
        name          TEXT NOT NULL DEFAULT '',   -- 学生在设置里填的昵称
        first_seen_at INTEGER NOT NULL,
        last_seen_at  INTEGER NOT NULL
    );

    CREATE TABLE chat_turns (
        id            INTEGER PRIMARY KEY,
        student_id    TEXT,                       -- 可空：没带编号的请求（脚本调用等）
        mode          TEXT NOT NULL,              -- qa | paper
        model         TEXT NOT NULL,
        question      TEXT NOT NULL,
        answer        TEXT NOT NULL,
        finish_reason TEXT,                       -- stop / length / interrupted / error
        notebook_ids  TEXT,                       -- JSON 数组
        duration_ms   INTEGER,
        created_at    INTEGER NOT NULL
    );
    CREATE INDEX idx_chat_student_time ON chat_turns (student_id, created_at);

    CREATE TABLE essay_reviews (
        id          INTEGER PRIMARY KEY,
        student_id  TEXT,
        model       TEXT NOT NULL,
        topic       TEXT,
        text        TEXT NOT NULL,
        score       INTEGER NOT NULL,
        review      TEXT NOT NULL,                -- 完整批改结果 JSON（维度、批注、总评）
        created_at  INTEGER NOT NULL
    );
    CREATE INDEX idx_essay_student_time ON essay_reviews (student_id, created_at);
    -- 学情统计（每人平均分）的覆盖索引：不建的话要逐行回表，压测里慢 37 倍
    CREATE INDEX idx_essay_student_score ON essay_reviews (student_id, score);

    CREATE TABLE exam_attempts (
        exam_id      TEXT PRIMARY KEY,
        student_id   TEXT,
        model        TEXT NOT NULL,
        title        TEXT NOT NULL DEFAULT '',
        topic        TEXT,
        total_points INTEGER,
        paper        TEXT,                        -- JSON：发给学生的卷面（不含答案）
        score        INTEGER,                     -- 交卷前为空
        answers      TEXT,                        -- JSON，交卷后才有
        review       TEXT,                        -- JSON，交卷后才有
        created_at   INTEGER NOT NULL,
        reviewed_at  INTEGER
    );
    CREATE INDEX idx_exam_student_time ON exam_attempts (student_id, created_at);
    CREATE INDEX idx_exam_student_score ON exam_attempts (student_id, score, total_points);
    """,
    # 第 2 版：出好的私有卷（含答案与评分规则）也落一份盘。以前只在内存里，
    # basic-agent 一重启（崩溃、演示时重跑启动脚本）学生交卷就是「试卷不存在或已过期」，答案白写
    """
    CREATE TABLE exam_cache (
        exam_id         TEXT PRIMARY KEY,
        served_model_id TEXT NOT NULL,              -- 出卷模型：判卷必须用同一个
        exam            TEXT NOT NULL,              -- 私有卷 JSON（含答案，只在服务端）
        expires_at      INTEGER NOT NULL            -- 毫秒时间戳，和内存缓存同一个有效期
    );
    CREATE INDEX idx_exam_cache_expiry ON exam_cache (expires_at);
    """,
    # 第 3 版：学生对回答的赞 / 踩（以前只存在页面内存里，刷新就没了，老师也看不到），
    # 外加按时间范围统计用的索引：管理后台的看板、按模型统计都是「最近 N 天」，
    # 原来的索引都以学生编号打头，按时间筛只能整表扫。统计要用的列都放进索引（覆盖索引）：
    # 不然每一行都要回表，答疑记录里带着整段回答，一学期 3 万条时看板一次要 50~130 毫秒，有了它 5~20 毫秒
    """
    CREATE TABLE feedback (
        id          INTEGER PRIMARY KEY,
        student_id  TEXT,
        message_key TEXT NOT NULL,                -- 前端那条回答的编号：同一条改评价是覆盖，不是再加一条
        model       TEXT NOT NULL,
        mode        TEXT NOT NULL,                -- qa | paper | chat
        rating      INTEGER NOT NULL,             -- 1 有帮助 / -1 没有帮助
        question    TEXT NOT NULL,
        answer      TEXT NOT NULL,
        created_at  INTEGER NOT NULL,
        updated_at  INTEGER NOT NULL
    );
    CREATE UNIQUE INDEX idx_feedback_message ON feedback (student_id, message_key);
    CREATE INDEX idx_feedback_time ON feedback (updated_at, model, rating);
    CREATE INDEX idx_chat_time ON chat_turns (created_at, mode, student_id, model, finish_reason, duration_ms);
    CREATE INDEX idx_essay_time ON essay_reviews (created_at, student_id, model, score);
    CREATE INDEX idx_exam_time ON exam_attempts (created_at, student_id, model, score, total_points);
    CREATE INDEX idx_exam_reviewed ON exam_attempts (reviewed_at, student_id);
    DROP INDEX idx_chat_student_time;
    CREATE INDEX idx_chat_student_time ON chat_turns (student_id, created_at, mode);
    """,
]


class LearningStore:
    def __init__(self, path: str | Path, *, busy_timeout_ms: int = 2000, backup_keep: int = 7):
        self.path = Path(path)
        self.busy_timeout_ms = busy_timeout_ms
        self.backup_keep = backup_keep
        self.backup_dir = self.path.parent / "backups"
        self._local = threading.local()
        self._backup_thread: threading.Thread | None = None
        self._backup_lock = threading.Lock()
        self._stop = threading.Event()
        self._stats = _StatsMemo()

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate(self._conn())

    # ====================== 连接 ======================
    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                self.path,
                timeout=self.busy_timeout_ms / 1000,
                isolation_level=None,  # 自动提交；成组写入自己包 BEGIN/COMMIT
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            for pragma in (
                "PRAGMA journal_mode=WAL",
                # WAL 下的推荐配置：进程崩溃不丢已提交的数据（压测实测）；断电可能丢最后几次提交
                "PRAGMA synchronous=NORMAL",
                f"PRAGMA busy_timeout={self.busy_timeout_ms}",
                # 默认页缓存只有 2 MB，库一大随机读几乎次次读文件（macOS 上慢 20 倍）。
                # 主要靠 mmap（各连接共享系统的文件缓存，不重复占内存）；页缓存是每个连接
                # 各一份的，服务有几十个线程，所以只给 16 MB，不照搬压测里单连接的 64 MB。
                "PRAGMA mmap_size=268435456",
                "PRAGMA cache_size=-16384",
                "PRAGMA temp_store=MEMORY",
                "PRAGMA foreign_keys=ON",
            ):
                conn.execute(pragma)
            self._local.conn = conn
        return conn

    def _migrate(self, conn: sqlite3.Connection) -> None:
        if conn.execute("PRAGMA user_version").fetchone()[0] >= len(MIGRATIONS):
            return  # 已是最新：不必去抢写锁
        # 拿到写锁之后**再读一次**版本：两个进程同时打开一个新库时，后到的那个要等前一个
        # 建完表，这时版本已经变了；照着锁外读到的旧版本再建一遍表只会报「表已存在」
        conn.execute("BEGIN IMMEDIATE")
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            for target, script in enumerate(MIGRATIONS[version:], start=version + 1):
                for statement in (s.strip() for s in script.split(";")):
                    if statement:
                        conn.execute(statement)
                conn.execute(f"PRAGMA user_version={target}")
                log.info("学习记录库升级到第 %s 版：%s", target, self.path)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    @property
    def schema_version(self) -> int:
        return self._conn().execute("PRAGMA user_version").fetchone()[0]

    # ====================== 写 ======================
    @_writes_records
    def touch_student(self, student_id: str, name: str = "") -> None:
        at = now_ms()
        self._conn().execute(
            "INSERT INTO students (id, name, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET last_seen_at = excluded.last_seen_at, "
            "name = CASE WHEN excluded.name <> '' THEN excluded.name ELSE students.name END",
            (student_id, name, at, at),
        )

    @_writes_records
    def record_chat(
        self,
        *,
        student_id: str | None,
        mode: str,
        model: str,
        question: str,
        answer: str,
        finish_reason: str | None = None,
        notebook_ids: list[str] | None = None,
        duration_ms: int | None = None,
    ) -> int:
        cur = self._conn().execute(
            "INSERT INTO chat_turns (student_id, mode, model, question, answer, finish_reason, notebook_ids, "
            "duration_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (student_id, mode, model, question, answer, finish_reason,
             json.dumps(notebook_ids or [], ensure_ascii=False), duration_ms, now_ms()),
        )
        return cur.lastrowid

    @_writes_records
    def record_essay_review(
        self, *, student_id: str | None, model: str, topic: str | None, text: str, review: dict[str, Any]
    ) -> int:
        cur = self._conn().execute(
            "INSERT INTO essay_reviews (student_id, model, topic, text, score, review, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (student_id, model, topic, text, int(review.get("score", 0)),
             json.dumps(review, ensure_ascii=False), now_ms()),
        )
        return cur.lastrowid

    @_writes_records
    def record_exam_generated(
        self,
        *,
        student_id: str | None,
        exam_id: str,
        model: str,
        title: str,
        topic: str | None,
        total_points: int | None,
        paper: dict[str, Any] | None = None,
    ) -> None:
        self._conn().execute(
            "INSERT INTO exam_attempts (exam_id, student_id, model, title, topic, total_points, paper, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(exam_id) DO NOTHING",
            (exam_id, student_id, model, title, topic, total_points,
             json.dumps(paper, ensure_ascii=False) if paper is not None else None, now_ms()),
        )

    @_writes_records
    def record_exam_reviewed(
        self,
        *,
        student_id: str | None,
        exam_id: str,
        model: str,
        answers: dict[str, Any],
        review: dict[str, Any],
    ) -> None:
        """交卷结果。出卷那条没记上（比如当时库不可用）也能补一条完整的。"""
        at = now_ms()
        self._conn().execute(
            "INSERT INTO exam_attempts (exam_id, student_id, model, title, total_points, score, answers, review, "
            "created_at, reviewed_at) VALUES (?, ?, ?, '', ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(exam_id) DO UPDATE SET score = excluded.score, answers = excluded.answers, "
            "review = excluded.review, total_points = excluded.total_points, reviewed_at = excluded.reviewed_at, "
            "student_id = COALESCE(exam_attempts.student_id, excluded.student_id)",
            (exam_id, student_id, model, review.get("total_points"), review.get("total_score"),
             json.dumps(answers, ensure_ascii=False), json.dumps(review, ensure_ascii=False), at, at),
        )

    # ====================== 出好的私有卷（重启后还能交卷） ======================
    @_writes_records
    def save_cached_exam(self, exam_id: str, served_model_id: str, exam_json: str, expires_at_ms: int) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO exam_cache (exam_id, served_model_id, exam, expires_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(exam_id) DO UPDATE SET served_model_id = excluded.served_model_id, "
            "exam = excluded.exam, expires_at = excluded.expires_at",
            (exam_id, served_model_id, exam_json, expires_at_ms),
        )
        conn.execute("DELETE FROM exam_cache WHERE expires_at <= ?", (now_ms(),))  # 顺手清掉过期的

    def load_cached_exam(self, exam_id: str) -> tuple[str, str, int] | None:
        """(出卷模型, 私有卷 JSON, 过期时刻)；没有或已过期返回 None。"""
        row = self._conn().execute(
            "SELECT served_model_id, exam, expires_at FROM exam_cache WHERE exam_id = ? AND expires_at > ?",
            (exam_id, now_ms()),
        ).fetchone()
        return (row["served_model_id"], row["exam"], row["expires_at"]) if row else None

    # ====================== 读（老师看学情） ======================
    @_memoized_stats
    def summary(self, limit: int = 500) -> dict[str, Any]:
        conn = self._conn()
        totals = conn.execute(
            "SELECT (SELECT COUNT(*) FROM students) AS students, (SELECT COUNT(*) FROM chat_turns) AS chat_turns, "
            "(SELECT COUNT(*) FROM essay_reviews) AS essay_reviews, "
            "(SELECT COUNT(*) FROM exam_attempts WHERE score IS NOT NULL) AS exams_reviewed"
        ).fetchone()
        rows = conn.execute(
            """
            SELECT s.id, s.name, s.first_seen_at, s.last_seen_at,
                   (SELECT COUNT(*) FROM chat_turns c WHERE c.student_id = s.id) AS chat_turns,
                   (SELECT COUNT(*) FROM essay_reviews e WHERE e.student_id = s.id) AS essay_reviews,
                   (SELECT ROUND(AVG(score), 1) FROM essay_reviews e WHERE e.student_id = s.id) AS essay_avg,
                   (SELECT COUNT(*) FROM exam_attempts x WHERE x.student_id = s.id AND x.score IS NOT NULL) AS exams_reviewed,
                   (SELECT ROUND(AVG(score * 100.0 / total_points), 1) FROM exam_attempts x
                     WHERE x.student_id = s.id AND x.score IS NOT NULL AND x.total_points > 0) AS exam_avg_percent
            FROM students s ORDER BY s.last_seen_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return {"totals": dict(totals), "students": [dict(r) for r in rows]}

    @_memoized_stats
    def student_timeline(self, student_id: str, limit: int = 50) -> dict[str, Any]:
        conn = self._conn()
        student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        chats = conn.execute(
            "SELECT id, mode, model, question, answer, finish_reason, duration_ms, created_at FROM chat_turns "
            "WHERE student_id = ? ORDER BY created_at DESC LIMIT ?", (student_id, limit)).fetchall()
        essays = conn.execute(
            "SELECT id, model, topic, text, score, review, created_at FROM essay_reviews "
            "WHERE student_id = ? ORDER BY created_at DESC LIMIT ?", (student_id, limit)).fetchall()
        exams = conn.execute(
            "SELECT exam_id, model, title, topic, total_points, paper, score, answers, review, created_at, reviewed_at "
            "FROM exam_attempts WHERE student_id = ? ORDER BY created_at DESC LIMIT ?", (student_id, limit)).fetchall()

        def decode(row, *fields):
            item = dict(row)
            for field in fields:
                if item.get(field):
                    item[field] = json.loads(item[field])
            return item

        return {
            "student": dict(student) if student else None,
            "chat_turns": [dict(r) for r in chats],
            "essay_reviews": [decode(r, "review") for r in essays],
            "exam_attempts": [decode(r, "paper", "answers", "review") for r in exams],
        }

    # ====================== 赞 / 踩 ======================
    @_writes_records
    def record_feedback(
        self,
        *,
        student_id: str,
        message_key: str,
        model: str,
        mode: str,
        rating: int,
        question: str,
        answer: str,
    ) -> None:
        """rating 为 0 表示撤销（再点一次同一个按钮），删掉那一条；同一条回答改评价是覆盖。"""
        conn = self._conn()
        if rating == 0:
            conn.execute(
                "DELETE FROM feedback WHERE student_id = ? AND message_key = ?", (student_id, message_key)
            )
            return
        at = now_ms()
        conn.execute(
            "INSERT INTO feedback (student_id, message_key, model, mode, rating, question, answer, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(student_id, message_key) DO UPDATE SET rating = excluded.rating, model = excluded.model, "
            "mode = excluded.mode, question = excluded.question, answer = excluded.answer, updated_at = excluded.updated_at",
            (student_id, message_key, model, mode, rating, question, answer, at, at),
        )

    @_memoized_stats
    def feedback_list(self, *, limit: int = 100, rating: int | None = None) -> list[dict[str, Any]]:
        sql = (
            "SELECT f.id, f.student_id, s.name AS student_name, f.model, f.mode, f.rating, f.question, f.answer, "
            "f.created_at, f.updated_at FROM feedback f LEFT JOIN students s ON s.id = f.student_id"
        )
        params: list[Any] = []
        if rating is not None:
            sql += " WHERE f.rating = ?"
            params.append(rating)
        sql += " ORDER BY f.updated_at DESC LIMIT ?"
        params.append(limit)
        return [dict(row) for row in self._conn().execute(sql, params).fetchall()]

    @_writes_records
    def delete_feedback(self, feedback_id: int) -> bool:
        """老师删掉一条（比如演示时自己点的）。返回有没有这一条。"""
        return self._conn().execute("DELETE FROM feedback WHERE id = ?", (feedback_id,)).rowcount > 0

    # ====================== 管理后台的统计 ======================
    @_memoized_stats
    def analytics(self, *, days: int = 14) -> dict[str, Any]:
        """最近 days 天（按本机时区的自然日）：每天的答疑 / 批改 / 出卷 / 交卷量和活跃学生数。

        「答疑量」只算课程答疑和论文助手；Playground 里直接和模型聊的（mode = chat）单独在 chat_modes 里。
        「活跃」= 那天有过答疑、批改、出卷或交卷。
        """
        conn = self._conn()
        window = _DayWindow(days)
        since = window.since
        created, reviewed = window.expr("created_at"), window.expr("reviewed_at")
        series: dict[str, dict[str, int]] = {}

        def add(rows, field):
            for row in rows:
                label = window.label(row["day"])
                if label is not None:
                    series.setdefault(label, {})[field] = row["n"]

        # 每天的答疑量和各场景的总数一趟扫出来（同一段索引，分两句就要扫两遍）
        modes: dict[str, int] = {}
        for row in conn.execute(f"SELECT {created} AS day, mode, COUNT(*) AS n FROM chat_turns WHERE created_at >= ? "
                                "GROUP BY day, mode", (since,)):
            modes[row["mode"]] = modes.get(row["mode"], 0) + row["n"]
            label = window.label(row["day"])
            if row["mode"] != "chat" and label is not None:
                bucket = series.setdefault(label, {})
                bucket["chat_turns"] = bucket.get("chat_turns", 0) + row["n"]
        add(conn.execute(f"SELECT {created} AS day, COUNT(*) AS n FROM essay_reviews WHERE created_at >= ? GROUP BY day",
                         (since,)), "essay_reviews")
        add(conn.execute(f"SELECT {created} AS day, COUNT(*) AS n FROM exam_attempts WHERE created_at >= ? GROUP BY day",
                         (since,)), "exams_generated")
        add(conn.execute(f"SELECT {reviewed} AS day, COUNT(*) AS n FROM exam_attempts WHERE reviewed_at >= ? GROUP BY day",
                         (since,)), "exams_reviewed")
        add(conn.execute(
            f"SELECT day, COUNT(DISTINCT student_id) AS n FROM ("
            f"SELECT {created} AS day, student_id FROM chat_turns WHERE created_at >= ? AND mode <> 'chat' "
            f"AND student_id IS NOT NULL "
            f"UNION ALL SELECT {created}, student_id FROM essay_reviews WHERE created_at >= ? AND student_id IS NOT NULL "
            f"UNION ALL SELECT {created}, student_id FROM exam_attempts WHERE created_at >= ? AND student_id IS NOT NULL "
            f"UNION ALL SELECT {reviewed}, student_id FROM exam_attempts WHERE reviewed_at >= ? AND student_id IS NOT NULL"
            ") GROUP BY day", (since, since, since, since)), "active_students")

        fields = ("chat_turns", "essay_reviews", "exams_generated", "exams_reviewed", "active_students")
        daily = [
            {"day": label, **{field: series.get(label, {}).get(field, 0) for field in fields}}
            for label in window.labels
        ]
        active, students = self._active_students(since)
        return {
            "days": days,
            "daily": daily,
            "totals": {field: sum(item[field] for item in daily) for field in fields[:4]},
            "chat_modes": modes,
            "active_students": active,
            "students": students,
        }

    def _active_students(self, since: int, limit: int = 50) -> tuple[int, list[dict[str, Any]]]:
        """窗口里活跃的学生数（口径同 analytics），和其中最活跃的 limit 个：各自的答疑、批改、交卷次数，按总数从多到少。"""
        conn = self._conn()
        counts: dict[str, dict[str, int]] = {}
        for field, sql in (
            ("chat_turns", "SELECT student_id, COUNT(*) AS n FROM chat_turns WHERE created_at >= ? "
                           "AND mode <> 'chat' AND student_id IS NOT NULL GROUP BY student_id"),
            ("essay_reviews", "SELECT student_id, COUNT(*) AS n FROM essay_reviews WHERE created_at >= ? "
                              "AND student_id IS NOT NULL GROUP BY student_id"),
            ("exams_generated", "SELECT student_id, COUNT(*) AS n FROM exam_attempts WHERE created_at >= ? "
                                "AND student_id IS NOT NULL GROUP BY student_id"),
            ("exams_reviewed", "SELECT student_id, COUNT(*) AS n FROM exam_attempts WHERE reviewed_at >= ? "
                               "AND student_id IS NOT NULL GROUP BY student_id"),
        ):
            for row in conn.execute(sql, (since,)):
                counts.setdefault(row["student_id"], {})[field] = row["n"]
        fields = ("chat_turns", "essay_reviews", "exams_reviewed")
        ranked = sorted(
            counts.items(), key=lambda item: sum(item[1].get(field, 0) for field in fields), reverse=True
        )[:limit]
        names = {
            row["id"]: row["name"]
            for row in conn.execute(
                f"SELECT id, name FROM students WHERE id IN ({', '.join('?' * len(ranked))})",
                [student_id for student_id, _ in ranked],
            )
        } if ranked else {}
        return len(counts), [
            {
                "id": student_id,
                "name": names.get(student_id, ""),
                **{field: values.get(field, 0) for field in fields},
            }
            for student_id, values in ranked
        ]

    @_memoized_stats
    def model_activity(self, model: str, *, days: int = 30) -> dict[str, Any]:
        """一个模型最近 days 天每天的答疑量和赞 / 踩，以及它被用在哪些场景（答疑 / 论文 / Playground）。"""
        conn = self._conn()
        window = _DayWindow(days)
        since = window.since
        series: dict[str, dict[str, int]] = {}
        for row in conn.execute(
            f"SELECT {window.expr('created_at')} AS day, COUNT(*) AS n FROM chat_turns "
            "WHERE created_at >= ? AND model = ? GROUP BY day", (since, model)):
            if (label := window.label(row["day"])) is not None:
                series.setdefault(label, {})["chat_turns"] = row["n"]
        for row in conn.execute(
            f"SELECT {window.expr('updated_at')} AS day, "
            "SUM(CASE WHEN rating > 0 THEN 1 ELSE 0 END) AS up, SUM(CASE WHEN rating < 0 THEN 1 ELSE 0 END) AS down "
            "FROM feedback WHERE updated_at >= ? AND model = ? GROUP BY day", (since, model)):
            if (label := window.label(row["day"])) is not None:
                series.setdefault(label, {}).update(thumbs_up=row["up"], thumbs_down=row["down"])
        fields = ("chat_turns", "thumbs_up", "thumbs_down")
        modes = conn.execute(
            "SELECT mode, COUNT(*) AS n FROM chat_turns WHERE created_at >= ? AND model = ? GROUP BY mode",
            (since, model),
        ).fetchall()
        return {
            "model": model,
            "days": days,
            "daily": [
                {"day": label, **{field: series.get(label, {}).get(field, 0) for field in fields}}
                for label in window.labels
            ],
            "chat_modes": {row["mode"]: row["n"] for row in modes},
        }

    @_memoized_stats
    def model_stats(self, *, days: int | None = None) -> list[dict[str, Any]]:
        """按模型统计：答疑量、平均耗时、答完率、赞踩、批改与整卷平均分。days 为空时统计全部记录。"""
        conn = self._conn()
        since = _DayWindow(days).since if days else 0
        models: dict[str, dict[str, Any]] = {}

        def merge(rows):
            for row in rows:
                item = dict(row)
                models.setdefault(item.pop("model"), {}).update(item)

        merge(conn.execute(
            "SELECT model, COUNT(*) AS chat_turns, ROUND(AVG(duration_ms)) AS avg_duration_ms, "
            "SUM(CASE WHEN finish_reason = 'stop' THEN 1 ELSE 0 END) AS completed, "
            "SUM(CASE WHEN finish_reason IN ('interrupted', 'error') THEN 1 ELSE 0 END) AS interrupted "
            "FROM chat_turns WHERE created_at >= ? GROUP BY model", (since,)))
        merge(conn.execute(
            "SELECT model, COUNT(*) AS essay_reviews, ROUND(AVG(score), 1) AS essay_avg "
            "FROM essay_reviews WHERE created_at >= ? GROUP BY model", (since,)))
        merge(conn.execute(
            "SELECT model, COUNT(*) AS exams_reviewed, ROUND(AVG(score * 100.0 / total_points), 1) AS exam_avg_percent "
            "FROM exam_attempts WHERE score IS NOT NULL AND total_points > 0 AND created_at >= ? GROUP BY model",
            (since,)))
        merge(conn.execute(
            "SELECT model, SUM(CASE WHEN rating > 0 THEN 1 ELSE 0 END) AS thumbs_up, "
            "SUM(CASE WHEN rating < 0 THEN 1 ELSE 0 END) AS thumbs_down "
            "FROM feedback WHERE updated_at >= ? GROUP BY model", (since,)))

        zero = {"chat_turns": 0, "avg_duration_ms": None, "completed": 0, "interrupted": 0, "essay_reviews": 0,
                "essay_avg": None, "exams_reviewed": 0, "exam_avg_percent": None, "thumbs_up": 0, "thumbs_down": 0}
        rows = [{"model": model, **zero, **values} for model, values in models.items()]
        for row in rows:
            row["completion_rate"] = round(row["completed"] / row["chat_turns"], 3) if row["chat_turns"] else None
            votes = row["thumbs_up"] + row["thumbs_down"]
            row["thumbs_up_rate"] = round(row["thumbs_up"] / votes, 3) if votes else None
        rows.sort(key=lambda row: (row["chat_turns"] + row["essay_reviews"] + row["exams_reviewed"]), reverse=True)
        return rows

    @_memoized_stats
    def db_info(self) -> dict[str, Any]:
        """库文件、大小、各表条数和现有备份，给管理后台的「数据库」页。"""
        conn = self._conn()
        tables = ("students", "chat_turns", "essay_reviews", "exam_attempts", "exam_cache", "feedback")
        counts = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}

        def size(path: Path) -> int:
            try:
                return path.stat().st_size
            except OSError:
                return 0

        def modified_ms(path: Path) -> int | None:
            try:
                return int(path.stat().st_mtime * 1000)
            except OSError:  # 刚好被轮换删掉了
                return None

        wal = self.path.with_name(self.path.name + "-wal")
        backups = [
            {"file": item.name, "bytes": size(item), "modified_at": modified}
            for item in sorted(self.backup_dir.glob("tagent-*.sqlite3"), reverse=True)
            if (modified := modified_ms(item)) is not None
        ] if self.backup_dir.exists() else []
        return {
            "path": str(self.path),
            "bytes": size(self.path) + size(wal),
            "schema_version": self.schema_version,
            "tables": counts,
            "backups": backups,
            "backup_keep": self.backup_keep,
        }

    # ====================== 备份 ======================
    @_writes_records
    def backup(self) -> Path:
        """在线备份：不停服务、不挡写入（100 万条约 1.6 秒）。只保留最近 backup_keep 份。

        - 同一时刻只跑一份（老师手动备份撞上每日自动备份时排队，不会两边写同一个文件）；
        - 先写到唯一的临时文件，写完整了才改名，备份目录里不会出现半截的 .sqlite3；
          写失败就把临时文件删掉，不留垃圾；
        - 文件名用 UTC 时间：按名字排序就是按时间排序，夏令时回拨也不会乱序。
        """
        with self._backup_lock:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            target = self.backup_dir / f"tagent-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}.sqlite3"
            partial = self.backup_dir / f".{target.stem}.{os.getpid()}.{threading.get_ident()}.partial"
            try:
                dest = sqlite3.connect(partial)
                try:
                    self._conn().backup(dest)
                finally:
                    dest.close()
                os.replace(partial, target)
            except BaseException:
                partial.unlink(missing_ok=True)
                raise
            for old in sorted(self.backup_dir.glob("tagent-*.sqlite3"))[: -self.backup_keep]:
                old.unlink(missing_ok=True)
            return target

    def latest_backup_age_s(self) -> float | None:
        backups = sorted(self.backup_dir.glob("tagent-*.sqlite3"))
        return (time.time() - backups[-1].stat().st_mtime) if backups else None

    def start_daily_backup(self, *, every_s: float = 86_400, check_s: float = 3600) -> None:
        """后台线程：距上次备份满一天就备一份。进程刚起来时若从没备份过，也会先备一份。"""
        if self._backup_thread is not None:
            return

        def loop():
            while not self._stop.is_set():
                try:
                    age = self.latest_backup_age_s()
                    if age is None or age >= every_s:
                        log.info("学习记录已备份：%s", self.backup())
                except Exception as exc:  # noqa: BLE001 —— 备份失败不能拖垮服务
                    log.warning("学习记录备份失败：%s", exc)
                self._stop.wait(check_s)

        self._backup_thread = threading.Thread(target=loop, name="learning-store-backup", daemon=True)
        self._backup_thread.start()

    def close(self) -> None:
        self._stop.set()
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

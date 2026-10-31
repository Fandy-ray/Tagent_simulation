"""试卷缓存与并发闸门。

纯标准库实现，不依赖 LLM/langchain，可离线单测。
内存里放一份（判卷时读得快）；给了 persistence 就再落一份盘（见 app/repository/exam_persistence.py），
basic-agent 重启后内存没了，交卷时去盘上找回来，学生不用重新出卷。
"""

from __future__ import annotations

import copy
import math
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, Tuple

from app.errors.exam_errors import ExamBusyError, ExamGoneError


@dataclass(frozen=True)
class StoredExam:
    """缓存中的私有试卷及其锁定模型；不保存 provider 凭据。"""

    exam: Any
    served_model_id: str


# ====================== 内存缓存 ======================
class ExamCache:
    """monotonic TTL + 容量上限；锁只包围缓存操作，读取在锁内深拷贝后立即释放。"""

    def __init__(
        self,
        ttl_seconds: float = 7200.0,
        max_items: int = 200,
        clock: Callable[[], float] = time.monotonic,
        persistence: Any = None,
    ):
        self._ttl = ttl_seconds
        self._max_items = max_items
        self._clock = clock
        # 有 save(exam_id, exam, ttl_seconds) / load(exam_id) -> (exam, 剩余秒数) | None 就行；None = 只在内存
        self._persistence = persistence
        self._lock = threading.Lock()
        # exam_id -> (过期时刻, 试卷对象)；dict 保持插入序，最旧在前
        self._items: Dict[str, Tuple[float, Any]] = {}

    def _cleanup_locked(self) -> None:
        now = self._clock()
        expired = [k for k, (deadline, _) in self._items.items() if deadline <= now]
        for k in expired:
            del self._items[k]

    def put(self, exam_id: str, exam: Any) -> None:
        with self._lock:
            self._cleanup_locked()
            while len(self._items) >= self._max_items:
                oldest = next(iter(self._items))
                del self._items[oldest]
            self._items[exam_id] = (self._clock() + self._ttl, exam)
        if self._persistence is not None:
            self._persistence.save(exam_id, exam, self._ttl)  # 尽力而为，内部出错只记日志

    def get_copy(self, exam_id: str) -> Any:
        """返回深拷贝；不存在/过期抛 ExamGoneError。拷贝在锁内完成，判分在锁外进行。"""
        with self._lock:
            self._cleanup_locked()
            entry = self._items.get(exam_id)
            if entry is not None:
                return copy.deepcopy(entry[1])
        # 内存里没有（多半是重启过）：去盘上找。读盘放在锁外，别让一次磁盘 IO 挡住别人判卷
        found = self._persistence.load(exam_id) if self._persistence is not None else None
        if found is None:
            raise ExamGoneError("试卷不存在或已过期，请重新生成")
        exam, seconds_left = found
        with self._lock:
            self._items[exam_id] = (self._clock() + seconds_left, exam)
            return copy.deepcopy(exam)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


# ====================== 并发闸门 ======================
class LLMGate:
    """全局闸门：同时压在上游的 LLM 调用（出卷、判卷、批改、批注、出题）不超过 max_concurrent。

    满了先排一会儿队：最多 wait_seconds 秒、最多 max_waiting 个人排着，排不上才 429。
    以前满了立刻 429 —— 一个班同时交稿，6 个人里 4 个直接报「请求过多」（压测 S2），只能自己再点一次。
    排队的人占着一个 waitress 线程干等，所以队长有上限（见 app/config.py 的 LLM_GATE_*、WAITRESS_THREADS）；
    排队算在这次运行的预算里，后端总耗时不超过预算（见 tests/test_timeout_budgets.py）。

    默认 wait_seconds=0：不排队、满了立刻 429（单测和老的调用方式照旧）。正式装配见 app/container.py。

    acquire 给了 deadline（这次运行的截止时间，排队也算在里面）时，最多排到「截止前还留 min_run_seconds」：
    排得再久，排到了也来不及跑完，不如早点告诉学生。答疑也用这个类（busy_error 换成答疑自己的说法）。
    """

    def __init__(
        self,
        max_concurrent: int = 2,
        *,
        wait_seconds: float = 0.0,
        max_waiting: int = 0,
        min_run_seconds: float = 20.0,
        busy_error: Callable[[str], Exception] = ExamBusyError,
        what: str = "批改 / 出题",
    ):
        self._sem = threading.BoundedSemaphore(max_concurrent)
        self._wait_seconds = wait_seconds
        self._max_waiting = max_waiting
        self._min_run_seconds = min_run_seconds
        self._busy_error = busy_error
        self._what = what
        self._waiting = 0
        self._lock = threading.Lock()

    @property
    def waiting(self) -> int:
        with self._lock:
            return self._waiting

    @contextmanager
    def acquire(self, *, deadline: float | None = None):
        if not self._sem.acquire(blocking=False):
            self._queue_for_a_slot(deadline)
        try:
            yield
        finally:
            self._sem.release()

    def _queue_for_a_slot(self, deadline: float | None) -> None:
        wait = self._wait_seconds
        if deadline is not None and math.isfinite(deadline):
            wait = min(wait, deadline - time.monotonic() - self._min_run_seconds)
        with self._lock:
            if wait <= 0 or self._waiting >= self._max_waiting:
                raise self._busy_error(f"同时在{self._what}的人太多，请稍后再试")
            self._waiting += 1
        try:
            got = self._sem.acquire(timeout=wait)
        finally:
            with self._lock:
                self._waiting -= 1
        if not got:
            raise self._busy_error(f"同时在{self._what}的人太多，排了 {wait:.0f} 秒还没轮到，请稍后再试")

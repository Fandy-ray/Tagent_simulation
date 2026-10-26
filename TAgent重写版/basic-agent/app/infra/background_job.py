"""要跑几秒到几分钟的一次性任务（重建索引、补参考文献）：接口立刻返回，任务在后台线程里跑，页面轮询状态。

- 同一种任务同一时刻只跑一个：已经在跑时再点一次，返回「已在进行」，不会叠出第二个；
- 任务函数返回一句话当结果说明，抛异常就记成失败（异常的那句话给页面看）；
- 纯标准库，可离线单测（时钟和起线程的方式都能注入）。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional


log = logging.getLogger(__name__)


class BackgroundJob:
    def __init__(
        self,
        name: str,
        *,
        clock: Optional[Callable[[], float]] = None,
        spawn: Optional[Callable[[Callable[[], None]], None]] = None,
    ):
        self.name = name
        self._clock = clock or time.time
        self._spawn = spawn or self._spawn_thread
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {"status": "idle", "started_at": None, "finished_at": None, "message": ""}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def start(self, task: Callable[[], str]) -> bool:
        """开始跑；已经在跑就返回 False、什么也不做。"""
        with self._lock:
            if self._state["status"] == "running":
                return False
            self._state = {"status": "running", "started_at": self._ms(), "finished_at": None, "message": ""}

        def run():
            try:
                message = task()
            except Exception as exc:  # noqa: BLE001 —— 后台任务出错只记下来给页面看，不能把线程带崩
                log.warning("后台任务 %s 失败：%s", self.name, exc)
                outcome = {"status": "failed", "message": str(exc) or type(exc).__name__}
            else:
                outcome = {"status": "succeeded", "message": message or ""}
            with self._lock:
                self._state = {**self._state, **outcome, "finished_at": self._ms()}

        try:
            self._spawn(run)
        except Exception as exc:  # noqa: BLE001
            # 起不来线程（资源耗尽之类）时不能一直挂着「进行中」，否则这个按钮再也点不动
            log.warning("后台任务 %s 没能开始：%s", self.name, exc)
            with self._lock:
                self._state = {**self._state, "status": "failed", "message": f"没能开始：{exc}",
                               "finished_at": self._ms()}
            return False
        return True

    def _ms(self) -> int:
        return int(self._clock() * 1000)

    @staticmethod
    def _spawn_thread(task: Callable[[], None]) -> None:
        threading.Thread(target=task, daemon=True).start()

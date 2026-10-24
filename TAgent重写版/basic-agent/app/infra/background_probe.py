"""后台探活：接口立刻拿缓存值，探测在别的线程里做。

/knowledge 原先每次请求都同步 ping 一次 OpenNotebook。连得上时还好，
**断连时一次请求要等 15~20 秒**——而这是个前端每次打开答疑页都会调的接口，
它本身不调模型，本不该有任何可感知的延迟。

所以：
- 读永远不阻塞，拿到的是上一次探测的结果；
- 过期了就**顺手**丢一个后台线程去刷新，当前这次请求照常立刻返回；
- 同一时刻只允许一个探测在跑，断连时不会把线程池堆满。

纯标准库，可离线单测（时钟和探测函数都能注入）。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional


log = logging.getLogger(__name__)


class BackgroundProbe:
    def __init__(
        self,
        probe: Callable[[], bool],
        *,
        ttl_seconds: float = 30.0,
        clock: Optional[Callable[[], float]] = None,
        spawn: Optional[Callable[[Callable[[], None]], None]] = None,
    ):
        self._probe = probe
        self._ttl = ttl_seconds
        self._clock = clock or time.monotonic
        self._spawn = spawn or self._spawn_thread
        self._lock = threading.Lock()
        self._value: Optional[bool] = None
        self._checked_at: Optional[float] = None
        self._running = False

    @staticmethod
    def _spawn_thread(work: Callable[[], None]) -> None:
        threading.Thread(target=work, daemon=True).start()

    def value(self) -> Optional[bool]:
        """立刻返回上一次的结果；过期就后台刷新。从不阻塞。

        第一次调用必然返回 None（还没探过）——前端把 None 当作「未知」显示，
        比让它等 20 秒好。下一次请求就有值了。
        """
        with self._lock:
            fresh = (
                self._checked_at is not None
                and self._clock() - self._checked_at < self._ttl
            )
            if fresh or self._running:
                return self._value
            self._running = True

        try:
            self._spawn(self._refresh)
        except Exception as exc:
            # 起不来线程（资源耗尽之类）时必须把 _running 放回去，
            # 否则这个探活就永久卡住：之后每次都认为「有人在刷」，
            # 接口一直返回旧值，再也不会重试。
            log.warning("探活线程起不来，这次跳过：%s", exc)
            with self._lock:
                self._running = False

        with self._lock:
            return self._value

    def _refresh(self) -> None:
        try:
            result = bool(self._probe())
        except Exception as exc:
            log.debug("探活失败，按连不上处理：%s", exc)
            result = False
        with self._lock:
            self._value = result
            self._checked_at = self._clock()
            self._running = False

    def refresh_now(self) -> Optional[bool]:
        """同步探一次。只给启动预热和单测用，请求路径上不要调。"""
        self._refresh()
        with self._lock:
            return self._value

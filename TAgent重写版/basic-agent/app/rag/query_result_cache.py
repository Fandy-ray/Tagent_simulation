"""有界检索结果缓存，不保存完整回答；同题并发只执行一次本地检索。"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future
from copy import deepcopy
from typing import Callable

from langchain_core.documents import Document


class QueryResultCache:
    def __init__(self, *, enabled: bool = True, max_entries: int = 128, ttl_seconds: int = 60):
        self.enabled = enabled
        self.max_entries = max(1, min(1024, int(max_entries)))
        self.ttl_seconds = max(0, min(3600, int(ttl_seconds)))
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple, tuple[float, list[Document]]] = OrderedDict()
        self._inflight: dict[tuple, Future] = {}

    def clear(self) -> int:
        """丢掉已缓存的结果（管理后台「清检索缓存」）。正在检索的不动：等它的请求照常拿到结果。"""
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            return count

    def stats(self) -> dict:
        with self._lock:
            return {
                "enabled": self.enabled,
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
                "entries": len(self._entries),
            }

    def get_or_load(self, query: str, *, identity: str, k: int, load: Callable[[], list[Document]]) -> list[Document]:
        if not self.enabled or not self.ttl_seconds:
            return load()
        # identity 绑定完整语料、切块、实际模型版本、精度和检索规则；不保存问题明文。
        key = (identity, k, hashlib.sha256(query.encode("utf-8")).digest())
        now = time.monotonic()
        pending = None
        owner = False
        with self._lock:
            for expired in [key for key, (expiry, _) in self._entries.items() if expiry <= now]:
                self._entries.pop(expired)
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
            else:
                pending = self._inflight.get(key)
                owner = pending is None
                if owner and len(self._inflight) < self.max_entries:
                    pending = Future()
                    self._inflight[key] = pending
        if cached is not None:
            return deepcopy(cached[1])
        if pending is None:
            return deepcopy(load())
        if not owner:
            return deepcopy(pending.result())
        try:
            documents = deepcopy(load())
            response = deepcopy(documents)
            with self._lock:
                self._entries[key] = (time.monotonic() + self.ttl_seconds, documents)
                self._entries.move_to_end(key)
                while len(self._entries) > self.max_entries:
                    self._entries.popitem(last=False)
                self._inflight.pop(key)
        except BaseException as error:
            with self._lock:
                self._inflight.pop(key, None)
            pending.set_exception(error)
            raise
        pending.set_result(documents)
        return response

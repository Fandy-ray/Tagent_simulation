"""检索词的嵌入：同时到的几条合成一批去算、算过的记住、有人在用时让显卡别睡着。

实测（text2vec-base-chinese，Apple M 系列，sentence-transformers 默认用 GPU（MPS），2026-10-26）：

- 一个班同时提问时，每个请求各自调一次 embed_query，几十路同时往同一个模型里塞单句、互相抢：
  32 个不同的问题同时到，各算各的每条要等 480 毫秒；拼成一批算，这一批 58 毫秒；
- 单句紧接着算 12~16 毫秒，隔 0.05~1 秒再算约 30 毫秒，**隔两秒以上要 55~76 毫秒**——显卡闲下来就降频，
  醒过来要几十毫秒。答疑里两次检索之间正好隔着几秒的模型回答，于是几乎每个问题都要多等这几十毫秒；
  （换成 CPU 也不划算：单句 23~42 毫秒，一批 50 句 171 毫秒，GPU 上是 70 毫秒左右）；
- 成批算出的向量和单句算的一致（误差 1e-5 以内）。

所以这里：

- 谁先到谁领头，领头的先等 3 毫秒让同时到的排进来，再把排着的**一批**一起算；它算的时候后到的接着排，
  算完再出一个领头的。没有并发时只多这 3 毫秒；
- 同一句检索词同时来了几条，只算一次；算过的向量记在 LRU 里（检索结果缓存只保 60 秒，过了时间同一句话还会再来）；
- 最近有人在问（答疑里用 2 分钟）时，每隔一会儿（答疑里 0.4 秒）用一句很短的话空算一次，让显卡保持醒着；
  空算也走同一个队，不会和真的检索同时算。没人问了就停，不会一直占着。

和具体模型无关：构造时给一个「一批文本 → 一批向量」的函数。
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Callable, Sequence

WARM_TEXT = "预热"


class _Slot:
    __slots__ = ("done", "vector", "error")

    def __init__(self):
        self.done = False
        self.vector: list[float] | None = None
        self.error: BaseException | None = None


class QueryEmbedder:
    def __init__(
        self,
        embed_batch: Callable[[list[str]], Sequence[Sequence[float]]],
        *,
        max_batch: int = 64,
        cache_size: int = 2048,
        gather_s: float = 0.003,
        keep_warm_s: float = 0.0,
        warm_interval_s: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._embed_batch = embed_batch
        self.max_batch = max_batch
        self.cache_size = cache_size
        self.gather_s = gather_s
        self.keep_warm_s = keep_warm_s
        self.warm_interval_s = warm_interval_s
        self._clock = clock
        self._cond = threading.Condition()
        self._busy = False
        self._pending: OrderedDict[str, _Slot] = OrderedDict()
        self._inflight: dict[str, _Slot] = {}
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._last_used: float | None = None
        self._warmer: threading.Thread | None = None
        self.batches = 0
        self.embedded = 0
        self.warmups = 0

    @property
    def batch_function(self):
        return self._embed_batch

    # ---------- 检索时调 ----------
    def embed(self, text: str) -> list[float]:
        with self._cond:
            self._last_used = self._clock()
            self._ensure_warmer()
            cached = self._cache.get(text)
            if cached is not None:
                self._cache.move_to_end(text)
                return cached
            slot = self._pending.get(text) or self._inflight.get(text)
            if slot is None:
                slot = _Slot()
                self._pending[text] = slot
            while not slot.done:
                if self._busy:
                    self._cond.wait()
                    continue
                self._run_one_batch()
        if slot.error is not None:
            raise slot.error
        return slot.vector  # type: ignore[return-value]

    def _run_one_batch(self) -> None:
        """在锁里调用：等一小会儿让同时到的排进来，取出一批，放开锁去算，算完回到锁里交结果、叫醒等着的。"""
        self._busy = True
        if self.gather_s > 0:
            # 「忙」已经占上了：这段时间里到的都只会排队，不会另起一批
            self._cond.release()
            try:
                time.sleep(self.gather_s)
            finally:
                self._cond.acquire()
        batch: list[tuple[str, _Slot]] = []
        while self._pending and len(batch) < self.max_batch:
            batch.append(self._pending.popitem(last=False))
        for text, slot in batch:
            self._inflight[text] = slot
        vectors: Sequence[Sequence[float]] | None = None
        error: BaseException | None = None
        self._cond.release()
        try:
            vectors = self._embed_batch([text for text, _ in batch])
            if len(vectors) != len(batch):
                raise RuntimeError(f"嵌入返回了 {len(vectors)} 个向量，应该是 {len(batch)} 个")
        except BaseException as exc:  # noqa: BLE001 —— 原样交给这一批里的每个请求，由它们各自抛
            error = exc
        finally:
            self._cond.acquire()
        self.batches += 1
        self.embedded += len(batch)
        for index, (text, slot) in enumerate(batch):
            self._inflight.pop(text, None)
            slot.done = True
            if error is not None:
                slot.error = error
                continue
            slot.vector = list(vectors[index])  # type: ignore[index]
            self._cache[text] = slot.vector
            self._cache.move_to_end(text)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)
        self._busy = False
        self._cond.notify_all()

    # ---------- 让显卡别睡着 ----------
    def _ensure_warmer(self) -> None:
        """在锁里调用。最近有人用、又还没有空算的线程时起一个。"""
        if self.keep_warm_s <= 0 or (self._warmer is not None and self._warmer.is_alive()):
            return
        self._warmer = threading.Thread(target=self._keep_warm, name="query-embedder-warm", daemon=True)
        self._warmer.start()

    def _keep_warm(self) -> None:
        while True:
            time.sleep(self.warm_interval_s)
            with self._cond:
                idle = self._clock() - (self._last_used or 0.0)
                if idle > self.keep_warm_s:
                    return  # 没人问了：线程退出，下次有人问再起
                if self._busy or self._pending:
                    continue  # 正在算真的，本来就醒着
                self._busy = True
            try:
                self._embed_batch([WARM_TEXT])
            except Exception:  # noqa: BLE001 —— 空算失败无所谓，真的检索会自己报错
                pass
            finally:
                with self._cond:
                    self.warmups += 1
                    self._busy = False
                    self._cond.notify_all()

    def run_exclusive(self, work: Callable[[], object]) -> object:
        """独占模型跑一件别的事（预热各种形状）：等正在算的那批算完再跑，跑的时候真的检索排队。"""
        with self._cond:
            while self._busy:
                self._cond.wait()
            self._busy = True
        try:
            return work()
        finally:
            with self._cond:
                self._busy = False
                self._cond.notify_all()

    # ---------- 管理 ----------
    def clear(self) -> int:
        with self._cond:
            count = len(self._cache)
            self._cache.clear()
            return count

    def stats(self) -> dict:
        with self._cond:
            return {
                "cached": len(self._cache),
                "cache_size": self.cache_size,
                "batches": self.batches,
                "embedded": self.embedded,
                "warmups": self.warmups,
            }

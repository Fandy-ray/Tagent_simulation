"""把多个知识来源拼在一起检索。

本地教材 + OpenNotebook 是第一阶段最可能的形态：
一边失败时另一边仍能作答，三个 service 不用知道背后有几个来源。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable


log = logging.getLogger(__name__)

# 一个来源出错之后先歇着，不让学生的问题再去碰它。OpenNotebook 没开时连接会被立刻拒绝，问题不大；
# 但它要是开着却卡住（容器在、接口不回），每个问题都要先白等满超时才轮到本地教材。
#
# 歇够了也不拿学生的问题去试：在后台探一次活（warm_up），探通了才接回来；探的这段时间里问题照样跳过它。
# 一直不通就越歇越久（30 秒起翻倍，最多 5 分钟），省得卡住的服务每隔半分钟被白敲一次。
SOURCE_RETRY_AFTER_SECONDS = 30.0
SOURCE_RETRY_MAX_SECONDS = 300.0


def _in_background(task: Callable[[], None]) -> None:
    threading.Thread(target=task, name="knowledge-source-probe", daemon=True).start()


class CompositeKnowledgeBase:
    def __init__(self, *sources, clock=time.monotonic, run_probe: Callable[[Callable[[], None]], None] = _in_background):
        if not sources:
            raise ValueError("CompositeKnowledgeBase needs at least one source.")
        self.sources = sources
        self._clock = clock
        self._run_probe = run_probe
        self._lock = threading.Lock()
        # id(来源) → 在这个时刻之前先不找它；连续失败几次（决定下次歇多久）；正在后台探活的
        self._resting_until: dict[int, float] = {}
        self._failures: dict[int, int] = {}
        self._probing: set[int] = set()

    def _rest(self, source, exc) -> None:
        with self._lock:
            failures = self._failures.get(id(source), 0) + 1
            self._failures[id(source)] = failures
            seconds = min(SOURCE_RETRY_AFTER_SECONDS * 2 ** (failures - 1), SOURCE_RETRY_MAX_SECONDS)
            self._resting_until[id(source)] = self._clock() + seconds
        log.warning("知识来源 %s 出错，接下来 %.0f 秒先不找它：%s", _kind_of(source), seconds, exc)

    def _recovered(self, source) -> None:
        with self._lock:
            self._failures.pop(id(source), None)
            was_resting = self._resting_until.pop(id(source), None) is not None
        if was_resting:
            log.info("知识来源 %s 恢复了", _kind_of(source))

    def _available(self, source) -> bool:
        """这个来源现在能不能给学生的问题用。歇够了就在后台探一次活，探通之前仍然跳过。"""
        with self._lock:
            until = self._resting_until.get(id(source))
            if until is None:
                return True
            if until > self._clock() or id(source) in self._probing or not hasattr(source, "warm_up"):
                return False
            self._probing.add(id(source))

        def probe():
            try:
                source.warm_up()
            except Exception as exc:  # noqa: BLE001
                self._rest(source, exc)
            else:
                self._recovered(source)
            finally:
                with self._lock:
                    self._probing.discard(id(source))

        self._run_probe(probe)
        with self._lock:  # 同步探活（单测）时这里已经有结论了
            return id(source) not in self._resting_until

    def describe(self) -> dict[str, Any]:
        return {
            "kind": "composite",
            "sources": [
                source.describe() if hasattr(source, "describe") else {"kind": type(source).__name__}
                for source in self.sources
            ],
        }

    def warm_up(self) -> None:
        errors: list[str] = []
        for source in self.sources:
            try:
                source.warm_up()
            except Exception as exc:
                errors.append(f"{type(source).__name__}: {exc}")
                # 少一个来源不致命，但必须喊出来：否则配错地址的表现是
                # "答疑一切正常，只是笔记一条都检索不到"，没人会去查。
                log.warning("知识来源 %s 预热失败：%s", _kind_of(source), exc)
                self._rest(source, exc)
        if len(errors) == len(self.sources):
            raise RuntimeError("所有知识来源预热失败：" + "；".join(errors))

    def ensure_index(self) -> list:
        chunks: list = []
        for source in self.sources:
            if hasattr(source, "ensure_index"):
                try:
                    chunks.extend(source.ensure_index() or [])
                except Exception:
                    continue
        return chunks

    def retrieve(self, query: str, notebook_ids: list[str] | None = None):
        return self._merge(lambda source: source.retrieve(query, notebook_ids=notebook_ids), notebook_ids)

    def search(self, query: str, *, k: int = 3, notebook_ids: list[str] | None = None):
        documents: list = []
        for source in self._iter_sources(notebook_ids):
            try:
                documents.extend(source.search(query, k=k, notebook_ids=notebook_ids) or [])
            except Exception as exc:
                self._rest(source, exc)
                continue
            self._recovered(source)
        return documents

    def chunks(self, notebook_ids: list[str] | None = None):
        documents: list = []
        errors: list[str] = []
        for source in self._iter_sources(notebook_ids):
            try:
                documents.extend(source.chunks(notebook_ids=notebook_ids) or [])
            except Exception as exc:
                errors.append(str(exc))
                self._rest(source, exc)
                continue
            self._recovered(source)
        if not documents:
            raise RuntimeError("没有可出题的知识片段。" + (" ".join(errors) if errors else ""))
        return documents

    def sample_exam_pieces(
        self, topic: str | None = None, notebook_ids: list[str] | None = None
    ) -> list[tuple[str, str]]:
        pieces: list[tuple[str, str]] = []
        for source in self._iter_sources(notebook_ids):
            try:
                found = source.sample_exam_pieces(topic, notebook_ids=notebook_ids)
            except Exception as exc:
                self._rest(source, exc)
                continue
            self._recovered(source)
            pieces.extend((text.strip(), kind) for text, kind in found if text and text.strip())
        return pieces

    def quiz_documents(self, *, max_documents: int = 2, notebook_ids: list[str] | None = None):
        from app.rag.knowledge_base import select_quiz_documents

        return select_quiz_documents(self.chunks(notebook_ids=notebook_ids), max_documents=max_documents)

    def _iter_sources(self, notebook_ids: list[str] | None):
        scoped = [str(item).strip() for item in notebook_ids or [] if str(item).strip()]
        for source in self.sources:
            kind = source.describe().get("kind") if hasattr(source, "describe") else ""
            if scoped and kind == "local":
                continue
            if not self._available(source):
                continue  # 刚出过错，先不找它（见 SOURCE_RETRY_AFTER_SECONDS）
            yield source

    def _merge(self, call, notebook_ids: list[str] | None = None):
        parts: list[str] = []
        documents: list = []
        errors: list[str] = []
        for source in self._iter_sources(notebook_ids):
            try:
                context, docs = call(source)
            except Exception as exc:
                errors.append(str(exc))
                self._rest(source, exc)
                continue
            self._recovered(source)
            if context and context.strip():
                parts.append(context.strip())
            documents.extend(docs or [])
        if not parts and not documents:
            raise RuntimeError("所有知识来源检索失败。" + (" ".join(errors) if errors else ""))
        return "\n\n---\n\n".join(parts), documents


def _kind_of(source) -> str:
    if hasattr(source, "describe"):
        try:
            return str(source.describe().get("kind") or type(source).__name__)
        except Exception:
            pass
    return type(source).__name__

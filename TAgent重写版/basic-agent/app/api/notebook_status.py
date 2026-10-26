"""笔记本服务连不连得上：后台探活，接口里只拿缓存的结论。

单独成模块（不定义 blueprint）：答疑页的 /knowledge 和管理后台的 /admin/knowledge 都要这一份结论，
而 controller 之间不许互相 import（tools/check_architecture.py 第 6 条）。
"""

from __future__ import annotations

import threading

from app.config import AgentConfig
from app.infra.background_probe import BackgroundProbe


# 探活结果按「知识库实例」缓存。/knowledge 前端每次打开答疑页都会调，
# 而它不调模型，本不该有可感知延迟；原先同步 ping，断连时一次要等 15~20 秒。
# 连同知识库对象本身一起存：只存 id() 的话，对象被回收后 id 会被新对象重用，
# 新知识库就会继承到旧的探活结果。顺带按 source 分键——AgentConfig.from_env()
# 是每次请求读的，知识来源可以在不重启的情况下变，变了就该换一个探测函数。
_probes: dict[tuple[int, str], tuple[object, BackgroundProbe]] = {}
_probes_lock = threading.Lock()


def _probe_for(knowledge_base, source: str, probe_fn) -> BackgroundProbe:
    key = (id(knowledge_base), source)
    with _probes_lock:
        cached = _probes.get(key)
        if cached is None:
            cached = (knowledge_base, BackgroundProbe(probe_fn))
            _probes[key] = cached
        return cached[1]


def notebook_reachable(settings: AgentConfig, knowledge_base) -> bool | None:
    """不阻塞：拿上一次后台探测的结果，过期了顺手丢个后台线程去刷。只用本地知识时返回 None。"""
    probe_fn = None
    if settings.knowledge_source in {"notebook", "composite"} and hasattr(knowledge_base, "ping"):
        probe_fn = knowledge_base.ping
    elif settings.knowledge_source == "composite":

        def probe_fn():
            return _notebook_reachable(knowledge_base)

    if probe_fn is None:
        return None
    return _probe_for(knowledge_base, settings.knowledge_source, probe_fn).value()


def _notebook_reachable(knowledge_base) -> bool | None:
    sources = getattr(knowledge_base, "sources", ())
    for source in sources:
        if hasattr(source, "ping"):
            try:
                return bool(source.ping())
            except Exception:
                return False
    return None

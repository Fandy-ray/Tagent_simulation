"""知识来源状态。给基础前端看现在用的是教材、笔记库还是两边一起。"""

from __future__ import annotations

import threading

from flask import Blueprint, jsonify

from app.api.deps import get_services
from app.config import AgentConfig
from app.infra.background_probe import BackgroundProbe


blueprint = Blueprint("knowledge", __name__)

# 探活结果按「知识库实例」缓存。这个接口前端每次打开答疑页都会调，
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


@blueprint.get("/knowledge")
def knowledge_status():
    settings = AgentConfig.from_env()
    knowledge_base = get_services().knowledge_base
    payload = (
        knowledge_base.describe()
        if hasattr(knowledge_base, "describe")
        else {"kind": type(knowledge_base).__name__}
    )
    reachable = None
    probe_fn = None
    if settings.knowledge_source in {"notebook", "composite"} and hasattr(knowledge_base, "ping"):
        probe_fn = knowledge_base.ping
    elif settings.knowledge_source == "composite":

        def probe_fn():
            return _notebook_reachable(knowledge_base)

    if probe_fn is not None:
        # 不阻塞：拿上一次的结果，过期了顺手丢个后台线程去刷
        reachable = _probe_for(knowledge_base, settings.knowledge_source, probe_fn).value()
    return jsonify(
        {
            "source": settings.knowledge_source,
            "notebook_url": settings.notebook_url,
            "notebook_reachable": reachable,
            "knowledge_base": payload,
        }
    )


def _notebook_reachable(knowledge_base) -> bool | None:
    sources = getattr(knowledge_base, "sources", ())
    for source in sources:
        if hasattr(source, "ping"):
            try:
                return bool(source.ping())
            except Exception:
                return False
    return None

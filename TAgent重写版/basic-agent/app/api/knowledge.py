"""知识来源状态。给基础前端看现在用的是教材、笔记库还是两边一起。"""

from __future__ import annotations

from flask import Blueprint, jsonify

from app.api.deps import get_services
from app.api.notebook_status import notebook_reachable
from app.config import AgentConfig


blueprint = Blueprint("knowledge", __name__)


@blueprint.get("/knowledge")
def knowledge_status():
    settings = AgentConfig.from_env()
    knowledge_base = get_services().knowledge_base
    payload = (
        knowledge_base.describe()
        if hasattr(knowledge_base, "describe")
        else {"kind": type(knowledge_base).__name__}
    )
    return jsonify(
        {
            "source": settings.knowledge_source,
            "notebook_url": settings.notebook_url,
            # 不阻塞：拿上一次后台探测的结果（见 notebook_status.py）
            "notebook_reachable": notebook_reachable(settings, knowledge_base),
            "knowledge_base": payload,
        }
    )

"""controller 的依赖获取入口。

**这是全工程唯一允许碰 current_app.extensions 的地方。**
service 层不认识 Flask，拿依赖一律经过这里注入。
"""

from __future__ import annotations

from flask import current_app, g

from app.errors.api_errors import AgentAPIError
from app.errors.api_errors import ModelNotFoundError


def get_registry():
    return current_app.extensions["model_provider_registry"]


def select_provider(model_id: str | None = None):
    registry = get_registry()
    course = getattr(g, "course", None)
    if course and current_app.config.get("AUTH_ENABLED"):
        allowed = course.get("model_ids") or []
        if not allowed:
            raise AgentAPIError("这门课程尚未配置模型。", 409, "course_models_empty")
        if model_id and model_id not in allowed:
            raise AgentAPIError("该模型不属于当前课程。", 403, "course_model_forbidden")
        model_id = model_id or allowed[0]
    try:
        return registry.get_enabled_provider(model_id)
    except KeyError:
        missing = model_id or registry.get_default_model_id() or "default"
        raise ModelNotFoundError(missing)


def get_services():
    return current_app.extensions["services"]


def get_chat_service():
    return get_services().chat


def get_quiz_service():
    return get_services().quiz


def get_exam_service():
    return get_services().exam


def get_essay_service():
    return get_services().essay


def get_learning_store():
    """学习记录库；没开、没建成、或测试替身里没有时返回 None。"""
    return getattr(current_app.extensions.get("services"), "store", None)


def invalidate_provider(model_id: str | None) -> None:
    services = current_app.extensions.get("services")
    if services is not None and hasattr(services, "invalidate_provider"):
        services.invalidate_provider(model_id)

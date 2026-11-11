"""api 层公用的小工具：取 service、解析请求体和查询参数、包 SSE 响应。

deps 只在这里碰 current_app.extensions（同 tagent 的 app/api/deps.py）。
"""

from __future__ import annotations

import json
from typing import Iterator, TypeVar

from flask import Response, current_app, request, stream_with_context
from pydantic import BaseModel, ValidationError

from app.service.notebook.assembly import Services
from app.errors.notebook import ValidationFailed

Body = TypeVar("Body", bound=BaseModel)

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def services() -> Services:
    # 并进 tagent 之后，extensions["services"] 是答疑那一套；笔记本的放在另一个键里。
    notebook = current_app.extensions.get("notebook_services")
    if notebook is not None:
        return notebook
    return current_app.extensions["services"]


def describe_validation(error: ValidationError) -> str:
    parts = []
    for item in error.errors()[:5]:
        location = ".".join(str(x) for x in item.get("loc", ()) if x != "__root__") or "body"
        parts.append(f"{location}: {item.get('msg', 'invalid')}")
    return "; ".join(parts) or "请求格式不对"


def parse(model: type[Body], data=None) -> Body:
    if data is None:
        data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationFailed("请求体必须是 JSON 对象")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ValidationFailed(describe_validation(exc)) from exc


def parse_optional(model: type[Body]) -> Body:
    """请求体可以不给（比如「存成笔记」不指定笔记本）。"""
    data = request.get_json(silent=True)
    return parse(model, data if isinstance(data, dict) else {})


def to_bool(value: str | None, *, name: str, default: bool | None) -> bool | None:
    if value is None or value == "":
        return default
    lowered = value.strip().lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise ValidationFailed(f"{name} 必须是布尔值")


def arg_bool(name: str, default: bool | None = None) -> bool | None:
    return to_bool(request.args.get(name), name=name, default=default)


def arg_int(name: str, default: int, *, low: int, high: int) -> int:
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValidationFailed(f"{name} 必须是整数") from exc
    if value < low or value > high:
        raise ValidationFailed(f"{name} 必须在 {low}~{high} 之间")
    return value


def form_list(name: str) -> list[str] | None:
    """表单里的数组字段是 JSON 字符串（原版前端就这么发）。"""
    raw = request.form.get(name)
    if raw is None or raw == "":
        return None
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise ValidationFailed(f"{name} 必须是 JSON 数组") from exc
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValidationFailed(f"{name} 必须是字符串数组")
    if len(value) > 50:
        raise ValidationFailed(f"{name} 最多 50 项")
    return value


def sse_response(events: Iterator[str]) -> Response:
    return Response(
        stream_with_context(events),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

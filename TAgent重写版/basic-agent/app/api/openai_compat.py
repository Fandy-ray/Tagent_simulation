"""OpenAI 兼容的公开通道。"""

from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify

from app.api.deps import get_registry, select_provider
from app.api.openai_view import chat_completion_response
from app.api.validators import json_body
from app.util.timeutil import timestamp_to_epoch


blueprint = Blueprint("openai", __name__, url_prefix="/v1")


@blueprint.get("/models")
def list_models():
    providers = get_registry().enabled_providers()
    course = getattr(g, "course", None)
    if current_app.config.get("AUTH_ENABLED") and course:
        allowed = set(course.get("model_ids") or [])
        providers = [provider for provider in providers if provider.served_model_id in allowed]
    return jsonify(
        {
            "object": "list",
            "data": [
                {
                    "id": provider.served_model_id,
                    "name": provider.name,
                    "object": "model",
                    "created": timestamp_to_epoch(provider.created_at),
                    "owned_by": "tagent",
                }
                for provider in providers
            ],
        }
    )


@blueprint.post("/chat/completions")
def chat_completions():
    data = json_body()
    provider = select_provider(data.get("model"))
    return chat_completion_response(data, provider)

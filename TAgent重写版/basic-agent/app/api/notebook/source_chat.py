"""来源聊天接口（同原版 api/routers/source_chat.py），发消息走 SSE。"""

from __future__ import annotations

from flask import Blueprint, jsonify

from app.api.notebook.http import parse, parse_optional, services, sse_response
from app.schema.notebook.requests import ChatSessionUpdate, SourceChatMessage, SourceChatSessionCreate

blueprint = Blueprint("source_chat", __name__, url_prefix="/api/sources/<source_id>/chat")


@blueprint.get("/sessions")
def list_sessions(source_id: str):
    return jsonify(services().chat.list_source_sessions(source_id))


@blueprint.post("/sessions")
def create_session(source_id: str):
    body = parse_optional(SourceChatSessionCreate)
    return jsonify(services().chat.create_source_session(source_id, body.title, body.model_override))


@blueprint.get("/sessions/<session_id>")
def get_session(source_id: str, session_id: str):
    return jsonify(services().chat.get_source_session(source_id, session_id))


@blueprint.put("/sessions/<session_id>")
def update_session(source_id: str, session_id: str):
    body = parse(ChatSessionUpdate)
    return jsonify(services().chat.update_source_session(source_id, session_id, body.model_dump(exclude_unset=True)))


@blueprint.delete("/sessions/<session_id>")
def delete_session(source_id: str, session_id: str):
    return jsonify(services().chat.delete_source_session(source_id, session_id))


@blueprint.post("/sessions/<session_id>/messages")
def send_message(source_id: str, session_id: str):
    body = parse(SourceChatMessage)
    return sse_response(services().chat.source_message_stream(source_id, session_id, body.message))

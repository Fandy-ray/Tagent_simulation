"""笔记本聊天接口（同原版 api/routers/chat.py）。"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.api.notebook.http import parse, services
from app.errors.notebook import ValidationFailed
from app.schema.notebook.requests import BuildContext, ChatExecute, ChatSessionCreate, ChatSessionUpdate

blueprint = Blueprint("chat", __name__, url_prefix="/api")


@blueprint.get("/chat/sessions")
def list_sessions():
    notebook_id = request.args.get("notebook_id")
    if not notebook_id:
        raise ValidationFailed("notebook_id 必填")
    return jsonify(services().chat.list_sessions(notebook_id))


@blueprint.post("/chat/sessions")
def create_session():
    body = parse(ChatSessionCreate)
    return jsonify(services().chat.create_session(body.notebook_id, body.title, body.model_override))


@blueprint.get("/chat/sessions/<session_id>")
def get_session(session_id: str):
    return jsonify(services().chat.get_session(session_id))


@blueprint.put("/chat/sessions/<session_id>")
def update_session(session_id: str):
    body = parse(ChatSessionUpdate)
    return jsonify(services().chat.update_session(session_id, body.model_dump(exclude_unset=True)))


@blueprint.delete("/chat/sessions/<session_id>")
def delete_session(session_id: str):
    return jsonify(services().chat.delete_session(session_id))


@blueprint.post("/chat/execute")
def execute():
    body = parse(ChatExecute)
    return jsonify(services().chat.execute(body.session_id, body.message, body.context))


@blueprint.post("/chat/context")
def build_context():
    body = parse(BuildContext)
    return jsonify(services().chat.build_context(body.notebook_id, body.context_config))

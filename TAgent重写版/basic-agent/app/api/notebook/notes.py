"""笔记接口（同原版 api/routers/notes.py）。"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.api.notebook.http import parse, services
from app.schema.notebook.requests import NoteCreate, NoteUpdate

blueprint = Blueprint("notes", __name__, url_prefix="/api")


@blueprint.get("/notes")
def list_notes():
    return jsonify(services().notes.list(request.args.get("notebook_id") or None))


@blueprint.post("/notes")
def create_note():
    body = parse(NoteCreate)
    return jsonify(services().notes.create(
        title=body.title, content=body.content, note_type=body.note_type, notebook_id=body.notebook_id
    ))


@blueprint.get("/notes/<note_id>")
def get_note(note_id: str):
    return jsonify(services().notes.get(note_id))


@blueprint.put("/notes/<note_id>")
def update_note(note_id: str):
    body = parse(NoteUpdate)
    return jsonify(services().notes.update(note_id, body.model_dump(exclude_unset=True)))


@blueprint.delete("/notes/<note_id>")
def delete_note(note_id: str):
    return jsonify(services().notes.delete(note_id))

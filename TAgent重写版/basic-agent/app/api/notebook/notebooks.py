"""笔记本接口（同原版 api/routers/notebooks.py）。"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.api.notebook.http import arg_bool, arg_int, parse, services
from app.schema.notebook.requests import NotebookCreate, NotebookUpdate

blueprint = Blueprint("notebooks", __name__, url_prefix="/api")


@blueprint.get("/notebooks")
def list_notebooks():
    return jsonify(services().notebooks.list(
        archived=arg_bool("archived"), order_by=request.args.get("order_by") or "updated desc"
    ))


@blueprint.post("/notebooks")
def create_notebook():
    body = parse(NotebookCreate)
    return jsonify(services().notebooks.create(body.name, body.description))


@blueprint.get("/recently-viewed")
def recently_viewed():
    return jsonify(services().notebooks.recently_viewed(arg_int("limit", 12, low=1, high=50)))


@blueprint.get("/notebooks/<notebook_id>/delete-preview")
def delete_preview(notebook_id: str):
    return jsonify(services().notebooks.delete_preview(notebook_id))


@blueprint.get("/notebooks/<notebook_id>")
def get_notebook(notebook_id: str):
    return jsonify(services().notebooks.get(notebook_id))


@blueprint.put("/notebooks/<notebook_id>")
def update_notebook(notebook_id: str):
    body = parse(NotebookUpdate)
    return jsonify(services().notebooks.update(notebook_id, body.model_dump(exclude_unset=True)))


@blueprint.post("/notebooks/<notebook_id>/sources/<source_id>")
def add_source(notebook_id: str, source_id: str):
    return jsonify(services().notebooks.add_source(notebook_id, source_id))


@blueprint.delete("/notebooks/<notebook_id>/sources/<source_id>")
def remove_source(notebook_id: str, source_id: str):
    return jsonify(services().notebooks.remove_source(notebook_id, source_id))


@blueprint.delete("/notebooks/<notebook_id>")
def delete_notebook(notebook_id: str):
    return jsonify(services().notebooks.delete(
        notebook_id, delete_exclusive_sources=bool(arg_bool("delete_exclusive_sources", False))
    ))

"""来源接口（同原版 api/routers/sources.py），外加洞察列表/生成和「重新嵌入」。"""

from __future__ import annotations

from flask import Blueprint, jsonify, request, send_file

from app.api.notebook.http import arg_int, form_list, parse, services
from app.errors.notebook import ValidationFailed
from app.schema.notebook.requests import EmbedRequest, InsightCreate, SourceJsonCreate, SourceUpdate
from app.service.notebook.source_service import SourceInput

blueprint = Blueprint("sources", __name__, url_prefix="/api")

_TYPES = {"link", "upload", "text"}
_TRUE = {"1", "true", "yes", "on"}


def _form_flag(name: str) -> bool:
    return (request.form.get(name) or "").strip().lower() in _TRUE


def _from_json(body: SourceJsonCreate) -> SourceInput:
    notebooks = body.notebooks or ([body.notebook_id] if body.notebook_id else [])
    return SourceInput(
        type=body.type, notebook_ids=notebooks, url=body.url, content=body.content, title=body.title,
        file_path=body.file_path, transformations=body.transformations, embed=body.embed,
        delete_source=body.delete_source, async_processing=body.async_processing,
    )


def _from_form() -> SourceInput:
    source_type = (request.form.get("type") or "").strip()
    if source_type not in _TYPES:
        raise ValidationFailed("type 必须是 link / upload / text")
    notebooks = form_list("notebooks")
    notebook_id = (request.form.get("notebook_id") or "").strip()
    if notebooks and notebook_id:
        raise ValidationFailed("notebook_id 和 notebooks 不能同时给")
    upload = request.files.get("file")
    return SourceInput(
        type=source_type,
        notebook_ids=notebooks or ([notebook_id] if notebook_id else []),
        url=request.form.get("url"),
        content=request.form.get("content"),
        title=request.form.get("title"),
        file_path=request.form.get("file_path"),
        upload_name=upload.filename if upload else None,
        upload_stream=upload.stream if upload else None,
        transformations=form_list("transformations") or [],
        embed=_form_flag("embed"),
        delete_source=_form_flag("delete_source"),
        async_processing=_form_flag("async_processing"),
    )


@blueprint.get("/sources")
def list_sources():
    return jsonify(services().sources.list(
        notebook_id=request.args.get("notebook_id") or None,
        limit=arg_int("limit", 50, low=1, high=100),
        offset=arg_int("offset", 0, low=0, high=10**9),
        sort_by=request.args.get("sort_by") or "updated",
        sort_order=(request.args.get("sort_order") or "desc").lower(),
    ))


@blueprint.post("/sources")
def create_source():
    data = _from_json(parse(SourceJsonCreate)) if request.is_json else _from_form()
    return jsonify(services().sources.create(data))


@blueprint.post("/sources/json")
def create_source_json():
    return jsonify(services().sources.create(_from_json(parse(SourceJsonCreate))))


@blueprint.get("/sources/<source_id>")
def get_source(source_id: str):
    return jsonify(services().sources.get(source_id))


@blueprint.get("/sources/<source_id>/download")
def download_source(source_id: str):
    path, name = services().sources.download_path(source_id)
    return send_file(path, as_attachment=True, download_name=name)


@blueprint.get("/sources/<source_id>/status")
def source_status(source_id: str):
    return jsonify(services().sources.status(source_id))


@blueprint.put("/sources/<source_id>")
def update_source(source_id: str):
    body = parse(SourceUpdate)
    return jsonify(services().sources.update(source_id, body.model_dump(exclude_unset=True)))


@blueprint.post("/sources/<source_id>/retry")
def retry_source(source_id: str):
    return jsonify(services().sources.retry(source_id))


@blueprint.delete("/sources/<source_id>")
def delete_source(source_id: str):
    return jsonify(services().sources.delete(source_id))


@blueprint.get("/sources/<source_id>/insights")
def list_insights(source_id: str):
    return jsonify(services().insights.list_for_source(source_id))


@blueprint.post("/sources/<source_id>/insights")
def create_insight(source_id: str):
    body = parse(InsightCreate)
    return jsonify(services().insights.create_insight(source_id, body.transformation_id)), 202


@blueprint.post("/embed")
def embed_item():
    body = parse(EmbedRequest)
    if body.item_type == "note":
        return jsonify(services().notes.embed(body.item_id))
    return jsonify(services().sources.embed(body.item_id, async_processing=body.async_processing))

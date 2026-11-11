"""检索与问答接口（同原版 api/routers/search.py）。"""

from __future__ import annotations

from flask import Blueprint, jsonify

from app.api.notebook.http import parse, services, sse_response
from app.schema.notebook.requests import AskRequest, SearchRequest

blueprint = Blueprint("search", __name__, url_prefix="/api")


@blueprint.post("/search")
def search():
    body = parse(SearchRequest)
    return jsonify(services().search.search(
        query=body.query, kind=body.type, limit=body.limit, sources=body.search_sources,
        notes=body.search_notes, minimum_score=body.minimum_score, raw_scope=body.scope(),
    ))


@blueprint.post("/search/ask")
def ask_stream():
    body = parse(AskRequest)
    return sse_response(services().ask.stream(body.question, body.scope()))


@blueprint.post("/search/ask/simple")
def ask_simple():
    body = parse(AskRequest)
    return jsonify(services().ask.ask(body.question, body.scope()))

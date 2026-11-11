"""洞察接口（同原版 api/routers/insights.py）。"""

from __future__ import annotations

from flask import Blueprint, jsonify

from app.api.notebook.http import parse_optional, services
from app.schema.notebook.requests import SaveAsNote

blueprint = Blueprint("insights", __name__, url_prefix="/api")


@blueprint.get("/insights/<insight_id>")
def get_insight(insight_id: str):
    return jsonify(services().insights.get(insight_id))


@blueprint.delete("/insights/<insight_id>")
def delete_insight(insight_id: str):
    return jsonify(services().insights.delete(insight_id))


@blueprint.post("/insights/<insight_id>/save-as-note")
def save_as_note(insight_id: str):
    body = parse_optional(SaveAsNote)
    return jsonify(services().insights.save_as_note(insight_id, body.notebook_id))

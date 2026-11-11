"""杂项：探活、配置、口令状态、设置（只读）、模型（只读）、内置变换（只读）、任务状态。"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.api.notebook.http import services

blueprint = Blueprint("notebook_meta", __name__)
# 单独的根路径：并进 tagent 之后 / 和 /health 已经是 basic-agent 的，不能再占。
# 笔记本自己的测试应用仍会挂上这份。
root_blueprint = Blueprint("notebook_root", __name__)


@root_blueprint.get("/")
def root():
    return jsonify({"message": "Open Notebook API is running"})


@root_blueprint.get("/health")
def root_health():
    return health()


@blueprint.get("/api/health")
def health():
    return jsonify({"status": "healthy"})


@blueprint.get("/api/config")
def config():
    return jsonify(services().meta.config())


@blueprint.get("/api/auth/status")
def auth_status():
    return jsonify(services().meta.auth_status())


@blueprint.get("/api/settings")
def settings():
    return jsonify(services().meta.settings())


@blueprint.get("/api/models")
def models():
    return jsonify(services().meta.models(request.args.get("type") or None))


@blueprint.get("/api/models/defaults")
def model_defaults():
    return jsonify(services().meta.model_defaults())


@blueprint.get("/api/models/<model_id>")
def model(model_id: str):
    return jsonify(services().meta.model(model_id))


@blueprint.get("/api/transformations")
def transformations():
    return jsonify(services().insights.list_transformations())


@blueprint.get("/api/transformations/<transformation_id>")
def transformation(transformation_id: str):
    return jsonify(services().insights.get_transformation(transformation_id))


@blueprint.get("/api/commands/jobs/<job_id>")
def job_status(job_id: str):
    return jsonify(services().meta.job(job_id))

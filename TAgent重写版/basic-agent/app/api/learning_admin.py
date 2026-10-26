"""老师看学情：学习记录库的只读接口 + 手动备份。

和模型登记同一套管理员口令（X-Agent-Admin-Token）：这里能读到学生的原文和成绩，
不能像答疑接口那样对谁都开放。没配口令时整组接口 503。
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.api.deps import get_learning_store
from app.api.security import require_admin_token
from app.errors.api_errors import AgentAPIError


blueprint = Blueprint("learning_admin", __name__, url_prefix="/admin/learning")

MAX_LIMIT = 500


def _store():
    require_admin_token()
    store = get_learning_store()
    if store is None:
        raise AgentAPIError(
            "学习记录库没有启用（LEARNING_STORE=0，或启动时没能打开数据库文件）。",
            503,
            "learning_store_unavailable",
        )
    return store


def _limit(default: int) -> int:
    raw = request.args.get("limit", "")
    if not raw:
        return default
    if not raw.isdigit() or not 1 <= int(raw) <= MAX_LIMIT:
        raise AgentAPIError(f"limit 要在 1 到 {MAX_LIMIT} 之间。", 400, "validation_error")
    return int(raw)


@blueprint.get("/summary")
def summary():
    """全班概览：总量 + 每个学生的提问数、批改数与平均分。"""
    return jsonify(_store().summary(limit=_limit(MAX_LIMIT)))


@blueprint.get("/students/<string:student_id>")
def student(student_id: str):
    """一个学生最近的答疑、论文批改、整卷记录（各取最近 limit 条，带原文与批改结果）。"""
    timeline = _store().student_timeline(student_id, limit=_limit(50))
    if timeline["student"] is None:
        raise AgentAPIError("没有这个学生的记录。", 404, "student_not_found")
    return jsonify(timeline)


MAX_DAYS = 365


def _days(default: int | None) -> int | None:
    raw = request.args.get("days", "")
    if not raw:
        return default
    if not raw.isdigit() or not 1 <= int(raw) <= MAX_DAYS:
        raise AgentAPIError(f"days 要在 1 到 {MAX_DAYS} 之间。", 400, "validation_error")
    return int(raw)


@blueprint.get("/analytics")
def analytics():
    """数据看板：最近 days 天（默认 14）每天的答疑、批改、出卷、交卷量和活跃学生数。"""
    return jsonify(_store().analytics(days=_days(14)))


@blueprint.get("/models")
def model_stats():
    """评测排行榜：按模型统计答疑量、平均耗时、答完率、赞踩、批改与整卷平均分。不带 days 时统计全部记录。"""
    return jsonify({"models": _store().model_stats(days=_days(None))})


@blueprint.get("/models/<string:model>/activity")
def model_activity(model: str):
    """排行榜点开一个模型：最近 days 天（默认 30）每天的答疑量、赞 / 踩，和它用在了哪些场景。"""
    return jsonify(_store().model_activity(model, days=_days(30)))


@blueprint.get("/feedback")
def feedback():
    """学生点的「有帮助 / 没有帮助」，最新的在前。rating=up|down 只看一种。"""
    rating = request.args.get("rating", "")
    if rating not in ("", "up", "down"):
        raise AgentAPIError("rating 只能是 up 或 down。", 400, "validation_error")
    value = {"up": 1, "down": -1}.get(rating)
    return jsonify({"feedback": _store().feedback_list(limit=_limit(100), rating=value)})


@blueprint.delete("/feedback/<int:feedback_id>")
def delete_feedback(feedback_id: int):
    """删掉一条反馈（演示、调试时自己点的那些）。"""
    if not _store().delete_feedback(feedback_id):
        raise AgentAPIError("没有这条反馈（可能已经删了）。", 404, "feedback_not_found")
    return jsonify({"status": True})


@blueprint.get("/db")
def db_info():
    """库文件、大小、各表条数和现有备份。"""
    return jsonify(_store().db_info())


@blueprint.post("/backup")
def backup():
    """立刻备份一份（平时每天自动备一次，比赛、演示前可以手动再备一次）。"""
    target = _store().backup()
    return jsonify({"status": True, "file": target.name, "bytes": target.stat().st_size})

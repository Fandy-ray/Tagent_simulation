"""统一请求边界。启用后，所有浏览器业务接口都从服务端会话识别账号。"""

from __future__ import annotations

from flask import current_app, g, request

from app.api.auth import require_csrf
from app.auth.service import Session
from app.errors.api_errors import AgentAPIError


PUBLIC_PATHS = {
    "/health",
    "/auth/status",
    "/auth/register",
    "/auth/verify-email",
    "/auth/password/forgot",
    "/auth/password/reset",
    "/auth/login",
}


def _direct_admin_call() -> bool:
    return (
        request.path.startswith("/admin/")
        and request.remote_addr in {"127.0.0.1", "::1"}
        and "X-Tagent-Via-Frontend" not in request.headers
        and bool(request.headers.get("X-Agent-Admin-Token"))
    )


def enforce_identity() -> None:
    if not current_app.config.get("AUTH_ENABLED") or request.method == "OPTIONS":
        return
    path = request.path.rstrip("/") or "/"
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("Origin")
        if origin and origin.rstrip("/") != current_app.config["AUTH_PUBLIC_ORIGIN"]:
            raise AgentAPIError("请求来源不受信任。", 403, "invalid_origin")
    if path in PUBLIC_PATHS:
        return
    # 本机工具的旧管理口令、内部服务令牌仍由原路由各自校验。
    if _direct_admin_call() or path.startswith("/internal/") or path.startswith("/v1/raw/"):
        return

    service = current_app.extensions["auth_service"]
    token = request.cookies.get(current_app.config["AUTH_COOKIE_NAME"], "")
    try:
        session: Session | None = service.session(token)
    except Exception as exc:
        current_app.logger.error("Identity store unavailable: %s", type(exc).__name__)
        raise AgentAPIError("账号服务暂时不可用。", 503, "auth_store_unavailable") from exc
    if not session:
        raise AgentAPIError("请先登录。", 401, "login_required")
    g.auth_session = session
    g.account = session.account
    g.course = None
    course_id = request.headers.get("X-Tagent-Course-Id", "").strip()
    if course_id and course_id != "general":
        course = service.course(course_id)
        if not course:
            raise AgentAPIError("课程不存在。", 404, "course_not_found")
        if session.account["role"] != "admin" and not service.is_member(session.account["uid"], course_id):
            raise AgentAPIError("你尚未加入这门课程。", 403, "course_forbidden")
        g.course = course
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_csrf()

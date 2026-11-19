"""浏览器账号接口。响应与日志均不包含密码、链接令牌或会话令牌。"""

from __future__ import annotations

import hmac
import ipaddress
import time

from flask import Blueprint, current_app, g, jsonify, make_response, request

from app.auth.service import public_account
from app.errors.api_errors import AgentAPIError


blueprint = Blueprint("auth", __name__, url_prefix="/auth")


@blueprint.get("/status")
def status():
    """让前端识别是否已切到账号模式，不泄露账号配置。"""
    enabled = bool(current_app.config.get("AUTH_ENABLED"))
    return jsonify({
        "enabled": enabled,
        "registration_open": _service().registration_is_open() if enabled else False,
        "registration_method": "email",
        "email_verification_required": bool(_service().mailer.can_send) if enabled else False,
        "password_reset_available": bool(_service().mailer.can_send) if enabled else False,
    })


def _service():
    service = current_app.extensions.get("auth_service")
    if service is None:
        raise AgentAPIError("账号服务尚未启用。", 503, "auth_unavailable")
    return service


def _data():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise AgentAPIError("请求应为 JSON 对象。", 400, "invalid_json")
    return data


def _ip():
    # Vite 在本机代理时覆盖此头；公网直连的浏览器头不能作为限流来源。
    if request.remote_addr in {"127.0.0.1", "::1"} and request.headers.get("X-Tagent-Via-Frontend") == "1":
        forwarded = request.headers.get("X-Tagent-Client-IP", "")
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return request.remote_addr or "unknown"


@blueprint.post("/register")
def register():
    data = _data()
    mail_enabled = _service().mailer.can_send
    _service().register(data.get("email"), data.get("password"), data.get("name", ""), _ip())
    if not mail_enabled:
        return jsonify({"message": "账号已创建，请登录。"}), 201
    return jsonify({"message": "如该邮箱可以注册，验证邮件将很快送达。"}), 202


@blueprint.post("/verify-email")
def verify_email():
    _service().verify_email(_data().get("token"))
    return jsonify({"verified": True})


@blueprint.post("/password/forgot")
def forgot_password():
    _service().request_reset(_data().get("email"))
    return jsonify({"message": "如该账号存在，重置邮件将很快送达。"}), 202


@blueprint.post("/password/reset")
def reset_password():
    data = _data()
    _service().reset_password(data.get("token"), data.get("password"))
    return jsonify({"reset": True})


@blueprint.post("/login")
def login():
    data = _data()
    existing = request.cookies.get(current_app.config["AUTH_COOKIE_NAME"], "")
    if existing and _service().session(existing):
        raise AgentAPIError("请先退出当前账号，再登录其他账号。", 409, "already_logged_in")
    token, session = _service().login(data.get("identifier", data.get("email")), data.get("password"), _ip())
    response = make_response(jsonify({
        "user": public_account(session.account), "csrf": session.csrf,
    }))
    response.set_cookie(
        current_app.config["AUTH_COOKIE_NAME"], token,
        secure=current_app.config["AUTH_COOKIE_SECURE"], httponly=True,
        samesite="Lax", path="/", max_age=max(0, int(session.expires_at / 1000 - time.time())),
    )
    return response


@blueprint.get("/me")
def me():
    session = getattr(g, "auth_session", None)
    if not session:
        raise AgentAPIError("请先登录。", 401, "login_required")
    return jsonify({"user": public_account(session.account), "csrf": session.csrf})


@blueprint.post("/logout")
def logout():
    session = getattr(g, "auth_session", None)
    if session:
        _service().revoke_digest(session.digest)
    response = make_response(jsonify({"logged_out": True}))
    response.delete_cookie(current_app.config["AUTH_COOKIE_NAME"], path="/")
    return response


def require_csrf() -> None:
    session = getattr(g, "auth_session", None)
    token = request.headers.get("X-Tagent-CSRF", "")
    if not session or not hmac.compare_digest(token, session.csrf):
        raise AgentAPIError("页面验证已失效，请刷新后重试。", 403, "csrf_failed")

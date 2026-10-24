"""管理通道与内部通道的 token 鉴权。

两个 token 都用 hmac.compare_digest 做定长比较，避免计时侧信道。
未配置 token 时返回 503 而不是 403：这是"功能未启用"，不是"你没权限"。
"""

from __future__ import annotations

import hmac

from flask import current_app, request

from app.errors.api_errors import AgentAPIError


def require_admin_token() -> None:
    expected = current_app.config.get("AGENT_ADMIN_TOKEN", "")
    if not expected:
        raise AgentAPIError(
            "Agent administration is unavailable because its token is not configured.",
            503,
            "admin_token_not_configured",
        )
    provided = request.headers.get("X-Agent-Admin-Token", "")
    if not provided or not hmac.compare_digest(provided, expected):
        raise AgentAPIError("Forbidden.", 403, "forbidden")

# 前端代理（tagentnote/vite.config.ts）给它转发的每个请求都盖上这个头。代理是用自己的值
# 覆盖客户端发来的同名头，所以客户端去不掉它：带着它，就说明请求是从前端端口进来的——
# 开了 --lan 时，那可能是局域网里的任何人。
FRONTEND_PROXY_HEADER = "X-Tagent-Via-Frontend"


def require_direct_caller() -> None:
    """只许本机直连的程序调用（例如 OpenNotebook 直连 5001），不许经前端端口进来。"""
    if FRONTEND_PROXY_HEADER in request.headers:
        raise AgentAPIError(
            "This channel is only for programs on this machine that call basic-agent directly.",
            403,
            "direct_callers_only",
        )


def require_internal_token() -> None:
    expected = current_app.config.get("AGENT_INTERNAL_TOKEN", "")
    if not expected:
        raise AgentAPIError(
            "The internal agent channel is unavailable because its token is not configured.",
            503,
            "internal_token_not_configured",
        )
    provided = request.headers.get("X-Agent-Internal-Token", "")
    if not provided or not hmac.compare_digest(provided, expected):
        raise AgentAPIError("Forbidden.", 403, "forbidden")

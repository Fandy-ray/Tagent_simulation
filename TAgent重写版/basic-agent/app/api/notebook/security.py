"""口令与跨域，对应原版的 PasswordAuthMiddleware 和 CORSMiddleware。

- 没设口令（ON_PASSWORD / OPEN_NOTEBOOK_PASSWORD）就完全不鉴权，同原版；
- 设了就要 `Authorization: Bearer <口令>`，也认 tagent 一并带的 `X-Password`；
- 放行的路径同原版：/、/health、/api/auth/status、/api/config（再加一个 /api/health）。
"""

from __future__ import annotations

import secrets

from flask import jsonify, request

OPEN_PATHS = {"/", "/health", "/api/health", "/api/auth/status", "/api/config"}
ALLOW_HEADERS = "Authorization, Content-Type, X-Password"
ALLOW_METHODS = "GET, POST, PUT, DELETE, OPTIONS, HEAD"


def _presented_password() -> str:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.headers.get("X-Password", "").strip()


def install_security(app, *, password: str, cors_origins: tuple[str, ...], api_only: bool = False) -> None:
    @app.before_request
    def check_password():
        if not password or request.method == "OPTIONS" or request.path in OPEN_PATHS:
            return None
        # 挂在 basic-agent 上时只守 /api/*，答疑、出卷、管理接口仍走自己的口令。
        if api_only and not request.path.startswith("/api/"):
            return None
        if secrets.compare_digest(_presented_password().encode(), password.encode()):
            return None
        response = jsonify({"detail": "Missing or invalid authorization"})
        response.status_code = 401
        response.headers["WWW-Authenticate"] = "Bearer"
        return response

    @app.after_request
    def add_cors(response):
        if api_only and not request.path.startswith("/api/"):
            return response
        origin = request.headers.get("Origin", "")
        if "*" in cors_origins:
            response.headers["Access-Control-Allow-Origin"] = "*"
        elif origin and origin in cors_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers.add("Vary", "Origin")
        else:
            return response
        # 同原版 CORSMiddleware(allow_headers=["*"])：预检要什么头就放什么头。
        # 前端直连后端时会带 Cache-Control 等头，只放固定几个会被浏览器拦下（实测登录页报连不上）。
        requested = request.headers.get("Access-Control-Request-Headers", "").strip()
        response.headers["Access-Control-Allow-Headers"] = requested or ALLOW_HEADERS
        response.headers["Access-Control-Allow-Methods"] = ALLOW_METHODS
        if request.method == "OPTIONS":
            response.headers["Access-Control-Max-Age"] = "600"
        return response

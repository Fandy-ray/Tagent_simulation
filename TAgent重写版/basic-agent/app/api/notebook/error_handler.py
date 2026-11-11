"""异常统一转成原版的 `{"detail": "..."}`。"""

from __future__ import annotations

import logging

from flask import jsonify
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from app.errors.notebook import NotebookError

log = logging.getLogger(__name__)


def _detail(message: str, status: int):
    response = jsonify({"detail": message})
    response.status_code = status
    return response


def register_error_handlers(app) -> None:
    @app.errorhandler(NotebookError)
    def handle_notebook_error(error: NotebookError):
        response = _detail(error.detail, error.status)
        if error.status == 401:
            response.headers["WWW-Authenticate"] = "Bearer"
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(_error):
        limit = app.config.get("MAX_CONTENT_LENGTH") or 0
        return _detail(f"File too large（上限 {limit // (1024 * 1024)} MB）", 413)

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        names = {404: "Not Found", 405: "Method Not Allowed"}
        return _detail(names.get(error.code or 500, error.description or "Error"), error.code or 500)

    @app.errorhandler(Exception)
    def handle_unexpected(error: Exception):
        log.exception("未处理的异常：%s", error)
        return _detail("Internal server error", 500)

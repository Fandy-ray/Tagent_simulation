"""@ControllerAdvice：把领域异常翻译成统一的错误响应体。

从启动类里挪出来，create_app 只负责调用 register_error_handlers(app)。
"""

from __future__ import annotations

import logging

from flask import jsonify
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from app.errors.api_errors import AgentAPIError
from app.errors.exam_errors import ExamServiceError
from app.errors.registry_errors import RegistryLoadError


def error_response(error: AgentAPIError):
    return (
        jsonify(
            {
                "error": {
                    "message": error.message,
                    "type": error.error_type,
                    "code": error.code,
                }
            }
        ),
        error.status,
    )


def register_error_handlers(app) -> None:
    @app.errorhandler(AgentAPIError)
    def handle_agent_error(error):
        return error_response(error)

    @app.errorhandler(ExamServiceError)
    def handle_exam_error(error):
        return error_response(
            AgentAPIError(error.message, error.status_code, error.code)
        )

    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_too_large(_error):
        return error_response(
            AgentAPIError("Request body exceeds the 1 MiB limit.", 413, "request_too_large")
        )

    @app.errorhandler(RegistryLoadError)
    def handle_registry_error(error):
        app.logger.error("Provider registry unavailable: %s", error)
        return error_response(
            AgentAPIError("Model provider configuration is unavailable.", 503, "provider_registry_unavailable")
        )

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        """路径不存在、方法不对这类是请求的问题，不是服务出错：照实回 404/405。

        以前它们落进下面的 Exception 兜底，一律变成 500 internal_error 还记一条 ERROR
        （浏览器打开一个不存在的地址就是一条）。
        """
        status = error.code or 500
        body, _ = error_response(
            AgentAPIError(
                error.description or error.name,
                status,
                error.name.lower().replace(" ", "_"),
                "server_error" if status >= 500 else "invalid_request_error",
            )
        )
        # 405 要带上 Allow，客户端才知道该用哪个方法
        headers = {k: v for k, v in error.get_headers() if k.lower() == "allow"}
        return body, status, headers

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        app.logger.error("Unhandled request failure: %s", type(error).__name__)
        return error_response(
            AgentAPIError("The agent service could not complete the request.", 500, "internal_error", "server_error")
        )

    logging.getLogger("httpx").setLevel(logging.WARNING)

"""业务异常：每种带一个 HTTP 状态码，api 层统一转成原版的 {"detail": "..."}。

对应原版 open_notebook/exceptions.py 的映射：NotFound→404、InvalidInput→400、
请求格式不对→422、Upstream（模型/网络）→502、Unsupported→415；口令不对的 401 由 api/security.py 直接回。
"""

from __future__ import annotations


class NotebookError(Exception):
    status = 500

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class InvalidInput(NotebookError):
    status = 400


class NotFound(NotebookError):
    status = 404


class UnsupportedType(NotebookError):
    status = 415


class ValidationFailed(NotebookError):
    """请求体或参数格式不对（原版 FastAPI 回 422）。"""

    status = 422


class UpstreamFailure(NotebookError):
    status = 502


class ExtractionFailed(NotebookError):
    """抽取不出文字：后台任务里算「永久失败」，不自动重试，用户可以点重试。"""

    status = 400

"""Use a signed loopback request to stop and purge a TAgent account in OpenNotebook."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import BinaryIO
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from app.errors.api_errors import AgentAPIError


class NotebookLifecycle:
    def __init__(self, base_url: str, secret: str,
                 transport: httpx.BaseTransport | None = None) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.port is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("OpenNotebook lifecycle URL must be a loopback HTTP origin")
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("OpenNotebook lifecycle key must have at least 32 bytes")
        self.base_url = base_url.rstrip("/")
        self.secret = secret
        self.transport = transport

    def _request_parts(self, method: str, account_id: str, action: str):
        account = UUID(account_id)
        path = f"/api/internal/accounts/{account}/{action}"
        timestamp = str(int(time.time()))
        message = f"{method}\n{path}\n{timestamp}".encode("utf-8")
        signature = hmac.new(
            self.secret.encode("utf-8"), message, hashlib.sha256
        ).hexdigest()
        return path, {
            "x-tagent-lifecycle-time": timestamp,
            "x-tagent-lifecycle-signature": signature,
        }

    def _call(self, method: str, account_id: str, action: str) -> None:
        path, headers = self._request_parts(method, account_id, action)
        try:
            with httpx.Client(timeout=10, follow_redirects=False, trust_env=False,
                              transport=self.transport) as client:
                response = client.request(
                    method,
                    self.base_url + path,
                    headers=headers,
                )
        except httpx.RequestError as error:
            raise AgentAPIError(
                "笔记本服务暂时不可用，账号保持待完成注销。", 503,
                "notebook_lifecycle_unavailable",
            ) from error
        if response.status_code == 202:
            raise AgentAPIError(
                "笔记本任务尚未结束，账号保持待完成注销。", 503,
                "notebook_cleanup_pending",
            )
        if response.status_code != 200:
            raise AgentAPIError(
                "笔记本数据清理未完成，账号保持待完成注销。", 503,
                "notebook_lifecycle_failed",
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise AgentAPIError(
                "笔记本服务返回内容无效，账号保持待完成注销。", 503,
                "notebook_lifecycle_invalid",
            ) from error
        expected = "disabled" if action == "disable" else "deleted"
        if not isinstance(payload, dict) or payload.get(expected) is not True:
            raise AgentAPIError(
                "笔记本服务未确认清理完成，账号保持待完成注销。", 503,
                "notebook_lifecycle_invalid",
            )

    def disable(self, account_id: str) -> None:
        self._call("POST", account_id, "disable")

    def purge(self, account_id: str) -> None:
        self._call("DELETE", account_id, "purge")

    def download(self, account_id: str, output: BinaryIO) -> None:
        """Copy the server-side account archive into an already-open ZIP member."""
        path, headers = self._request_parts("GET", account_id, "export")
        try:
            with httpx.Client(
                timeout=httpx.Timeout(120, connect=5), follow_redirects=False,
                trust_env=False, transport=self.transport,
            ) as client:
                with client.stream("GET", self.base_url + path, headers=headers) as response:
                    if response.status_code != 200 or not response.headers.get(
                        "content-type", ""
                    ).startswith("application/zip"):
                        raise AgentAPIError(
                            "笔记本数据暂时无法导出。", 503, "notebook_export_unavailable"
                        )
                    size = 0
                    for chunk in response.iter_bytes(64 * 1024):
                        output.write(chunk)
                        size += len(chunk)
                    if size == 0:
                        raise AgentAPIError(
                            "笔记本导出文件为空。", 503, "notebook_export_invalid"
                        )
        except httpx.RequestError as error:
            raise AgentAPIError(
                "笔记本服务暂时不可用，无法导出完整账号数据。", 503,
                "notebook_export_unavailable",
            ) from error

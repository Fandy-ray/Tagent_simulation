"""连上游模型的 HTTP 客户端：能直连就直连，直连不通才走系统代理。

为什么：开发机为了访问 GitHub 常常全局配着 HTTPS_PROXY，以前对所有非本机地址
一律跟着环境变量走代理，国内的模型服务也绕到代理出口再绕回来。2026-10-24 实测
（DeepSeek，本机代理 127.0.0.1:17897）：

                                 走代理      直连
    一段短提示词：首字            2.48s      0.67s
    一段短提示词：单路总耗时       6.84s      1.72s
    同一套出卷流程：整卷中位        9.3s       7.2s
    同时发 8 路                  互相拖慢   每路仍 1.9s

最后一行最要紧：整卷要同时发好几路，走代理时拆得越细越慢；直连后才能拆成七路
同时写（见 app/agent/graphs/exam.py），整卷压到 5 秒以内。

规则：
- 本机地址（127.0.0.1 / localhost / ::1）：直连，不看代理；
- 环境里没配代理，或 NO_PROXY 排除了这台主机：照旧，没什么可选的；
- 配了代理：**先直连**。握手阶段失败（连不上、域名解析不了、握手超时）时请求还没
  发出去，换代理重发是安全的；换完记住这台主机，之后直接走代理，不再每次试直连。
  直连握手只等 UPSTREAM_DIRECT_CONNECT_TIMEOUT 秒，防火墙丢包的网络第一次最多多等这么久。
- 设 UPSTREAM_DIRECT_FIRST=0 回到以前的做法（有代理就一律走代理）。
"""

from __future__ import annotations

import logging
import threading
import urllib.request
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import UPSTREAM_DIRECT_CONNECT_TIMEOUT, UPSTREAM_DIRECT_FIRST

log = logging.getLogger(__name__)

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

# 直连连不上、改走代理的主机。进程内记住即可：网络环境变了重启服务就会重新试。
_proxy_only: set[str] = set()
_lock = threading.Lock()


def is_local(base_url: str) -> bool:
    return (urlparse(base_url).hostname or "").lower() in _LOCAL_HOSTS


def environment_proxy(url: str) -> str | None:
    """这个地址按环境（HTTPS_PROXY / ALL_PROXY / NO_PROXY，macOS 还有系统设置）该走的代理。

    和 httpx 自己的判断用的是同一个来源（urllib.request.getproxies）。
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host or host in _LOCAL_HOSTS:
        return None
    proxies = urllib.request.getproxies()
    proxy = proxies.get(parsed.scheme) or proxies.get("all")
    if not proxy or urllib.request.proxy_bypass(host):
        return None
    return proxy if "://" in proxy else f"http://{proxy}"


def _needs_proxy(host: str) -> bool:
    with _lock:
        return host in _proxy_only


def _remember_proxy(host: str, error: Exception) -> None:
    with _lock:
        if host in _proxy_only:
            return
        _proxy_only.add(host)
    log.warning("直连 %s 失败（%s），之后改走系统代理", host, type(error).__name__)


def _short_connect(request: httpx.Request) -> dict[str, Any]:
    """直连那一次的握手限时收短；返回原来的 extensions，换代理重发前要还原。"""
    original = request.extensions
    timeout = dict(original.get("timeout") or {})
    connect = timeout.get("connect")
    timeout["connect"] = (
        UPSTREAM_DIRECT_CONNECT_TIMEOUT if connect is None else min(connect, UPSTREAM_DIRECT_CONNECT_TIMEOUT)
    )
    request.extensions = {**original, "timeout": timeout}
    return original


# 只有这两类是「请求还没发出去」：连接没建起来、或握手超时。读超时、连接中途断开
# 都可能已经把请求发到了上游，重发会让模型白算一遍（还多计一次费），不能换路重试。
_NOT_SENT = (httpx.ConnectError, httpx.ConnectTimeout)


class DirectFirstTransport(httpx.BaseTransport):
    def __init__(
        self,
        proxy_url: str,
        *,
        direct: httpx.BaseTransport | None = None,
        proxied: httpx.BaseTransport | None = None,
    ):
        self._direct = direct or httpx.HTTPTransport()
        self._proxied = proxied or httpx.HTTPTransport(proxy=proxy_url)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if not _needs_proxy(host):
            original = _short_connect(request)
            try:
                return self._direct.handle_request(request)
            except _NOT_SENT as exc:
                _remember_proxy(host, exc)
            finally:
                request.extensions = original
        return self._proxied.handle_request(request)

    def close(self) -> None:
        self._direct.close()
        self._proxied.close()


class AsyncDirectFirstTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        proxy_url: str,
        *,
        direct: httpx.AsyncBaseTransport | None = None,
        proxied: httpx.AsyncBaseTransport | None = None,
    ):
        self._direct = direct or httpx.AsyncHTTPTransport()
        self._proxied = proxied or httpx.AsyncHTTPTransport(proxy=proxy_url)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if not _needs_proxy(host):
            original = _short_connect(request)
            try:
                return await self._direct.handle_async_request(request)
            except _NOT_SENT as exc:
                _remember_proxy(host, exc)
            finally:
                request.extensions = original
        return await self._proxied.handle_async_request(request)

    async def aclose(self) -> None:
        await self._direct.aclose()
        await self._proxied.aclose()


def _proxy_plan(base_url: str) -> tuple[bool, str | None]:
    """(trust_env, 先直连时用的代理地址)。代理地址为 None 就照旧建客户端。"""
    if is_local(base_url):
        return False, None
    proxy = environment_proxy(base_url) if UPSTREAM_DIRECT_FIRST else None
    if proxy is None:
        return True, None
    return False, proxy


def sync_client(base_url: str, **kwargs: Any) -> httpx.Client:
    trust_env, proxy = _proxy_plan(base_url)
    if proxy is None:
        return httpx.Client(trust_env=trust_env, **kwargs)
    return httpx.Client(trust_env=False, transport=DirectFirstTransport(proxy), **kwargs)


def async_client(base_url: str, **kwargs: Any) -> httpx.AsyncClient:
    trust_env, proxy = _proxy_plan(base_url)
    if proxy is None:
        return httpx.AsyncClient(trust_env=trust_env, **kwargs)
    return httpx.AsyncClient(trust_env=False, transport=AsyncDirectFirstTransport(proxy), **kwargs)

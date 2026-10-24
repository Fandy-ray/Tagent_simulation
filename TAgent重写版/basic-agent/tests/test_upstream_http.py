"""连上游模型：配着代理时先直连，直连连不上才走代理。"""

from __future__ import annotations

import asyncio
import urllib.request

import httpx
import pytest

from app.infra import upstream_http
from app.infra.upstream_http import (
    AsyncDirectFirstTransport,
    DirectFirstTransport,
    environment_proxy,
)

URL = "https://api.deepseek.com/chat/completions"


@pytest.fixture(autouse=True)
def _forget_hosts():
    upstream_http._proxy_only.clear()
    yield
    upstream_http._proxy_only.clear()


class Recorder:
    """记下每一路收到的请求和那时的握手限时，按脚本回应或抛错。"""

    def __init__(self, error: Exception | None = None):
        self.error = error
        self.connect_timeouts: list[float | None] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.connect_timeouts.append((request.extensions.get("timeout") or {}).get("connect"))
        if self.error is not None:
            raise self.error
        return httpx.Response(200, json={"ok": True})

    @property
    def calls(self) -> int:
        return len(self.connect_timeouts)


def client_with(direct: Recorder, proxied: Recorder) -> httpx.Client:
    transport = DirectFirstTransport(
        "http://127.0.0.1:9", direct=httpx.MockTransport(direct), proxied=httpx.MockTransport(proxied)
    )
    return httpx.Client(transport=transport, timeout=httpx.Timeout(90, connect=10))


def refused() -> httpx.ConnectError:
    return httpx.ConnectError("connection refused")


# ====================== 先直连 ======================


def test_direct_works_so_the_proxy_is_never_used():
    direct, proxied = Recorder(), Recorder()
    assert client_with(direct, proxied).post(URL).status_code == 200
    assert (direct.calls, proxied.calls) == (1, 0)


def test_direct_handshake_is_cut_short_but_the_proxy_gets_the_full_timeout():
    # 防火墙丢包的网络，第一次最多多等 UPSTREAM_DIRECT_CONNECT_TIMEOUT 秒
    direct, proxied = Recorder(refused()), Recorder()
    client_with(direct, proxied).post(URL)
    assert direct.connect_timeouts == [upstream_http.UPSTREAM_DIRECT_CONNECT_TIMEOUT]
    assert proxied.connect_timeouts == [10]


@pytest.mark.parametrize("error", [refused(), httpx.ConnectTimeout("handshake timed out")])
def test_a_failed_handshake_falls_back_to_the_proxy_and_is_remembered(error):
    direct, proxied = Recorder(error), Recorder()
    client = client_with(direct, proxied)
    assert client.post(URL).status_code == 200
    assert client.post(URL).status_code == 200
    # 第二次直接走代理，不再每次都先试一遍直连
    assert (direct.calls, proxied.calls) == (1, 2)


def test_an_error_after_the_request_went_out_is_not_retried_through_the_proxy():
    # 读超时时请求可能已经发到上游：换路重发会让模型白算一遍、多计一次费
    direct, proxied = Recorder(httpx.ReadTimeout("slow")), Recorder()
    with pytest.raises(httpx.ReadTimeout):
        client_with(direct, proxied).post(URL)
    assert proxied.calls == 0


def test_the_async_client_does_the_same():
    direct, proxied = Recorder(refused()), Recorder()

    async def handler_direct(request):
        return direct(request)

    async def handler_proxied(request):
        return proxied(request)

    async def run():
        transport = AsyncDirectFirstTransport(
            "http://127.0.0.1:9",
            direct=httpx.MockTransport(handler_direct),
            proxied=httpx.MockTransport(handler_proxied),
        )
        async with httpx.AsyncClient(transport=transport) as client:
            return [(await client.post(URL)).status_code for _ in range(2)]

    assert asyncio.run(run()) == [200, 200]
    assert (direct.calls, proxied.calls) == (1, 2)


# ====================== 找代理 ======================


def test_the_proxy_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "127.0.0.1:17897")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    assert environment_proxy(URL) == "http://127.0.0.1:17897"


def test_no_proxy_excludes_the_host(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:17897")
    monkeypatch.setenv("NO_PROXY", "localhost,api.deepseek.com")
    assert environment_proxy(URL) is None


def test_local_models_never_go_through_a_proxy(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:17897")
    assert environment_proxy("http://127.0.0.1:11434/v1") is None


def test_without_any_proxy_the_client_is_built_as_before(monkeypatch):
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})
    client = upstream_http.sync_client(URL)
    assert not isinstance(client._transport, DirectFirstTransport)


def test_with_a_proxy_the_client_tries_direct_first(monkeypatch):
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {"https": "http://127.0.0.1:17897"})
    monkeypatch.setattr(urllib.request, "proxy_bypass", lambda host: False)
    assert isinstance(upstream_http.sync_client(URL)._transport, DirectFirstTransport)
    assert isinstance(upstream_http.async_client(URL)._transport, AsyncDirectFirstTransport)


def test_the_switch_restores_the_old_behaviour(monkeypatch):
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {"https": "http://127.0.0.1:17897"})
    monkeypatch.setattr(urllib.request, "proxy_bypass", lambda host: False)
    monkeypatch.setattr(upstream_http, "UPSTREAM_DIRECT_FIRST", False)
    client = upstream_http.sync_client(URL)
    assert not isinstance(client._transport, DirectFirstTransport)
    assert client._trust_env is True


def test_the_model_client_uses_direct_first_for_both_sync_and_async(monkeypatch):
    # 出题判卷走的是 ainvoke：以前只给了同步客户端，异步那边由 SDK 自建、跟着环境变量走代理
    from app.infra.model_client_factory import ModelClientFactory
    from tests.test_essay_service import TEST_PROVIDER

    monkeypatch.setattr(urllib.request, "getproxies", lambda: {"https": "http://127.0.0.1:17897"})
    monkeypatch.setattr(urllib.request, "proxy_bypass", lambda host: False)
    client = ModelClientFactory().get(TEST_PROVIDER)
    assert isinstance(client.http_client._transport, DirectFirstTransport)
    assert isinstance(client.http_async_client._transport, AsyncDirectFirstTransport)

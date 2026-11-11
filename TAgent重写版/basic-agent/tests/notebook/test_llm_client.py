"""模型客户端：OpenAI 兼容格式解析、思考内容剥离、偶发错误重试、失败时的提示。"""

from __future__ import annotations

import httpx
import pytest

from app.errors.notebook import UpstreamFailure
from app.infra.notebook.llm_client import LLMClient


def _client(handler, **kwargs) -> LLMClient:
    return LLMClient("http://127.0.0.1:5001/v1/raw", transport=httpx.MockTransport(handler), backoff=0, **kwargs)


def _ok(text: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


def test_complete_parses_and_strips_thinking():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["body"] = request.read()
        return _ok("<think>草稿</think>最终答案")

    llm = _client(handler, model="deepseek", api_key="k")
    assert llm.complete([{"role": "user", "content": "hi"}]) == "最终答案"
    assert seen["url"] == "http://127.0.0.1:5001/v1/raw/chat/completions"
    assert b'"model":"deepseek"' in seen["body"].replace(b" ", b"")


def test_retries_transient_gateway_errors():
    calls = []

    def handler(request):
        calls.append(1)
        return _ok("好了") if len(calls) == 3 else httpx.Response(502, json={"error": {"message": "证书校验失败"}})

    assert _client(handler).complete([{"role": "user", "content": "x"}]) == "好了"
    assert len(calls) == 3


def test_gives_up_with_upstream_message():
    def handler(request):
        return httpx.Response(502, json={"error": {"message": "无法校验上游的 HTTPS 证书"}})

    with pytest.raises(UpstreamFailure) as info:
        _client(handler, retries=1).complete([{"role": "user", "content": "x"}])
    assert "502" in info.value.detail and "证书" in info.value.detail


def test_client_errors_are_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(400, json={"detail": "bad request"})

    with pytest.raises(UpstreamFailure):
        _client(handler).complete([{"role": "user", "content": "x"}])
    assert len(calls) == 1


def test_connection_refused_is_retried_then_reported():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(UpstreamFailure) as info:
        _client(handler).complete([{"role": "user", "content": "x"}])
    assert len(calls) == 3 and "连不上" in info.value.detail


def test_bad_payload_and_empty_answer():
    with pytest.raises(UpstreamFailure):
        _client(lambda r: httpx.Response(200, json={"nope": 1})).complete([{"role": "user", "content": "x"}])
    with pytest.raises(UpstreamFailure):
        _client(lambda r: _ok("<think>只有思考</think>")).complete([{"role": "user", "content": "x"}])

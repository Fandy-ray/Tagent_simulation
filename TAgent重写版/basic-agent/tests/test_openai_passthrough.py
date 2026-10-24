"""透传通道 /v1/raw 的行为约定。

这里钉住的核心事实是：**它不做检索注入**。
/v1/chat/completions 会把课程教材塞进 prompt，OpenNotebook 拿它做摘要会跑偏；
/v1/raw/chat/completions 必须原样转发。这条一旦被改坏，OpenNotebook 那头
表现为"总结出来的东西里混进了系统仿真教材"，很难反查到这里，所以用测试焊死。
"""

from __future__ import annotations

import json
import gzip

import httpx
import pytest

from app.infra import passthrough_client
from app.schema.provider import ModelProvider


def make_provider(**overrides) -> ModelProvider:
    fields = {
        "name": "DeepSeek",
        "served_model_id": "deepseek",
        "base_url": "https://api.deepseek.com",
        "upstream_model": "deepseek-chat",
        "auth_mode": "bearer",
        "api_key": "sk-test",
        "temperature": 0.1,
    }
    fields.update(overrides)
    return ModelProvider(**fields)


class TestBuildPayload:
    def test_adds_registered_extra_body_without_overriding_the_caller(self):
        """登记的厂商参数（例如关闭思考）也要透传过去；调用方自己写了同名字段的，听调用方的。"""
        provider = make_provider(
            extra_body={"thinking": {"type": "disabled"}, "top_k": 5}
        )
        payload = passthrough_client.build_payload(
            {"model": "deepseek", "messages": [], "top_k": 9}, provider
        )
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["top_k"] == 9
        assert "thinking" not in passthrough_client.build_payload(
            {"model": "deepseek", "messages": []}, make_provider()
        )

    def test_swaps_served_id_for_upstream_model(self):
        """客户端报 served_model_id，上游只认 upstream_model。"""
        payload = passthrough_client.build_payload(
            {"model": "deepseek", "messages": []}, make_provider()
        )
        assert payload["model"] == "deepseek-chat"

    def test_drops_tagent_only_fields(self):
        """notebook_ids 是 TAgent 的扩展字段，上游会因为不认识而报 400。"""
        payload = passthrough_client.build_payload(
            {"model": "deepseek", "messages": [], "notebook_ids": ["nb:1"]},
            make_provider(),
        )
        assert "notebook_ids" not in payload

    def test_forwards_arbitrary_openai_fields(self):
        """透传的意义就在于 tools / response_format 这些字段能原样带过去。"""
        payload = passthrough_client.build_payload(
            {
                "model": "deepseek",
                "messages": [],
                "tools": [{"type": "function"}],
                "response_format": {"type": "json_object"},
                "temperature": 0.7,
            },
            make_provider(),
        )
        assert payload["tools"] == [{"type": "function"}]
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["temperature"] == 0.7

    def test_does_not_mutate_caller_payload(self):
        original = {"model": "deepseek", "messages": [], "notebook_ids": ["nb:1"]}
        passthrough_client.build_payload(original, make_provider())
        assert original["model"] == "deepseek"
        assert original["notebook_ids"] == ["nb:1"]


class TestBuildHeaders:
    def test_bearer_mode_sends_key(self):
        headers = passthrough_client.build_headers(make_provider())
        assert headers["Authorization"] == "Bearer sk-test"

    def test_none_mode_omits_authorization(self):
        """auth_mode=none 的本地模型（Ollama / LM Studio）不能带 Authorization。"""
        headers = passthrough_client.build_headers(
            make_provider(auth_mode="none", api_key="")
        )
        assert "Authorization" not in headers


class TestPassthroughRoute:
    """走 Flask 测试客户端，确认请求真的原样落到上游、且没有检索注入。"""

    def test_forwards_messages_verbatim(self, client, monkeypatch, registered_provider):
        seen = {}

        def fake_complete(data, provider, **kwargs):
            seen["data"] = data
            seen["provider"] = provider
            body = json.dumps(
                {
                    "id": "chatcmpl-1",
                    "object": "chat.completion",
                    "choices": [
                        {"index": 0, "message": {"role": "assistant", "content": "ok"}}
                    ],
                }
            ).encode()
            return 200, body, "application/json"

        monkeypatch.setattr(passthrough_client, "complete", fake_complete)

        sent = [{"role": "user", "content": "把这段话总结成三句"}]
        response = client.post(
            "/v1/raw/chat/completions",
            json={"model": "deepseek", "messages": sent},
        )

        assert response.status_code == 200
        # 关键断言：messages 一字未改，没有任何检索出来的教材内容被塞进去
        assert seen["data"]["messages"] == sent
        assert len(seen["data"]["messages"]) == 1

    def test_relays_upstream_status_code(self, client, monkeypatch, registered_provider):
        """上游 401 就该原样是 401，不能被翻译成 502 —— 否则那头没法排查。"""

        def fake_complete(data, provider, **kwargs):
            return 401, b'{"error":{"message":"bad key"}}', "application/json"

        monkeypatch.setattr(passthrough_client, "complete", fake_complete)

        response = client.post(
            "/v1/raw/chat/completions",
            json={"model": "deepseek", "messages": []},
        )
        assert response.status_code == 401

    def test_streams_upstream_bytes(self, client, monkeypatch, registered_provider):
        def fake_stream(data, provider, **kwargs):
            assert data.get("stream") is True

            def generate():
                yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
                yield b"data: [DONE]\n\n"

            return generate()

        monkeypatch.setattr(passthrough_client, "stream", fake_stream)

        response = client.post(
            "/v1/raw/chat/completions",
            json={"model": "deepseek", "messages": [], "stream": True},
        )
        assert response.status_code == 200
        assert response.mimetype == "text/event-stream"
        assert b"[DONE]" in response.get_data()

    def test_models_list_matches_registry(self, client, registered_provider):
        """两条通道共用一份注册表 —— 这就是"统一配置"落地的地方。"""
        raw = client.get("/v1/raw/models").get_json()
        rag = client.get("/v1/models").get_json()
        assert [m["id"] for m in raw["data"]] == [m["id"] for m in rag["data"]]

    def test_unknown_model_is_rejected(self, client, registered_provider):
        response = client.post(
            "/v1/raw/chat/completions",
            json={"model": "not-registered", "messages": []},
        )
        assert response.status_code == 404


class TestTransportErrors:
    def test_timeout_maps_to_504(self):
        error = passthrough_client.translate_transport_error(
            httpx.TimeoutException("timed out")
        )
        assert error.status == 504

    def test_connect_error_maps_to_502(self):
        error = passthrough_client.translate_transport_error(
            httpx.ConnectError("refused")
        )
        assert error.status == 502

    def test_tls_failure_says_so_in_chinese(self):
        """证书问题在国内网络下很常见，错误信息要能直接看懂。"""
        error = passthrough_client.translate_transport_error(
            httpx.ConnectError("CERTIFICATE_VERIFY_FAILED")
        )
        assert "证书" in error.message


@pytest.mark.parametrize("compressed", [False, True])
def test_stream_decodes_content_encoding_and_releases_client(monkeypatch, compressed):
    expected = b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n'
    encoded = gzip.compress(expected) if compressed else expected

    class Pieces(httpx.SyncByteStream):
        closed = False

        def __iter__(self):
            for offset in range(0, len(encoded), 7):
                yield encoded[offset:offset + 7]

        def close(self):
            self.closed = True

    pieces = Pieces()
    upstream = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, headers={"Content-Encoding": "gzip"} if compressed else {}, stream=pieces,
    )))
    monkeypatch.setattr(passthrough_client, "_open_client", lambda *args: upstream)
    assert b"".join(passthrough_client.stream({"messages": []}, make_provider())) == expected
    assert pieces.closed and upstream.is_closed


def test_closing_stream_early_releases_upstream(monkeypatch):
    class Pieces(httpx.SyncByteStream):
        closed = False

        def __iter__(self):
            yield b"data: first\n\n"
            yield b"data: second\n\n"

        def close(self):
            self.closed = True

    pieces = Pieces()
    upstream = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=pieces)))
    monkeypatch.setattr(passthrough_client, "_open_client", lambda *args: upstream)
    stream = passthrough_client.stream({"messages": []}, make_provider())
    assert next(stream) == b"data: first\n\n"
    stream.close()
    assert pieces.closed and upstream.is_closed


class TestOnlyDirectCallers:
    """透传通道不经前端端口开放。

    前端代理给它转发的每个请求都盖上 FRONTEND_PROXY_HEADER（客户端去不掉）。开了 --lan 时
    前端端口对整个局域网开着，不拦的话谁都能拿登记的 Key 当通用大模型接口用。
    """

    VIA_FRONTEND = {"X-Tagent-Via-Frontend": "1"}

    def test_chat_through_the_frontend_proxy_is_refused(self, client, monkeypatch, registered_provider):
        called = []
        monkeypatch.setattr(passthrough_client, "complete", lambda *a, **k: called.append(a))
        response = client.post(
            "/v1/raw/chat/completions",
            json={"model": "deepseek", "messages": [{"role": "user", "content": "hi"}]},
            headers=self.VIA_FRONTEND,
        )
        assert response.status_code == 403
        assert response.get_json()["error"]["code"] == "direct_callers_only"
        assert called == [], "被拒的请求不该再发到上游"

    def test_any_value_of_the_header_counts(self, client, registered_provider):
        # 只看有没有，不看值：代理总会盖上它，客户端自己写个 0 也去不掉
        response = client.get("/v1/raw/models", headers={"X-Tagent-Via-Frontend": "0"})
        assert response.status_code == 403

    def test_direct_callers_still_get_through(self, client, registered_provider):
        assert client.get("/v1/raw/models").status_code == 200


class TestAdminProbe:
    """登记页的「测试连接」：要管理口令，只发一句固定的话。"""

    TOKEN = {"X-Agent-Admin-Token": "admin-token"}

    @pytest.fixture
    def admin_client(self, registry):
        from app.factory import create_app
        from tests.conftest import FakeServices

        app = create_app(
            {"TESTING": True, "AGENT_ADMIN_TOKEN": "admin-token"},
            registry=registry,
            services=FakeServices(),
        )
        return app.test_client()

    @pytest.fixture
    def upstream(self, monkeypatch):
        seen = {}

        def fake_complete(data, provider, **kwargs):
            seen.update(data=data, provider=provider, kwargs=kwargs)
            return 200, b'{"choices":[{"message":{"content":"\\u597d"}}]}', "application/json"

        monkeypatch.setattr(passthrough_client, "complete", fake_complete)
        return seen

    def test_needs_the_admin_token(self, admin_client, upstream, registered_provider):
        response = admin_client.post("/admin/model-providers/deepseek/probe")
        assert response.status_code == 403
        assert upstream == {}

    def test_sends_only_the_fixed_short_message(self, admin_client, upstream, registered_provider):
        # 调用方塞什么都不转：这里不是另一条通用转发
        response = admin_client.post(
            "/admin/model-providers/deepseek/probe",
            json={"messages": [{"role": "user", "content": "写一万字"}], "max_tokens": 99999},
            headers=self.TOKEN,
        )
        assert response.status_code == 200
        assert upstream["data"]["max_tokens"] == 64
        assert upstream["data"]["messages"] == [{"role": "user", "content": "只回复一个字：好"}]
        assert set(upstream["data"]) == {"model", "messages", "max_tokens"}
        assert upstream["kwargs"]["timeout"] < 60, "前端 60 秒就放弃了，后端不该等得更久"

    def test_works_through_the_frontend_proxy(self, admin_client, upstream, registered_provider):
        # 登记页就是从前端端口来的；有管理口令就行
        response = admin_client.post(
            "/admin/model-providers/deepseek/probe",
            headers={**self.TOKEN, "X-Tagent-Via-Frontend": "1"},
        )
        assert response.status_code == 200

    def test_relays_the_upstream_status(self, admin_client, monkeypatch, registered_provider):
        monkeypatch.setattr(
            passthrough_client, "complete", lambda *a, **k: (401, b'{"error":{"message":"bad key"}}', "application/json")
        )
        response = admin_client.post("/admin/model-providers/deepseek/probe", headers=self.TOKEN)
        assert response.status_code == 401
        assert response.get_json()["error"]["message"] == "bad key"
        assert response.headers.get("X-Tagent-Upstream") == "1"

    def test_own_refusals_are_not_marked_as_upstream(self, admin_client, upstream, registered_provider):
        # 口令不对、模型没登记是这边拦的，不能让前端当成「上游拒了 Key」
        assert "X-Tagent-Upstream" not in admin_client.post("/admin/model-providers/deepseek/probe").headers
        missing = admin_client.post("/admin/model-providers/nope/probe", headers=self.TOKEN)
        assert "X-Tagent-Upstream" not in missing.headers

    def test_unknown_model_is_404(self, admin_client, upstream, registered_provider):
        response = admin_client.post("/admin/model-providers/nope/probe", headers=self.TOKEN)
        assert response.status_code == 404

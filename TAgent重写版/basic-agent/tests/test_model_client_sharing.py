"""同一个模型的几个客户端（答疑、出卷、判卷……各要各的超时）不能互相踢。

以前缓存未命中时会关掉这个模型的所有客户端。答疑是同步流式读的：别人新建一个
不同超时的客户端，正在出的回答就被关了连接，卡住不动、也不报错。
这里用本地假上游复现，不连网。
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.infra.model_client_factory import ModelClientFactory
from app.schema.provider import ModelProvider

TOKENS = 10


class SlowStream(BaseHTTPRequestHandler):
    """每隔一小会儿吐一个字，模拟正在出的回答。"""

    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def send(text: str) -> None:
            raw = text.encode()
            self.wfile.write(f"{len(raw):x}\r\n".encode() + raw + b"\r\n")
            self.wfile.flush()

        try:
            for i in range(TOKENS):
                chunk = {"id": "x", "object": "chat.completion.chunk", "created": 0, "model": "m",
                         "choices": [{"index": 0, "delta": {"content": f"t{i}"}, "finish_reason": None}]}
                send(f"data: {json.dumps(chunk)}\n\n")
                time.sleep(0.05)
            send("data: [DONE]\n\n")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


@pytest.fixture
def upstream():
    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowStream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


def make_provider(base_url: str, updated_at: str = "2026-10-25T00:00:00Z") -> ModelProvider:
    return ModelProvider(
        name="fake", served_model_id="fake", base_url=base_url, upstream_model="m",
        auth_mode="none", api_key="", temperature=0.1,
        created_at="2026-10-25T00:00:00Z", updated_at=updated_at,
    )


def test_a_streaming_answer_survives_another_request_with_a_different_timeout(upstream):
    factory = ModelClientFactory()
    provider = make_provider(upstream)
    chat = factory.get(provider)  # 答疑：默认超时
    received: list[str] = []

    def answer():
        for piece in chat.stream("hi"):
            if piece.content:
                received.append(piece.content)

    reader = threading.Thread(target=answer, daemon=True)
    reader.start()
    time.sleep(0.2)  # 回答出到一半
    factory.get(provider, timeout_seconds=55, max_retries=0)  # 有人交卷：判卷要另一个超时
    reader.join(timeout=5)
    assert not reader.is_alive(), f"回答卡住了，只收到 {len(received)}/{TOKENS} 个字"
    assert len(received) == TOKENS
    factory.close()


def test_clients_with_different_timeouts_coexist(upstream):
    factory = ModelClientFactory()
    provider = make_provider(upstream)
    chat = factory.get(provider)
    grading = factory.get(provider, timeout_seconds=55, max_retries=0)
    assert factory.get(provider) is chat, "答疑的客户端被判卷的挤掉了"
    assert factory.get(provider, timeout_seconds=55, max_retries=0) is grading
    factory.close()


def test_a_changed_registration_still_replaces_the_old_client(upstream):
    # 登记信息改了（换了 Key、地址），旧配置的客户端照旧要丢掉
    factory = ModelClientFactory()
    old = factory.get(make_provider(upstream))
    new = factory.get(make_provider(upstream, updated_at="2026-10-25T01:00:00Z"))
    assert new is not old
    assert factory.get(make_provider(upstream, updated_at="2026-10-25T01:00:00Z")) is new
    assert len(factory._clients) == 1, "旧配置的客户端还留在缓存里"
    factory.close()

"""上游卡住和上游慢，要分得开（app/agent/nodes.py json_call）。

用真的 ChatOpenAI 客户端连本地假上游（不连网），卡住的阈值调成 0.4 秒：
- 卡住（一个字节都不发）：阈值一到就放弃这一次、重试，不用等满单次上限；
- 慢但一直在发（先思考的模型就是这样）：不算卡住，等它写完；
- 一直在发、但超过单次总上限：照旧截断，不重试。
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pydantic import BaseModel

from app.agent import nodes
from app.agent.runtime import AgentDeps
from app.errors.exam_errors import UpstreamTimeoutError
from app.infra.model_client_factory import ModelClientFactory
from app.schema.provider import ModelProvider

STALL = 0.4


class Answer(BaseModel):
    value: str


def make_handler(script):
    """script：每个请求依次取一项——"hang_before"（不回响应头）、"hang_after"（回了头就不动）、
    ("slow", 间隔秒数, 段数)（一直在发、但每段隔一会儿）、"ok"（正常回）。"""
    lock = threading.Lock()
    served = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            with lock:
                step = script[min(len(served), len(script) - 1)]
                served.append(step)
            if step == "hang_before":
                time.sleep(3)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            def send(text):
                raw = text.encode()
                self.wfile.write(f"{len(raw):x}\r\n".encode() + raw + b"\r\n")
                self.wfile.flush()

            def piece(content):
                chunk = {"id": "x", "object": "chat.completion.chunk", "created": 0, "model": "m",
                         "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}]}
                send(f"data: {json.dumps(chunk)}\n\n")

            try:
                if step == "hang_after":
                    piece("{")
                    time.sleep(3)
                    return
                if isinstance(step, tuple):
                    _, gap, count = step
                    for _ in range(count):
                        piece(" ")
                        time.sleep(gap)
                piece('{"value": "ok"}')
                send("data: [DONE]\n\n")
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler, served


@pytest.fixture
def upstream(monkeypatch):
    monkeypatch.setattr(nodes, "UPSTREAM_STALL_SECONDS", STALL)
    servers = []

    def start(script):
        handler, served = make_handler(script)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        provider = ModelProvider(
            name="fake", served_model_id="fake", base_url=f"http://127.0.0.1:{server.server_port}/v1",
            upstream_model="m", auth_mode="none", api_key="", temperature=0.1,
        )
        deps = AgentDeps.start(knowledge_base=None, client_factory=ModelClientFactory(),
                               provider=provider, budget_seconds=60)
        return deps, served

    yield start
    for server in servers:
        server.shutdown()


def call(deps, limit=30.0):
    started = time.monotonic()
    result = nodes.json_call(deps, "出题", Answer, max_tokens=100, limit=limit, floor=0.5)
    return result, time.monotonic() - started


def test_an_upstream_that_stops_mid_stream_is_retried_without_waiting_out_the_cap(upstream):
    deps, served = upstream(["hang_after", "ok"])
    result, took = call(deps)
    assert result.value == "ok"
    assert served == ["hang_after", "ok"]
    assert took < 2.5, f"等了 {took:.1f} 秒：卡住检测没起作用，在等单次上限"


def test_an_upstream_that_never_answers_is_retried_too(upstream):
    deps, served = upstream(["hang_before", "ok"])
    result, took = call(deps)
    assert result.value == "ok"
    assert served == ["hang_before", "ok"]
    assert took < 2.5


def test_slow_but_alive_is_not_a_stall(upstream):
    # 每段隔 0.25 秒（小于阈值 0.4），一共 1.5 秒（超过阈值好几倍）：这是慢，不是卡
    deps, served = upstream([("slow", 0.25, 6)])
    result, took = call(deps)
    assert result.value == "ok"
    assert len(served) == 1, "慢模型被当成卡住重试了"
    assert took >= 1.4


def test_alive_past_the_attempt_cap_is_cut_and_not_retried(upstream):
    deps, served = upstream([("slow", 0.25, 20)])
    with pytest.raises(UpstreamTimeoutError):
        call(deps, limit=1.0)
    assert len(served) == 1, "一直在写、只是慢：再来一次照样慢，不该重试"

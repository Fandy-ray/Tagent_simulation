"""门口的闸门：答疑满了排队、排队不超过这次运行的截止时间、学生停下就把名额还回来。

2026-10-30 在 2 核 2G 的服务器上压测：不限的话 100 人同时提问，后端内存涨到 1G 被系统杀掉。
"""

from __future__ import annotations

import tempfile
import threading
import time
import types
from pathlib import Path

import pytest

from app.container import Services
from app.errors.api_errors import AgentAPIError
from app.errors.exam_errors import ExamBusyError
from app.factory import create_app
from app.repository.exam_cache import LLMGate
from app.repository.provider_repository import ModelProviderRegistry
from app.service.chat_service import ChatService

PROVIDER = types.SimpleNamespace(served_model_id="m")
MESSAGES = [{"role": "user", "content": "什么是排队论？"}]


# ====================== 闸门排队不超过截止时间 ======================


def test_queueing_stops_in_time_to_leave_room_for_the_run():
    gate = LLMGate(max_concurrent=1, wait_seconds=30, max_waiting=5, min_run_seconds=1)
    with gate.acquire():
        started = time.monotonic()
        with pytest.raises(ExamBusyError, match="排了 1 秒"):
            with gate.acquire(deadline=time.monotonic() + 1.6):  # 只能排 0.6 秒
                pass
        assert time.monotonic() - started < 2


def test_no_queueing_when_the_deadline_leaves_no_room():
    gate = LLMGate(max_concurrent=1, wait_seconds=30, max_waiting=5, min_run_seconds=20)
    with gate.acquire():
        started = time.monotonic()
        with pytest.raises(ExamBusyError, match="人太多，请稍后再试"):
            with gate.acquire(deadline=time.monotonic() + 10):
                pass
        assert time.monotonic() - started < 0.5


def test_without_a_deadline_the_full_wait_applies():
    gate = LLMGate(max_concurrent=1, wait_seconds=0.3, max_waiting=5)
    got = []
    with gate.acquire():

        def later():
            with gate.acquire(deadline=float("inf")):
                got.append(True)

        worker = threading.Thread(target=later)
        worker.start()
        time.sleep(0.1)
    worker.join(2)
    assert got == [True]


# ====================== 答疑在门口排队 ======================


class OneWordKB:
    def __init__(self):
        self.queries: list[str] = []

    def retrieve(self, query, notebook_ids=None):
        self.queries.append(query)
        return "材料", []


class TwoChunks:
    def stream(self, _messages):
        yield types.SimpleNamespace(content="到达率", response_metadata={})
        yield types.SimpleNamespace(content="是λ", response_metadata={"finish_reason": "stop"})


class Factory:
    def get(self, _provider, **_kwargs):
        return TwoChunks()


def service(gate):
    return ChatService(OneWordKB(), Factory(), answer_gate=gate)


def test_answers_beyond_the_limit_wait_at_the_door():
    chat = service(LLMGate(max_concurrent=1, wait_seconds=5, max_waiting=5))
    first = chat.stream_answer(MESSAGES, PROVIDER)
    assert next(first) == ("到达率", None)  # 第一个正在答，占着名额
    done = threading.Event()

    def second():
        list(chat.stream_answer(MESSAGES, PROVIDER))
        done.set()

    threading.Thread(target=second).start()
    time.sleep(0.2)
    assert not done.is_set() and len(chat.knowledge_base.queries) == 1, "第二个应该还在门口，连检索都没开始"
    list(first)  # 第一个答完
    assert done.wait(2) and len(chat.knowledge_base.queries) == 2


def test_stopping_an_answer_gives_the_slot_back_at_once():
    chat = service(LLMGate(max_concurrent=1, wait_seconds=0.2, max_waiting=5))
    first = chat.stream_answer(MESSAGES, PROVIDER)
    next(first)
    first.close()  # 学生点了「停止」
    assert list(chat.stream_answer(MESSAGES, PROVIDER))[-1] == ("", "stop")


def test_without_a_gate_answers_are_not_limited():
    chat = ChatService(OneWordKB(), Factory())
    streams = [chat.stream_answer(MESSAGES, PROVIDER) for _ in range(3)]
    assert [next(stream) for stream in streams] == [("到达率", None)] * 3


# ====================== 排不上时照实说人太多 ======================


def test_a_stream_that_cannot_get_in_says_too_many_people():
    gate = LLMGate(
        max_concurrent=1,
        busy_error=lambda message: AgentAPIError(message, 429, "answer_busy"),
        what="提问",
    )
    registry = ModelProviderRegistry(Path(tempfile.mkdtemp()) / "providers.json")
    registry.create_provider({
        "name": "m", "served_model_id": "m", "base_url": "http://127.0.0.1:9/v1",
        "upstream_model": "u", "auth_mode": "none", "api_key": "", "enabled": True,
    })
    chat = service(gate)
    services = Services(chat=chat, quiz=None, exam=None, essay=None, knowledge_base=chat.knowledge_base,
                        client_factory=None, store=None)
    client = create_app({"TESTING": True}, registry=registry, services=services).test_client()
    with gate.acquire():  # 名额被别人占着，门口又不让排
        body = client.post("/v1/chat/completions", json={"model": "m", "stream": True, "messages": MESSAGES})
        text = body.get_data(as_text=True)
    assert "同时在提问的人太多" in text
    assert "模型服务出错了" not in text

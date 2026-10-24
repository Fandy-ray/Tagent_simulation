"""对话的 mode 与检索提示：论文模式换 system prompt，检索改用前端给的短检索词。"""

from __future__ import annotations

import types

import pytest

from app.api.validators import MAX_RETRIEVAL_QUERY_CHARS, chat_mode, chat_retrieval_query
from app.errors.api_errors import AgentAPIError
from app.prompts.chat_prompts import build_prompt_messages
from app.service.chat_service import ChatService


PROVIDER = types.SimpleNamespace(served_model_id="test-provider")
MESSAGES = [{"role": "user", "content": "很长的论文任务 prompt……"}]


# ====================== system prompt ======================


def test_qa_prompt_is_unchanged():
    system = build_prompt_messages(MESSAGES, "CTX")[0]["content"]
    assert system.startswith("You are a teaching assistant.")
    assert system.endswith("Reference:\nCTX")


def test_paper_mode_uses_the_writing_assistant_prompt():
    system = build_prompt_messages(MESSAGES, "CTX", mode="paper")[0]["content"]
    assert "论文写作助教" in system
    assert "不要编造" in system
    assert system.endswith("Reference:\nCTX")


# ====================== 校验 ======================


@pytest.mark.parametrize(
    "payload, expected",
    [({}, "qa"), ({"mode": None}, "qa"), ({"mode": ""}, "qa"), ({"mode": "qa"}, "qa"), ({"mode": "paper"}, "paper")],
)
def test_chat_mode_accepts_known_values(payload, expected):
    assert chat_mode(payload) == expected


@pytest.mark.parametrize("value", ["essay", "PAPER", 1])
def test_chat_mode_rejects_anything_else(value):
    with pytest.raises(AgentAPIError) as info:
        chat_mode({"mode": value})
    assert info.value.code == "invalid_mode"
    assert info.value.status == 400


def test_retrieval_query_is_optional():
    assert chat_retrieval_query({}) is None
    assert chat_retrieval_query({"retrieval_query": "   "}) is None


def test_retrieval_query_is_truncated_not_rejected():
    # 它只是个检索提示，题目写长了不该让整次对话失败
    value = chat_retrieval_query({"retrieval_query": "排" * (MAX_RETRIEVAL_QUERY_CHARS + 50)})
    assert value == "排" * MAX_RETRIEVAL_QUERY_CHARS


def test_retrieval_query_must_be_a_string():
    with pytest.raises(AgentAPIError) as info:
        chat_retrieval_query({"retrieval_query": ["排队论"]})
    assert info.value.code == "validation_error"


# ====================== service ======================


class RecordingKB:
    def __init__(self):
        self.queries: list[str] = []

    def retrieve(self, query, notebook_ids=None):
        self.queries.append(query)
        return "⟪材料⟫", []


class RecordingModel:
    def __init__(self):
        self.messages = None

    def stream(self, messages):
        self.messages = messages
        yield types.SimpleNamespace(content="好", response_metadata={"finish_reason": "stop"})

    def invoke(self, messages):
        self.messages = messages
        return types.SimpleNamespace(content="好")


class Factory:
    def __init__(self, model):
        self.model = model

    def get(self, _provider, **_kwargs):
        return self.model


def make(kb, model):
    return ChatService(kb, Factory(model))


def test_stream_searches_with_the_retrieval_query_and_uses_the_paper_prompt():
    kb, model = RecordingKB(), RecordingModel()
    list(make(kb, model).stream_answer(MESSAGES, PROVIDER, mode="paper", retrieval_query="排队论 银行"))
    assert kb.queries == ["排队论 银行"]
    assert "论文写作助教" in model.messages[0]["content"]


def test_stream_falls_back_to_the_last_user_message():
    kb, model = RecordingKB(), RecordingModel()
    list(make(kb, model).stream_answer(MESSAGES, PROVIDER))
    assert kb.queries == [MESSAGES[-1]["content"]]
    assert model.messages[0]["content"].startswith("You are a teaching assistant.")


def test_non_stream_answer_passes_the_mode_through_the_graph():
    kb, model = RecordingKB(), RecordingModel()
    make(kb, model).answer(MESSAGES, PROVIDER, mode="paper", retrieval_query="排队论")
    assert kb.queries == ["排队论"]
    assert "论文写作助教" in model.messages[0]["content"]


def test_a_request_without_user_messages_is_still_rejected():
    # 给了检索提示也不能绕过「至少一条用户消息」
    kb, model = RecordingKB(), RecordingModel()
    with pytest.raises(AgentAPIError):
        list(
            make(kb, model).stream_answer(
                [{"role": "system", "content": "x"}], PROVIDER, retrieval_query="排队论"
            )
        )


# ====================== 流被截断 ======================


class TruncatedModel(RecordingModel):
    """连接中途断开：吐了几个字就结束，没有 finish_reason，也不抛异常（真实客户端实测如此）。"""

    def stream(self, messages):
        self.messages = messages
        yield types.SimpleNamespace(content="到达率是", response_metadata={})


def test_a_stream_that_ends_without_finish_reason_says_it_was_cut_off():
    kb, model = RecordingKB(), TruncatedModel()
    chunks = list(make(kb, model).stream_answer(MESSAGES, PROVIDER))
    text = "".join(token for token, _ in chunks)
    assert text.startswith("到达率是")
    assert "回答中断" in text
    # 内部如实标成「没答完」（学习记录要用）；发给前端时由 openai_view 换回标准的 stop
    assert chunks[-1] == ("", "interrupted")


def test_a_complete_stream_gets_no_interruption_note():
    kb, model = RecordingKB(), RecordingModel()
    text = "".join(token for token, _ in make(kb, model).stream_answer(MESSAGES, PROVIDER))
    assert "回答中断" not in text


@pytest.mark.parametrize("reason", ["stop", "length", "content_filter"])
def test_usage_only_chunk_does_not_erase_the_finish_reason(reason):
    class WithUsage(RecordingModel):
        def stream(self, messages):
            yield types.SimpleNamespace(content="好", response_metadata={"finish_reason": reason})
            yield types.SimpleNamespace(content="", response_metadata={"finish_reason": None})

    chunks = list(make(RecordingKB(), WithUsage()).stream_answer(MESSAGES, PROVIDER))
    assert chunks == [("好", None), ("", reason)]



# ====================== 学生点停止 ======================


class LongModel(RecordingModel):
    """一口气能吐 100 块；记下上游的流有没有被关掉、吐到了第几块。"""

    def __init__(self):
        super().__init__()
        self.sent = 0
        self.closed = False

    def stream(self, messages):
        self.messages = messages
        try:
            for i in range(100):
                self.sent = i + 1
                yield types.SimpleNamespace(content=f"第{i}块", response_metadata={})
            yield types.SimpleNamespace(content="", response_metadata={"finish_reason": "stop"})
        finally:
            self.closed = True


def test_closing_the_stream_closes_the_upstream_stream_right_away():
    """学生点停止（或断开）时，上游的流要立刻断，不能让模型照样生成到底、照样计费。

    这正是逐块生成没放进答疑图的原因：LangGraph 的 stream 在消费方中途关掉时
    会等节点跑完（见 app/agent/graphs/answer.py 开头）。谁把它挪进图里，这里会红。
    """
    model = LongModel()
    stream = make(RecordingKB(), model).stream_answer(MESSAGES, PROVIDER)
    assert next(stream) == ("第0块", None)
    stream.close()
    assert model.closed, "上游的流没被关掉"
    assert model.sent < 5, f"关掉之后上游还在往下吐（吐到了第 {model.sent} 块）"

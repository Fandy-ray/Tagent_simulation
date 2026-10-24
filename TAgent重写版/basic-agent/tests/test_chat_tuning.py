"""对话可调参数：校验、绑定、以及「真的发出去了」。

修的是「高级参数是假开关」：前端把温度、top_p、最大长度发出来，后端却只读
messages / notebook_ids / mode / retrieval_query / stream，学生把温度调到 0 或 2
回答都没变化。
"""

from __future__ import annotations

import types

import pytest

from app.api.validators import MAX_CHAT_MAX_TOKENS, chat_tuning
from app.errors.exam_errors import InvalidExamRequestError
from app.infra.model_client_factory import TUNABLE, tuning_bind_kwargs


def provider(extra_body=None):
    return types.SimpleNamespace(extra_body=extra_body)


# ====================== 校验 ======================


def test_accepts_the_three_supported_knobs():
    assert chat_tuning({"temperature": 0.3, "top_p": 0.9, "max_tokens": 800}) == {
        "temperature": 0.3,
        "top_p": 0.9,
        "max_tokens": 800,
    }


def test_absent_knobs_mean_no_override():
    assert chat_tuning({"model": "m", "messages": []}) == {}


def test_ignores_knobs_the_model_does_not_support():
    # 面板上多出来的开关一律不接：调了没反应比没有这个开关更糟
    assert chat_tuning({"presence_penalty": 1.5, "seed": 42}) == {}


@pytest.mark.parametrize(
    "payload,field",
    [
        ({"temperature": 2.1}, "temperature"),
        ({"temperature": -0.1}, "temperature"),
        ({"top_p": 1.5}, "top_p"),
        ({"top_p": -1}, "top_p"),
        ({"max_tokens": 0}, "max_tokens"),
        ({"max_tokens": MAX_CHAT_MAX_TOKENS + 1}, "max_tokens"),
    ],
)
def test_rejects_out_of_range_values(payload, field):
    # 静默截断会让「我调了但没反应」变成另一种假开关
    with pytest.raises(InvalidExamRequestError, match=field):
        chat_tuning(payload)


@pytest.mark.parametrize(
    "payload", [{"temperature": "0.5"}, {"max_tokens": "800"}, {"max_tokens": 1.5}]
)
def test_rejects_wrong_types(payload):
    with pytest.raises(InvalidExamRequestError):
        chat_tuning(payload)


@pytest.mark.parametrize("payload", [{"temperature": True}, {"max_tokens": True}])
def test_booleans_are_not_numbers(payload):
    # Python 里 True 是 int 的子类，不挡住就会被当成 temperature=1
    with pytest.raises(InvalidExamRequestError):
        chat_tuning(payload)


@pytest.mark.parametrize("value", [0.0, 2.0])
def test_boundary_values_are_allowed(value):
    assert chat_tuning({"temperature": value})["temperature"] == value


# ====================== 绑定 ======================


def test_max_tokens_goes_through_extra_body_not_as_a_plain_kwarg():
    """这条是整个修复的要害。

    langchain 的 ChatOpenAI 会把 max_tokens 改名成 max_completion_tokens 发出去，
    而 DeepSeek 只认 max_tokens——改了名就等于没传，又变回一个假开关。
    所以它必须塞进 extra_body 原样透传。
    """
    kwargs = tuning_bind_kwargs(provider(), {"max_tokens": 500})
    assert kwargs == {"extra_body": {"max_tokens": 500}}
    assert "max_tokens" not in {k for k in kwargs if k != "extra_body"}


def test_extra_body_is_merged_not_replaced():
    # 登记模型时填的厂商参数（例如关闭思考）也在 extra_body 里，
    # 直接 bind 一个新的会把它整个冲掉
    registered = {"thinking": {"type": "disabled"}}
    kwargs = tuning_bind_kwargs(provider(registered), {"max_tokens": 500})
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}, "max_tokens": 500}


def test_merging_does_not_mutate_the_registered_extra_body():
    # provider 是缓存里的对象，就地改会污染后续所有请求
    registered = {"thinking": {"type": "disabled"}}
    tuning_bind_kwargs(provider(registered), {"max_tokens": 500})
    assert registered == {"thinking": {"type": "disabled"}}


def test_temperature_and_top_p_bind_directly():
    assert tuning_bind_kwargs(provider(), {"temperature": 0.2, "top_p": 0.8}) == {
        "temperature": 0.2,
        "top_p": 0.8,
    }


def test_no_tuning_means_no_bind_at_all():
    # 没有可调项就不该 bind——包装一层却什么都没改，只会让调用链更难读
    assert tuning_bind_kwargs(provider({"thinking": "x"}), None) == {}
    assert tuning_bind_kwargs(provider({"thinking": "x"}), {}) == {}


def test_tunable_list_matches_what_the_validator_accepts():
    accepted = set(chat_tuning({"temperature": 1, "top_p": 1, "max_tokens": 1}))
    assert accepted == set(TUNABLE)


# ====================== 真的发出去了 ======================


class RecordingClient:
    def __init__(self):
        self.bound: dict | None = None

    def bind(self, **kwargs):
        self.bound = kwargs
        return self

    def stream(self, _messages):
        yield types.SimpleNamespace(content="好", response_metadata={"finish_reason": "stop"})


class RecordingFactory:
    def __init__(self, client):
        self.client = client

    def get(self, _provider, **_kwargs):
        return self.client


class StubKB:
    def retrieve(self, _query, notebook_ids=None):
        return "材料", []


def test_tuning_reaches_the_client_on_the_streaming_path():
    """端到端的那一条：学生调了温度，它必须真的绑到这次调用上。"""
    from app.service.chat_service import ChatService

    client = RecordingClient()
    service = ChatService(StubKB(), RecordingFactory(client))

    list(
        service.stream_answer(
            [{"role": "user", "content": "排队论是什么"}],
            provider(extra_body={"thinking": {"type": "disabled"}}),
            tuning={"temperature": 0.1, "max_tokens": 300},
        )
    )

    assert client.bound is not None, "参数没绑上，还是个假开关"
    assert client.bound["temperature"] == 0.1
    assert client.bound["extra_body"] == {
        "thinking": {"type": "disabled"},
        "max_tokens": 300,
    }


def test_no_tuning_leaves_the_client_untouched():
    from app.service.chat_service import ChatService

    client = RecordingClient()
    service = ChatService(StubKB(), RecordingFactory(client))

    list(service.stream_answer([{"role": "user", "content": "你好"}], provider()))

    assert client.bound is None


# ====================== 多轮上下文确实送到了模型 ======================


class CapturingClient(RecordingClient):
    def __init__(self):
        super().__init__()
        self.sent: list = []

    def stream(self, messages):
        self.sent = messages
        yield from super().stream(messages)


class QueryKB:
    def __init__(self):
        self.queries: list[str] = []

    def retrieve(self, query, notebook_ids=None):
        self.queries.append(query)
        return "材料", []


HISTORY = [
    {"role": "user", "content": "什么是排队论"},
    {"role": "assistant", "content": "排队论研究随机服务系统。"},
]


def run_with_history(kb=None):
    from app.service.chat_service import ChatService

    client, kb = CapturingClient(), kb or QueryKB()
    service = ChatService(kb, RecordingFactory(client))
    list(
        service.stream_answer(
            [*HISTORY, {"role": "user", "content": "那它的前提呢"}],
            provider(),
        )
    )
    return client, kb


def test_previous_turns_are_forwarded_to_the_model():
    # 答疑长期只发「系统提示 + 当前这一句」，学生问「那它的前提呢」时
    # 模型根本不知道「它」指什么
    client, _ = run_with_history()
    roles = [m["role"] for m in client.sent]
    contents = [m["content"] for m in client.sent]
    assert roles[0] == "system", "后端自己的系统提示要在最前"
    assert "什么是排队论" in contents
    assert "排队论研究随机服务系统。" in contents
    assert contents[-1] == "那它的前提呢", "当前这一问要在最后"


def test_retrieval_keeps_the_current_question_and_adds_the_topic():
    """检索词必须**包含当前这一问**，不能被上一轮顶替掉。

    这条原来断言检索词就等于原句。后来加了追问补全：
    「那它的前提呢」里没有任何可检索的实词，原样拿去检索会命中无关论文
    （实测命中的是供应链和疫情），所以会把上一问的话题词拼进去。
    补上文是有意为之，但「当前这一问不能丢」这条底线没变。
    """
    _, kb = run_with_history()
    (query,) = kb.queries
    assert "那它的前提呢" in query, "当前这一问被顶替了"
    assert "排队论" in query, "没把上文的话题词带上，检索还是会跑偏"

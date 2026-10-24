"""把指代型追问补成能检索的问题（答疑子图的「理解问题」一步）。

实测现象：追问「那它的前提呢」检索到的是供应链 / COVID-19 / NSGA-II，
因为这句话里没有任何可检索的实词，而「前提」撞上了「Pareto 前沿」。
"""

from __future__ import annotations

import pytest

from app.rag.followup import looks_like_followup, resolve_query


def turns(*pairs) -> list[dict[str, str]]:
    return [{"role": role, "content": content} for role, content in pairs]


# ====================== 判断是不是追问 ======================


@pytest.mark.parametrize(
    "text",
    [
        # 光杆追问靠词表认，不靠字数——靠字数会把上面那些自足问题一起误伤
        "为什么",
        "具体点",
        "举个例子",
        "继续",
        "然后呢",
        "那它的前提呢",
        "它适用于什么场景",
        "这个怎么算",
        "那些条件是什么",
        "为什么",
        "还有呢",
        "具体点",
        "举个例子",
        "前者和后者的区别",
        "该模型的局限",
    ],
)
def test_detects_questions_that_need_context(text):
    assert looks_like_followup(text), f"「{text}」离开上文检索不出东西"


@pytest.mark.parametrize(
    "text",
    [
        "什么是 M/M/1 排队模型",
        "Little 公式怎么推导",
        "离散事件仿真的事件调度法",
        "泊松分布和指数分布的关系",
        # 下面这几条是短但自足的，早先按「字数少就算追问」判会全部误伤：
        # 中文实词密度高，「什么是排队论」去掉虚词只剩 5 个字。
        # 误判的后果是先问 M/M/1 再问「什么是仿真」时，
        # 会拿 M/M/1 的材料去答仿真——比不补上文更糟。
        "什么是排队论",
        "什么是仿真",
        "排队论是什么",
        "泊松分布",
        "离散事件仿真",
    ],
)
def test_leaves_self_contained_questions_alone(text):
    assert not looks_like_followup(text)
    assert resolve_query(turns(("user", "前一个问题")), text) == text


def test_blank_input_is_not_a_followup():
    assert not looks_like_followup("")
    assert resolve_query([], "") == ""


# ====================== 补上文 ======================


def test_prepends_the_previous_topic_question():
    history = turns(
        ("user", "什么是 M/M/1 排队模型"),
        ("assistant", "M/M/1 是单服务台、泊松到达的排队模型。"),
    )
    query = resolve_query(history, "那它的前提呢")
    assert "M/M/1" in query, f"没把话题词带上：{query}"
    assert "那它的前提呢" in query, "原问题要保留，它带着「前提」这个检索意图"


def test_uses_the_user_question_not_the_long_assistant_answer():
    # 回答动辄上千字，拼进检索词会把话题词冲淡
    history = turns(
        ("user", "什么是 Little 公式"),
        ("assistant", "排队论" * 500),
    )
    query = resolve_query(history, "它怎么用")
    assert "Little" in query
    assert len(query) < 200, f"检索词被回答撑爆了：{len(query)} 字"


def test_walks_back_past_consecutive_followups():
    # 连着追问好几句时，拼上去的不能还是一句指代
    history = turns(
        ("user", "什么是 M/M/1 排队模型"),
        ("assistant", "……"),
        ("user", "那它的前提呢"),
        ("assistant", "……"),
    )
    query = resolve_query(history, "那第二条呢")
    assert "M/M/1" in query, f"该一直回溯到带话题词的那一问：{query}"


def test_no_history_leaves_the_question_as_is():
    # 第一句就是指代型（刷新后接着问），没有上文可补，原样检索总比空检索好
    assert resolve_query([], "那它的前提呢") == "那它的前提呢"


def test_history_without_a_usable_question_leaves_it_as_is():
    history = turns(("user", "它呢"), ("assistant", "……"))
    assert resolve_query(history, "那前提呢") == "那前提呢"


def test_the_current_question_is_not_used_as_its_own_context():
    # 当前这问已经在 messages 里了，不能把自己拼给自己
    history = turns(("user", "那它的前提呢"))
    assert resolve_query(history, "那它的前提呢") == "那它的前提呢"


def test_ignores_assistant_turns_when_looking_back():
    history = turns(
        ("assistant", "离散事件仿真的三种调度法如下……"),
        ("user", "事件调度法怎么实现"),
        ("assistant", "……"),
    )
    query = resolve_query(history, "它的缺点呢")
    assert "事件调度法" in query


def test_the_real_case_from_production():
    """实测那一例：补之前检索到供应链/NSGA-II，补之后才可能命中排队论。"""
    history = turns(
        ("user", "什么是 M/M/1 排队模型"),
        ("assistant", "M/M/1 是单服务台、泊松到达、指数服务时间的排队模型。"),
    )
    query = resolve_query(history, "那它的前提呢")
    assert "排队" in query and "前提" in query


# ====================== 接线：两条路必须用同一个检索词 ======================
import types  # noqa: E402


class RecordingKB:
    def __init__(self):
        self.queries: list[str] = []

    def retrieve(self, query, notebook_ids=None):
        self.queries.append(query)
        return "材料", []


class StubClient:
    def bind(self, **_kwargs):
        return self

    def invoke(self, _messages):
        return types.SimpleNamespace(content="答")

    def stream(self, _messages):
        yield types.SimpleNamespace(content="答", response_metadata={"finish_reason": "stop"})


class StubFactory:
    def get(self, _provider, **_kwargs):
        return StubClient()


FOLLOWUP_TURNS = [
    {"role": "user", "content": "什么是 M/M/1 排队模型"},
    {"role": "assistant", "content": "M/M/1 是单服务台、泊松到达的排队模型。"},
    {"role": "user", "content": "那它的前提呢"},
]


def make_service(kb):
    from app.service.chat_service import ChatService

    return ChatService(kb, StubFactory())


def provider():
    return types.SimpleNamespace(extra_body=None, served_model_id="m")


def test_streaming_path_resolves_the_followup():
    kb = RecordingKB()
    list(make_service(kb).stream_answer(FOLLOWUP_TURNS, provider()))
    assert "M/M/1" in kb.queries[0], f"流式路径没补上文：{kb.queries[0]}"


def test_non_streaming_path_resolves_the_followup():
    kb = RecordingKB()
    make_service(kb).answer(FOLLOWUP_TURNS, provider())
    assert "M/M/1" in kb.queries[0], f"非流式路径没补上文：{kb.queries[0]}"


def test_both_paths_agree_on_the_query():
    # 同一个问题，两条路给出的依据必须一样，否则学生换个开关答案的出处就变了
    streaming, blocking = RecordingKB(), RecordingKB()
    list(make_service(streaming).stream_answer(FOLLOWUP_TURNS, provider()))
    make_service(blocking).answer(FOLLOWUP_TURNS, provider())
    assert streaming.queries == blocking.queries


@pytest.mark.parametrize("streamed", [True, False])
def test_an_explicit_retrieval_query_is_not_rewritten(streamed):
    # 论文模式给的是「题目 + 关键词」，它本来就是替代原问题的，补上文只会冲淡
    kb = RecordingKB()
    service = make_service(kb)
    if streamed:
        list(service.stream_answer(FOLLOWUP_TURNS, provider(), retrieval_query="排队论 仿真"))
    else:
        service.answer(FOLLOWUP_TURNS, provider(), retrieval_query="排队论 仿真")
    assert kb.queries == ["排队论 仿真"]


def test_a_self_contained_question_is_retrieved_as_typed():
    kb = RecordingKB()
    turns = [{"role": "user", "content": "Little 公式怎么推导"}]
    list(make_service(kb).stream_answer(turns, provider()))
    assert kb.queries == ["Little 公式怎么推导"]


def test_the_followup_is_only_resolved_once():
    # 两处都调 resolve 的话会拼两遍上文
    kb = RecordingKB()
    make_service(kb).answer(FOLLOWUP_TURNS, provider())
    assert kb.queries[0].count("M/M/1") == 1, f"上文被拼了两遍：{kb.queries[0]}"

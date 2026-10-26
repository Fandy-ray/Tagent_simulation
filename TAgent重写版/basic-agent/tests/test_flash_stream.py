"""闪卡边写边给：第一张写好就到，不等整组。

钉住的几件事：
- 扫描器在数组里的一项收口的那一刻就交出它，字符串里的括号、转义不会骗到它；
- 流式调用把写完的项交回调用方自己的线程（LangGraph 的 writer 只认节点线程），
  而且在整次调用结束**之前**；
- 服务层发出的每张卡都过了质量检查和跨片去重，编号按到达先后；
- 第一行之前的错误照旧是普通的 4xx，之后的错误放进流里；已经发出卡就照常收尾。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
import time
import types

import pytest
from langchain_core.messages import AIMessageChunk

from app.agent.nodes import json_call_streaming
from app.errors.exam_errors import ExamBusyError, InvalidExamRequestError, UpstreamLLMError
from app.factory import create_app
from app.infra.llm_json import StreamingClient
from app.schema.flash import DraftFlashCard, FlashClozeShardDraft
from app.util.json_items import JsonItemScanner
from tests.conftest import FakeRegistry
from tests.test_flash_service import (
    TEST_PROVIDER,
    EmptyKnowledgeBase,
    ExamOnlyServices,
    ScriptedShardLLM,
    ShardedKnowledgeBase,
    make_service,
)


# ====================== 扫描器 ======================
DOC = json.dumps(
    {
        "title": "排队\"论\"",
        "cloze": [
            {"text": "花括号 {x} 方括号 [y] 引号 \\\" 都在字符串里 ____", "accept": ["a}"], "n": {"k": [1, 2]}},
            {"text": "第二句 ____", "accept": ["b"]},
        ],
    },
    ensure_ascii=False,
)


def scan(text: str, step: int) -> tuple[list[str], JsonItemScanner]:
    scanner = JsonItemScanner()
    items: list[str] = []
    for start in range(0, len(text), step):
        items += scanner.feed(text[start : start + step])
    return items, scanner


@pytest.mark.parametrize("step", [1, 2, 5, 13, len(DOC)])
def test_scanner_yields_each_item_whatever_the_chunking(step):
    items, scanner = scan(DOC, step)
    assert [json.loads(item)["accept"] for item in items] == [["a}"], ["b"]]
    assert scanner.title == '排队"论"'


def test_an_item_comes_out_the_moment_it_closes():
    scanner = JsonItemScanner()
    first_end = DOC.index('"n": {"k": [1, 2]}}') + len('"n": {"k": [1, 2]}}')
    assert scanner.feed(DOC[: first_end - 1]) == []
    assert len(scanner.feed(DOC[first_end - 1 : first_end])) == 1


def test_fences_and_prose_around_the_json_do_not_matter():
    wrapped = "好的，下面是题目：\n```json\n" + DOC + "\n```\n以上。"
    items, scanner = scan(wrapped, 7)
    assert len(items) == 2 and scanner.title == '排队"论"'


def test_a_title_inside_an_item_is_not_the_deck_title():
    doc = json.dumps({"cloze": [{"title": "不是我", "text": "____"}], "title": "是我"}, ensure_ascii=False)
    items, scanner = scan(doc, 3)
    assert len(items) == 1 and scanner.title == "是我"


def test_a_half_written_item_is_not_yielded():
    items, _ = scan(DOC[: DOC.index("第二句")], 4)
    assert len(items) == 1


# ====================== StreamingClient ======================
class ChunkedLLM:
    """把一段文字切成几块，用 astream 一块块吐。"""

    def __init__(self, text: str, size: int = 9, pause: float = 0.0):
        self.text, self.size, self.pause = text, size, pause
        self.bound = {}

    def bind(self, **kwargs):
        self.bound.update(kwargs)
        return self

    async def astream(self, _prompt):
        for start in range(0, len(self.text), self.size):
            if self.pause:
                await asyncio.sleep(self.pause)
            yield AIMessageChunk(content=self.text[start : start + self.size])
        yield AIMessageChunk(content="", response_metadata={"finish_reason": "stop"})


def test_streaming_client_reads_every_piece_and_returns_the_whole_message():
    pieces: list[str] = []
    client = StreamingClient(ChunkedLLM(DOC), lambda: pieces.append)
    message = asyncio.run(client.ainvoke("prompt"))
    assert "".join(pieces) == DOC == message.content
    assert message.response_metadata.get("finish_reason") == "stop"


def test_streaming_client_opens_a_new_reader_per_attempt():
    opened: list[list[str]] = []

    def open_reader():
        opened.append([])
        return opened[-1].append

    client = StreamingClient(ChunkedLLM(DOC), open_reader)
    asyncio.run(client.ainvoke("a"))
    asyncio.run(client.ainvoke("b"))
    assert len(opened) == 2 and "".join(opened[1]) == DOC


def test_streaming_client_falls_back_to_ainvoke():
    class Plain:
        async def ainvoke(self, _prompt):
            return types.SimpleNamespace(content=DOC)

    pieces: list[str] = []
    message = asyncio.run(StreamingClient(Plain(), lambda: pieces.append).ainvoke("p"))
    assert pieces == [DOC] and message.content == DOC


# ====================== json_call_streaming ======================
class OneClientFactory:
    def __init__(self, client):
        self.client = client

    def get(self, *_args, **_kwargs):
        return self.client


def deps_for(client):
    from app.agent.runtime import AgentDeps

    return AgentDeps.start(
        knowledge_base=None,
        client_factory=OneClientFactory(client),
        provider=TEST_PROVIDER,
        budget_seconds=60,
    )


def call_streaming(client, **kwargs):
    seen: list[tuple[str, object, float, int]] = []
    result = json_call_streaming(
        deps_for(client),
        "prompt",
        FlashClozeShardDraft,
        item_cls=DraftFlashCard,
        on_item=lambda item: seen.append(("item", item, time.monotonic(), threading.get_ident())),
        on_title=lambda title: seen.append(("title", title, time.monotonic(), threading.get_ident())),
        max_tokens=100,
        limit=30,
        floor=5,
        **kwargs,
    )
    return result, seen


def test_items_reach_the_caller_thread_before_the_call_finishes():
    text = json.dumps(
        {"title": "T", "cloze": [{"text": f"第 {i} 句 ____", "accept": [f"答{i}"]} for i in range(4)]},
        ensure_ascii=False,
    )
    started = time.monotonic()
    result, seen = call_streaming(ChunkedLLM(text, size=10, pause=0.02))
    finished = time.monotonic()
    items = [entry for entry in seen if entry[0] == "item"]
    assert [entry[1].accept for entry in items] == [[f"答{i}"] for i in range(4)]
    assert {entry[3] for entry in seen} == {threading.get_ident()}, "没回到调用方的线程"
    assert items[0][2] - started < (finished - started) / 2, "第一项等到最后才交出来"
    assert seen[0][:2] == ("title", "T")
    assert len(result.cloze) == 4


def test_a_broken_item_is_skipped_and_the_shard_is_not_retried():
    text = json.dumps(
        {"cloze": [{"text": "没有挖空", "accept": ["x"]}, {"text": "有挖空 ____", "accept": ["y"]}]},
        ensure_ascii=False,
    )
    llm = ChunkedLLM(text)
    calls = []
    original = llm.astream

    async def counting(prompt):
        calls.append(prompt)
        async for chunk in original(prompt):
            yield chunk

    llm.astream = counting
    result, seen = call_streaming(llm)
    assert [entry[1].accept for entry in seen if entry[0] == "item"] == [["y"]]
    assert [card.accept for card in result.cloze] == [["y"]]
    assert len(calls) == 1


def test_errors_come_back_to_the_caller():
    with pytest.raises(UpstreamLLMError):
        call_streaming(ChunkedLLM("完全不是 JSON"))


# ====================== 服务层 ======================
class StreamingShardLLM(ScriptedShardLLM):
    """按 ScriptedShardLLM 的内容，一块块吐出来；每片在第一张卡之后还要写很久。"""

    def __init__(self, *args, tail=0.5, fail_kind=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tail = tail
        self.fail_kind = fail_kind  # 这一类的片每次都回坏 JSON

    async def astream(self, prompt):
        message = await self.ainvoke(prompt)  # 走子类改过的 ainvoke（例如 Leaky）
        kind = "choice" if "**选择题**" in prompt else "cloze"
        if self.fail_kind == kind:
            # 坏 JSON 要整段写完才认得出来，真实情况下总比别的片的第一张卡晚到；
            # 不等这一下，谁先到全看线程调度（2 核服务器上跑全量测试时偶尔是坏的这片先到）
            await asyncio.sleep(0.2)
            yield AIMessageChunk(content="不是 JSON")
            return
        text = message.content
        first_card_end = text.index("}") + 1
        yield AIMessageChunk(content=text[:first_card_end])
        await asyncio.sleep(self.tail)
        yield AIMessageChunk(content=text[first_card_end:])


def run_stream(llm, kb=None):
    service = make_service(kb or ShardedKnowledgeBase(), llm)
    return service, service.stream_flash_deck("排队论", TEST_PROVIDER)


def test_the_first_card_arrives_long_before_the_deck_is_finished():
    _, events = run_stream(StreamingShardLLM(tail=0.6))
    started = time.monotonic()
    arrivals = [(event, time.monotonic() - started) for event in events]
    first_card = next(at for event, at in arrivals if event["type"] == "card")
    total = arrivals[-1][1]
    assert first_card < 0.3 and total >= 0.6


def test_events_come_in_order_with_ids_in_arrival_order():
    _, events = run_stream(StreamingShardLLM(tail=0))
    events = list(events)
    assert events[0]["type"] == "deck" and events[0]["deck_id"]
    assert events[-1] == {"type": "done", "total_cards": 12}
    cards = [event["card"] for event in events if event["type"] == "card"]
    assert [card["id"] for card in cards] == [f"F{i}" for i in range(1, 13)]
    assert {card["type"] for card in cards} == {"cloze", "choice"}
    assert all(card.get("accept_normalized") for card in cards if card["type"] == "cloze")
    titles = [event for event in events if event["type"] == "title"]
    assert titles == [{"type": "title", "title": "排队论与仿真基础"}]


def test_duplicates_across_shards_are_sent_once():
    _, events = run_stream(StreamingShardLLM(tail=0, duplicate_everything=True))
    events = list(events)
    cards = [event for event in events if event["type"] == "card"]
    # 填空、选择撞同一个考点，只发第一张；整组只剩一张也照常收尾（已经在学生手上了）
    assert len(cards) == 1 and events[-1] == {"type": "done", "total_cards": 1}


def test_cards_that_leak_their_answer_are_not_sent():
    class Leaky(StreamingShardLLM):
        async def ainvoke(self, prompt):
            message = await super().ainvoke(prompt)
            payload = json.loads(message.content)
            for item in payload.get("cloze", []):
                item["text"] = f"{item['accept'][0]} 就是答案，空格填 ____ 即可。"
            return types.SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))

    _, events = run_stream(Leaky(tail=0))
    cards = [event["card"] for event in events if event["type"] == "card"]
    assert cards and all(card["type"] == "choice" for card in cards)


def test_empty_material_fails_before_the_first_event():
    _, events = run_stream(StreamingShardLLM(), EmptyKnowledgeBase())
    with pytest.raises(InvalidExamRequestError):
        next(events)


def test_one_failed_shard_after_others_sent_cards_still_finishes():
    _, events = run_stream(StreamingShardLLM(tail=0, fail_kind="choice"))
    events = list(events)
    assert events[-1]["type"] == "done" and events[-1]["total_cards"] == 8


def test_nothing_sent_passes_the_upstream_error_through():
    # 学生要看到的是上游那句（Key 不对、限流、结构异常……），而不是笼统的「质量不达标」
    class AllBroken(StreamingShardLLM):
        async def astream(self, prompt):
            yield AIMessageChunk(content="不是 JSON")

    _, events = run_stream(AllBroken())
    with pytest.raises(UpstreamLLMError, match="结构异常"):
        list(events)


def test_every_card_filtered_out_is_an_upstream_error():
    # 各片都写完了、没出错，但每张都指代学生看不到的材料，全被删掉
    class MaterialRef(StreamingShardLLM):
        async def ainvoke(self, prompt):
            message = await super().ainvoke(prompt)
            payload = json.loads(message.content)
            for item in payload.get("cloze", []):
                item["text"] = "如图 4.9 所示，空格填 ____ 即可。"
            for item in payload.get("choice", []):
                item["question"] = "根据材料，下列哪个正确？"
            return types.SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))

    _, events = run_stream(MaterialRef(tail=0))
    with pytest.raises(UpstreamLLMError, match="质量不达标"):
        list(events)


def free_slots(gate, limit=2) -> int:
    """闸门现在还能进几个（make_service 的闸门容量是 2）。"""
    with contextlib.ExitStack() as stack:
        for taken in range(limit):
            try:
                stack.enter_context(gate.acquire())
            except ExamBusyError:
                return taken
    return limit


def test_leaving_early_gives_the_gate_slot_back():
    service, events = run_stream(StreamingShardLLM(tail=0.2))
    assert next(events)["type"] == "deck"
    assert free_slots(service.llm_gate) == 1
    events.close()
    assert free_slots(service.llm_gate) == 2


def test_papers_do_not_go_into_flash_cards():
    kb = ShardedKnowledgeBase(pieces=6)
    kb.sources = ["textbook", "reference"] * 3
    llm = StreamingShardLLM(tail=0)
    _, events = run_stream(llm, kb)
    list(events)
    for prompt in llm.prompts:
        assert not any(f"材料{i} " in prompt for i in (1, 3, 5)), "论文片段进了闪卡"


def test_the_non_streaming_deck_still_assembles_and_interleaves():
    deck = make_service(ShardedKnowledgeBase(), StreamingShardLLM(tail=0)).generate_flash_deck(
        None, TEST_PROVIDER
    )
    kinds = [card.type for card in deck.cards]
    assert deck.total_cards == 12 and kinds.index("choice") < 8


# ====================== 路由 ======================
def client_with(llm, kb=None):
    service = make_service(kb or ShardedKnowledgeBase(), llm)
    application = create_app(
        {"TESTING": True},
        registry=FakeRegistry([TEST_PROVIDER]),
        services=ExamOnlyServices(service),
    )
    return application.test_client()


def ndjson(response) -> list[dict]:
    return [json.loads(line) for line in response.get_data(as_text=True).splitlines() if line]


def test_route_streams_ndjson():
    response = client_with(StreamingShardLLM(tail=0)).post(
        "/quiz/flash/stream", json={"model": TEST_PROVIDER.served_model_id, "topic": "排队论"}
    )
    assert response.status_code == 200
    assert response.mimetype == "application/x-ndjson"
    events = ndjson(response)
    assert events[0]["type"] == "deck" and events[-1]["type"] == "done"
    assert sum(event["type"] == "card" for event in events) == events[-1]["total_cards"] == 12


def test_route_reports_errors_before_the_stream_as_plain_errors():
    client = client_with(StreamingShardLLM(), EmptyKnowledgeBase())
    response = client.post("/quiz/flash/stream", json={"model": TEST_PROVIDER.served_model_id})
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "invalid_exam_request"
    assert client.post("/quiz/flash/stream", json={"model": "nope"}).status_code == 404


def test_route_puts_later_errors_into_the_stream():
    class AllBroken(StreamingShardLLM):
        async def astream(self, prompt):
            yield AIMessageChunk(content="不是 JSON")

    response = client_with(AllBroken()).post(
        "/quiz/flash/stream", json={"model": TEST_PROVIDER.served_model_id}
    )
    assert response.status_code == 200
    events = ndjson(response)
    assert events[0]["type"] == "deck"
    assert events[-1]["type"] == "error" and events[-1]["code"] == "upstream_llm_error"

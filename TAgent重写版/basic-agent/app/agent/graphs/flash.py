"""闪卡组：填空 + 选择两类，按材料分片并发，卡组不计分。

    START → deal ─Send×N→ shard → assemble → END

与整卷的分段是同一条思路再往下切一层。整卷的填空段一次要 8~10 张、
配 4500 字上下文；闪卡把「每次调用的输出量」和「上下文长度」同时砍到
三分之一——每片 3~4 张配 ~1600 字材料，几片并发。

分片的材料**互不相同**：sample_exam_context 返回的是若干片段用
EXAM_CONTEXT_SEPARATOR 拼起来的，deal 把它切回去轮流发牌。这是并发分片
不撞考点的主要手段——整卷那边实测过「把已考知识点清单塞回 prompt」，
结果是重复更多，所以不走那条路，改在 assemble 里 dedupe_cards 兜底。

大题不进闪卡：写一段话没法当场判，而「当场知道对错」正是闪卡的全部意义。
"""

from __future__ import annotations

import operator
import uuid
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Send

from app.agent.nodes import json_call
from app.agent.runtime import AgentDeps
from app.config import (
    EXAM_CONTEXT_SEPARATOR,
    FLASH_CHOICE_SHARDS,
    FLASH_CLOZE_SHARDS,
    FLASH_CONTEXT_CHAR_LIMIT,
    FLASH_DECK_MIN_CARDS,
    FLASH_LLM_TIMEOUT,
    FLASH_MIN_ATTEMPT_TIMEOUT,
    FLASH_SHARD_CARD_RANGE,
    FLASH_SHARD_COUNT,
)
from app.errors.exam_errors import InvalidExamRequestError, UpstreamLLMError
from app.prompts.exam_prompts import build_choice_prompt, build_cloze_prompt
from app.schema.exam_quality import clean_questions
from app.schema.flash import (
    DraftFlashChoice,
    FlashChoiceShardDraft,
    FlashClozeShardDraft,
    dedupe_cards,
    interleave,
    normalize_deck,
)
from app.util.text import deal_shards


_STAGES = {
    "cloze": (build_cloze_prompt, FlashClozeShardDraft),
    "choice": (build_choice_prompt, FlashChoiceShardDraft),
}


class FlashState(TypedDict, total=False):
    topic: str | None
    notebook_ids: list[str] | None
    jobs: list[tuple[str, str]]  # (题型, 这一片的材料)
    count_range: tuple[int, int]
    # LangGraph 按发牌顺序（而不是完成先后）合并各片的结果，卡组顺序因此稳定；
    # 测试 test_deck_keeps_the_deal_order_when_the_first_shard_finishes_last 钉着这一点
    parts: Annotated[list[Any], operator.add]
    deck: Any


class ShardTask(TypedDict):
    kind: str
    context: str
    topic: str | None
    count_range: tuple[int, int]


def _deal(state: FlashState, runtime: Runtime[AgentDeps]) -> dict:
    context = runtime.context.knowledge_base.sample_exam_context(
        state.get("topic"), notebook_ids=state.get("notebook_ids")
    )
    shards = deal_shards(
        context,
        FLASH_SHARD_COUNT,
        separator=EXAM_CONTEXT_SEPARATOR,
        char_limit=FLASH_CONTEXT_CHAR_LIMIT,
    )
    if not shards:
        raise InvalidExamRequestError("所选知识范围里没有可出题的材料，请换一个笔记本或来源")

    kinds = ["cloze"] * FLASH_CLOZE_SHARDS + ["choice"] * FLASH_CHOICE_SHARDS
    lo, hi = FLASH_SHARD_CARD_RANGE
    if len(shards) < len(kinds):
        # 知识库太小、切不出这么多片。宁可少发几次，也不能让两片拿同一份
        # 材料——那等于自找重复。填空优先，还剩位置再给选择留一片。
        keep = len(shards)
        kinds = ["cloze"] if keep == 1 else ["cloze"] * (keep - 1) + ["choice"]
        # 每片多出几张，卡组规模才不会跟着分片数一起缩水
        scale = FLASH_SHARD_COUNT / keep
        lo = min(int(round(lo * scale)), 10)
        hi = min(int(round(hi * scale)), 12)
    return {"jobs": list(zip(kinds, shards)), "count_range": (lo, hi)}


def _fan_out(state: FlashState) -> list[Send]:
    return [
        Send(
            "shard",
            {
                "kind": kind,
                "context": context,
                "topic": state.get("topic"),
                "count_range": state["count_range"],
            },
        )
        for kind, context in state["jobs"]
    ]


def _shard(task: ShardTask, runtime: Runtime[AgentDeps]) -> dict:
    build_prompt, model_cls = _STAGES[task["kind"]]
    part = json_call(
        runtime.context,
        build_prompt(
            task["context"], task["topic"], [], count_range=task["count_range"], deck_mode=True
        ),
        model_cls,
        max_tokens=2500,
        limit=FLASH_LLM_TIMEOUT,
        floor=FLASH_MIN_ATTEMPT_TIMEOUT,
    )
    return {"parts": [part]}


def _assemble(state: FlashState) -> dict:
    parts = state["parts"]
    cloze_cards = [
        card for part in parts if isinstance(part, FlashClozeShardDraft) for card in part.cloze
    ]
    choice_cards = [
        card for part in parts if isinstance(part, FlashChoiceShardDraft) for card in part.choice
    ]

    # 闪卡这边**不**像整卷那样用 post_validate 守题量：那会让任何一片出一道
    # 坏卡就整片重来，而闪卡本来就是几片并发、追求快。这里只管删，
    # 删完不够数由下面的 FLASH_DECK_MIN_CARDS 一起兜。
    cloze_cards = clean_questions(cloze_cards, "闪卡填空")
    choice_cards = clean_questions(choice_cards, "闪卡选择")

    # 先跨类型去重（同一个考点出成填空还是选择都算重复，填空先到先得），
    # 再交错，顺序才不会被去重打乱。
    kept = dedupe_cards(cloze_cards + choice_cards)
    if len(kept) < FLASH_DECK_MIN_CARDS:
        # 各片撞考点撞得太狠、或坏卡删太多，剩下的卡组不值得刷
        raise UpstreamLLMError("生成的闪卡质量不达标，请重试")

    cards = interleave(
        [card for card in kept if not isinstance(card, DraftFlashChoice)],
        [card for card in kept if isinstance(card, DraftFlashChoice)],
    )
    return {"deck": normalize_deck(cards, parts[0].title, str(uuid.uuid4()))}


def build_flash_graph():
    graph = StateGraph(FlashState, context_schema=AgentDeps)
    graph.add_node("deal", _deal)
    graph.add_node("shard", _shard)
    graph.add_node("assemble", _assemble)
    graph.add_edge(START, "deal")
    graph.add_conditional_edges("deal", _fan_out, ["shard"])
    graph.add_edge("shard", "assemble")
    graph.add_edge("assemble", END)
    return graph.compile()


FLASH_GRAPH = build_flash_graph()

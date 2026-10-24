"""整卷出题。

    START → sample ─Send×7─┬─ 大题 ×3（每路一道：计算 / 建模 / 分析或对比，带全部材料）
                           └─ 填空 ×2、选择 ×2（各拿一片不同的教材；第一路专管核心概念）
                     → assemble（删违规题 → 填空选择跨段去重 → 裁到规定题数）→ END

**耗时几乎全花在模型「写」上**：单调一次首字 0.7 秒，之后每秒两三百字。一路要
大题三道就得写 2500 字左右、填空十道 1800 字左右——写多少字等多久。所以不是让
一路写得更快，而是让每一路少写、多发几路同时写，七路同时起步、谁也不等谁。

能这么做的前提是直连（app/infra/upstream_http.py）：以前走本机代理时多发几路就
互相拖慢，拆开反而更慢；直连后同时发 8 路，每路仍是 1.9 秒左右。

2026-10-24 实测（DeepSeek，直连，同一时段，各 6~10 张）：

    以前：大题一路三道 ∥ 定考点 → 填空一路 ∥ 选择一路     中位 7.2 秒，每卷撞考点 8.7 对
    现在：七路同时，每路一道大题 / 五六道填空 / 四五道选择   中位 4.0~4.3 秒，8.7 对

几处取舍：
- **不再先定考点**（那一次调用挡在填空、选择前面 1.5 秒），改为每路一片不同的材料、
  第一路专管核心概念、其余各路避开，撞考点和以前持平。数据见 config.py 同名那段。
- **填空、选择只分教材片段**，论文片段只给大题。材料切得小，分到论文片段的那一路
  只能从论文里挑，出来的是「小区开放后的改善率怎么定义」这类论文独有的细节
  （评委统计每卷 2.1 道，以前 0.3 道）；大题拿全部材料，论文正好当应用场景。
- **大题拆成三路、每路一道**，组与组的能力类型不相交（schema.exam.ESSAY_GROUPS），
  三道题结构上就不会撞类型；一次出三道时模型守不住「每类一道」。
- 再拆细没用：试过填空选择拆成六七路、每路两三道，单路仍要两秒多（首字等待、
  读入几千字材料是每路都有的固定开销），加上路数多了尾巴更长，反而更慢。

为什么还要分段（老结论，仍然成立）：整卷一次性输出上万 token 会顶穿单次调用超时；
某一路不合法时也只重出那一路。
"""

from __future__ import annotations

import logging
import operator
import uuid
from typing import Annotated, Any, NamedTuple, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Send

from app.agent.nodes import json_call, sample_quiz_material
from app.agent.runtime import AgentDeps
from app.config import EXAM_CONTEXT_SEPARATOR, EXAM_LLM_TIMEOUT, EXAM_MIN_ATTEMPT_TIMEOUT
from app.errors.exam_errors import UpstreamLLMError
from app.prompts.exam_prompts import (
    LANE_CORE,
    LANE_OTHER,
    build_choice_prompt,
    build_cloze_prompt,
    build_essay_gen_prompt,
)
from app.schema.exam import (
    CHOICE_COUNT_RANGE,
    CLOZE_COUNT_RANGE,
    ESSAY_COUNT_RANGE,
    ESSAY_GROUPS,
    ChoiceExamDraft,
    ClozeExamDraft,
    EssayExamDraft,
    GeneratedExamDraft,
    normalize_draft,
)
from app.schema.exam_quality import clean_questions, require_clean_enough
from app.schema.flash import dedupe_cards
from app.util.text import deal_shards

log = logging.getLogger(__name__)


class Stage(NamedTuple):
    """出卷的一路。用具名字段而不是裸元组，谁重排一下也不会静默取错。"""

    kind: str  # cloze / choice / essay
    build_prompt: Any
    model_cls: Any
    max_tokens: int
    count_range: tuple[int, int]  # 让模型出几道
    minimum: int  # 删掉违规题后至少还要剩几道，不够就重出这一路


# 填空、选择各分两路。每路要的题数比「整卷下限 / 路数」多一两道：
# 删违规题、跨段去重都要余量，多出来的组卷时裁掉
CLOZE_STAGE = Stage("cloze", build_cloze_prompt, ClozeExamDraft, 2500, (5, 6), 4)
CHOICE_STAGE = Stage("choice", build_choice_prompt, ChoiceExamDraft, 2500, (4, 5), 3)
# (这一路, 管不管核心概念)。第一路专管核心概念，其余各路避开，见 exam_prompts._lane_block
OBJECTIVE_LANES = [
    (CLOZE_STAGE, LANE_CORE),
    (CLOZE_STAGE, LANE_OTHER),
    (CHOICE_STAGE, LANE_OTHER),
    (CHOICE_STAGE, LANE_OTHER),
]
assert 2 * CLOZE_STAGE.minimum >= CLOZE_COUNT_RANGE[0]
assert 2 * CHOICE_STAGE.minimum >= CHOICE_COUNT_RANGE[0]
ESSAY_STAGE = Stage("essay", build_essay_gen_prompt, EssayExamDraft, 2000, (1, 1), 1)
# 每片材料的字数上限。出题材料一共 EXAM_CONTEXT_CHAR_LIMIT 字左右，切成四片
_SHARD_CHAR_LIMIT = 1600


class ExamState(TypedDict, total=False):
    topic: str | None
    notebook_ids: list[str] | None
    context: str  # 全部材料，给大题
    objective_material: list[str]  # 填空、选择分片用的片段（不含论文）
    # 每路一份 (题型, 草稿)；LangGraph 按发出的顺序合并，不按完成先后
    parts: Annotated[list[tuple[str, Any]], operator.add]
    exam: Any


class WriteTask(TypedDict):
    stage: Stage
    context: str
    topic: str | None
    group: dict | None  # 大题那几路：出哪一组能力类型
    lane: str | None  # 填空选择那几路：管不管核心概念


def _sample(state: ExamState, runtime: Runtime[AgentDeps]) -> dict:
    texts, objective = sample_quiz_material(
        runtime.context, state.get("topic"), state.get("notebook_ids")
    )
    return {"context": EXAM_CONTEXT_SEPARATOR.join(texts), "objective_material": objective}


def _fan_out(state: ExamState) -> list[Send]:
    context, topic = state["context"], state.get("topic")
    tasks = [
        {"stage": ESSAY_STAGE, "context": context, "topic": topic, "group": group, "lane": None}
        for group in ESSAY_GROUPS
    ]
    # 填空、选择每路一片不同的材料；材料太少切不出这么多片时轮流共用
    # （撞了的由组卷时的去重收拾）
    material = EXAM_CONTEXT_SEPARATOR.join(state["objective_material"])
    shards = deal_shards(
        material, len(OBJECTIVE_LANES), separator=EXAM_CONTEXT_SEPARATOR, char_limit=_SHARD_CHAR_LIMIT
    ) or [material]
    tasks += [
        {
            "stage": stage,
            "context": shards[index % len(shards)],
            "topic": topic,
            "group": None,
            "lane": lane,
        }
        for index, (stage, lane) in enumerate(OBJECTIVE_LANES)
    ]
    return [Send("write", task) for task in tasks]


def _write(task: WriteTask, runtime: Runtime[AgentDeps]) -> dict:
    """写一路题。大题、填空、选择共用这一个节点。"""
    stage = task["stage"]
    if stage.kind == "essay":
        prompt = stage.build_prompt(task["context"], task["topic"], [], group=task["group"])
    else:
        prompt = stage.build_prompt(
            task["context"], task["topic"], [], lane=task["lane"], count_range=stage.count_range
        )
    try:
        part = json_call(
            runtime.context,
            prompt,
            stage.model_cls,
            max_tokens=stage.max_tokens,
            limit=EXAM_LLM_TIMEOUT,
            floor=EXAM_MIN_ATTEMPT_TIMEOUT,
            # 守的是「违规题删掉之后还够不够数」，而不是「有没有违规题」。
            # 后者会让一路里出一道坏题就整路重来，白等一轮模型
            post_validate=lambda value: require_clean_enough(value, stage.kind, stage.minimum),
        )
    except UpstreamLLMError as exc:
        if stage.kind != "essay":
            raise
        # 三路大题少一路，剩下两道仍够一张卷（下限 2 道），别为它让整卷失败
        log.warning("一路大题没出来（%s），用其余几道组卷", exc)
        return {"parts": []}
    return {"parts": [(stage.kind, part)]}


def _dedupe_keeping_counts(cloze: list, choice: list) -> tuple[list, list]:
    """填空、选择放在一起按答案和题干去重（同一个点出成填空还是选择都算撞）。

    去重后跌破题数下限时，按原顺序把删掉的补回来几道——一道近似题，好过整卷 502。
    """
    kept = {id(question) for question in dedupe_cards([*cloze, *choice])}

    def refill(questions: list, minimum: int) -> list:
        result = [q for q in questions if id(q) in kept]
        for question in questions:
            if len(result) >= minimum:
                break
            if id(question) not in kept:
                result.append(question)
        return result

    return refill(cloze, CLOZE_COUNT_RANGE[0]), refill(choice, CHOICE_COUNT_RANGE[0])


def _assemble(state: ExamState) -> dict:
    by_kind: dict[str, list] = {"cloze": [], "choice": [], "essay": []}
    for kind, part in state.get("parts") or []:
        by_kind[kind].append(part)

    cloze = clean_questions([q for p in by_kind["cloze"] for q in p.cloze], "填空")
    choice = clean_questions([q for p in by_kind["choice"] for q in p.choice], "选择")
    cloze, choice = _dedupe_keeping_counts(cloze, choice)
    # 每组大题按自己的上限裁（模型多给的余量），合起来再按整卷上限裁
    essays = [
        q
        for part in by_kind["essay"]
        for q in clean_questions(part.essay, "解答", ESSAY_STAGE.count_range[1])
    ]
    if len(essays) < ESSAY_COUNT_RANGE[0]:
        raise UpstreamLLMError("解答题没能出够，请稍后重试")

    draft = GeneratedExamDraft(
        title=by_kind["cloze"][0].title,
        cloze=cloze[: CLOZE_COUNT_RANGE[1]],
        choice=choice[: CHOICE_COUNT_RANGE[1]],
        essay=essays[: ESSAY_COUNT_RANGE[1]],
    )
    return {"exam": normalize_draft(draft, str(uuid.uuid4()))}


def build_exam_graph():
    graph = StateGraph(ExamState, context_schema=AgentDeps)
    graph.add_node("sample", _sample)
    graph.add_node("write", _write)
    graph.add_node("assemble", _assemble)
    graph.add_edge(START, "sample")
    graph.add_conditional_edges("sample", _fan_out, ["write"])
    # 同一轮的七路全部写完才组卷，assemble 只跑一次
    graph.add_edge("write", "assemble")
    graph.add_edge("assemble", END)
    return graph.compile()


EXAM_GRAPH = build_exam_graph()

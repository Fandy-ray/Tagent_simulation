"""判卷里要模型评的那部分。

    START → prepare ─Send×批次→ grade → END

本机能判的（选择、精确匹配的填空、没作答的）在 ExamService.review_exam 里先判掉，
不进这张图；只把语义题按题型切成小批送来。

分批而不是一次评完，是题量提高后判分准确性的主要保障：
- 填空复核与解答题各用一套互不干扰的准则（二值判定 vs 逐要点计数），
  混在同一条 prompt 里时两种尺度会互相污染；
- 每批 ID 集合小，validate_grade_batch 的「不多不少」更容易满足，
  少一次整批重试就少一次评分漂移；
- max_tokens 按批内题数给，避免十几条 feedback 撑爆输出导致 JSON 截断。

各批**并发**：批与批之间互不依赖。以前是一批接一批，总耗时是各批相加，
还得把预算按「剩余时间 / 剩余批数」切开，免得靠前的批次吃掉整个预算；
并发后各批共用同一个截止时间，谁都不必让谁。
"""

from __future__ import annotations

import json
import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Send

from app.agent.nodes import json_call
from app.agent.runtime import AgentDeps
from app.config import (
    GRADE_CLOZE_BATCH,
    GRADE_ESSAY_BATCH,
    GRADE_LLM_TIMEOUT,
    GRADE_MIN_ATTEMPT_TIMEOUT,
)
from app.prompts.exam_prompts import build_cloze_grade_prompt, build_essay_grade_prompt
from app.schema.exam import LLMGradeBatch, LLMGradeItem, validate_grade_batch
from app.util.text import chunked


_PROMPTS = {"essay": build_essay_grade_prompt, "cloze": build_cloze_grade_prompt}


class GradeState(TypedDict, total=False):
    items: list[dict[str, Any]]
    batches: list[tuple[str, list[dict[str, Any]]]]
    graded: Annotated[list[LLMGradeItem], operator.add]


class BatchTask(TypedDict):
    kind: str
    chunk: list[dict[str, Any]]


def _prepare(state: GradeState, runtime: Runtime[AgentDeps]) -> dict:
    """给每道大题配几段参考材料，再按题型切批。"""
    essays, clozes = [], []
    for item in state["items"]:
        if item["type"] == "essay":
            documents = runtime.context.knowledge_base.search(item["question"], k=3)
            item = {**item, "knowledge_context": [d.page_content[:600] for d in documents]}
            essays.append(item)
        else:
            clozes.append(item)
    batches = [("essay", chunk) for chunk in chunked(essays, GRADE_ESSAY_BATCH)]
    batches += [("cloze", chunk) for chunk in chunked(clozes, GRADE_CLOZE_BATCH)]
    return {"batches": batches}


def _fan_out(state: GradeState) -> list[Send]:
    return [Send("grade", {"kind": kind, "chunk": chunk}) for kind, chunk in state["batches"]]


def _grade(task: BatchTask, runtime: Runtime[AgentDeps]) -> dict:
    chunk = task["chunk"]
    expected_ids = {item["question_id"] for item in chunk}
    batch = json_call(
        runtime.context,
        _PROMPTS[task["kind"]](json.dumps(chunk, ensure_ascii=False, indent=1)),
        LLMGradeBatch,
        max_tokens=600 + 500 * len(chunk),
        limit=GRADE_LLM_TIMEOUT,
        floor=GRADE_MIN_ATTEMPT_TIMEOUT,
        # 题号多一个少一个都算不合格，在重试圈里重来
        post_validate=lambda value: validate_grade_batch(value, expected_ids),
    )
    return {"graded": batch.items}


def build_grade_graph():
    graph = StateGraph(GradeState, context_schema=AgentDeps)
    graph.add_node("prepare", _prepare)
    graph.add_node("grade", _grade)
    graph.add_edge(START, "prepare")
    graph.add_conditional_edges("prepare", _fan_out, ["grade"])
    graph.add_edge("grade", END)
    return graph.compile()


GRADE_GRAPH = build_grade_graph()

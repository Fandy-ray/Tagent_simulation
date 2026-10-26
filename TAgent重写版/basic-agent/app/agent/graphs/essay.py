"""小论文批改，以及答疑论文模式里的出题。

批改的图：

    START → retrieve ─Send×3→ dimension → drill_down → END

- 三个维度并发打分，材料只给要它的维度（内容、论证）；语言只看文字本身，
  给它材料纯属浪费 token 和时间；
- 只有论证维度顺带报可疑段落——它本来就要通读全文，这一步是白捡的；
- 下钻是条件触发的第四轮：没被点名就一轮都不发（drill_down 里直接返回）。

整次批改共用一个截止时间（AgentDeps.deadline），下钻用的是剩下的那部分。
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Send

from app.agent.graphs.annotate import annotate_sentences
from app.agent.nodes import json_call, search_text
from app.agent.runtime import FANOUT_MAX_CONCURRENCY, AgentDeps
from app.config import (
    ESSAY_CONTEXT_CHAR_LIMIT,
    ESSAY_LLM_TIMEOUT,
    ESSAY_MAX_FLAGGED_PARAGRAPHS,
    ESSAY_MIN_ATTEMPT_TIMEOUT,
    ESSAY_TOPIC_LLM_TIMEOUT,
    ESSAY_TOPIC_MAX_SUGGESTED_CHARS,
    ESSAY_TOPIC_MIN_ATTEMPT_TIMEOUT,
    ESSAY_TOPIC_MIN_SUGGESTED_CHARS,
)
from app.prompts.essay_prompts import (
    build_annotation_prompt,
    build_dimension_prompt,
    build_topic_prompt,
    dimension_order,
)
from app.schema.essay import (
    MAX_ISSUES,
    MAX_PRAISES,
    Annotation,
    LLMDimension,
    LLMEssayTopic,
    numbered_text,
    validate_dimension,
)


# 需要参考材料的维度
_NEEDS_CONTEXT = {"content", "argument"}
# 顺带报可疑段落的维度
_REPORTS_FLAGS = "argument"


def essay_context(deps: AgentDeps, topic: str | None, fallback: str, notebook_ids) -> str:
    """按题目（没题目就按 fallback）检索材料，用来判「是否用上课程内容」。"""
    query = (topic or "").strip() or fallback[:120]
    return search_text(
        deps,
        query,
        k=3,
        piece_chars=600,
        char_limit=ESSAY_CONTEXT_CHAR_LIMIT,
        notebook_ids=notebook_ids,
    )


# ====================== 批改 ======================


class EssayState(TypedDict, total=False):
    source: str
    topic: str | None
    notebook_ids: list[str] | None
    sentences: list[Any]
    context: str
    # 三路并发各写自己那一维，合并成一张表
    graded: Annotated[dict[str, LLMDimension], operator.or_]
    annotations: list[Annotation]


class DimensionTask(TypedDict):
    dimension: str
    numbered: str
    topic: str | None
    context: str


def _retrieve(state: EssayState, runtime: Runtime[AgentDeps]) -> dict:
    # 检索失败不该让整次批改失败：语言维度根本不需要材料，
    # 另两维没材料也还能评，只是「用上课程概念」那条判得保守些
    return {
        "context": essay_context(
            runtime.context, state.get("topic"), state["source"], state.get("notebook_ids")
        )
    }


def _fan_out(state: EssayState) -> list[Send]:
    numbered = numbered_text(state["sentences"])
    return [
        Send(
            "dimension",
            {
                "dimension": name,
                "numbered": numbered,
                "topic": state.get("topic"),
                "context": state["context"] if name in _NEEDS_CONTEXT else "",
            },
        )
        for name in dimension_order()
    ]


def _dimension(task: DimensionTask, runtime: Runtime[AgentDeps]) -> dict:
    name = task["dimension"]
    prompt = build_dimension_prompt(
        name,
        task["numbered"],
        topic=task["topic"],
        context=task["context"],
        want_flags=(name == _REPORTS_FLAGS),
    )
    result = json_call(
        runtime.context,
        prompt,
        LLMDimension,
        max_tokens=900,
        limit=ESSAY_LLM_TIMEOUT,
        floor=ESSAY_MIN_ATTEMPT_TIMEOUT,
        # **必须**走 post_validate，不能拿到结果之后在外面校验：
        # 模型把要点换个说法抄回来是常事，那是该重试的情形。
        # 放在圈外校验，一次不合格就直接 500 了（实测踩过）。
        post_validate=lambda value: validate_dimension(value, name),
    )
    return {"graded": {name: result}}


def _drill_down(state: EssayState, runtime: Runtime[AgentDeps]) -> dict:
    """条件触发的第四轮：没被点名就一轮都不发。"""
    sentences = state["sentences"]
    paragraphs = {p for p in state["graded"][_REPORTS_FLAGS].flagged_paragraphs if p > 0}
    if not paragraphs or not sentences:
        return {"annotations": []}
    # 只限制批注目标；全文仍作为上下文提供，避免把前文已给的参数误判缺失。
    paragraphs = set(sorted(paragraphs)[:ESSAY_MAX_FLAGGED_PARAGRAPHS])

    focused = [s for s in sentences if s.paragraph in paragraphs]
    if not focused:
        return {"annotations": []}

    prompt = build_annotation_prompt(
        numbered_text(focused),
        full_text=numbered_text(sentences),
        focus="这几段是通读后觉得问题最集中的部分。",
        max_issues=MAX_ISSUES,
        max_praises=MAX_PRAISES,
    )
    # 和大题批注是同一个节点；截止时间沿用整次批改的
    return {
        "annotations": annotate_sentences(
            runtime.context,
            prompt,
            focused,
            max_issues=MAX_ISSUES,
            max_praises=MAX_PRAISES,
            limit=ESSAY_LLM_TIMEOUT,
            floor=ESSAY_MIN_ATTEMPT_TIMEOUT,
        )
    }


def build_essay_graph():
    graph = StateGraph(EssayState, context_schema=AgentDeps)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("dimension", _dimension)
    graph.add_node("drill_down", _drill_down)
    graph.add_edge(START, "retrieve")
    graph.add_conditional_edges("retrieve", _fan_out, ["dimension"])
    # 三路都写完才进下一步：同一轮里的 Send 全部结束，drill_down 只跑一次
    graph.add_edge("dimension", "drill_down")
    graph.add_edge("drill_down", END)
    return graph.compile()


ESSAY_GRAPH = build_essay_graph().with_config(max_concurrency=FANOUT_MAX_CONCURRENCY)


# ====================== 出题 ======================


def write_topic(
    deps: AgentDeps, hint: str | None, fallback: str, notebook_ids
) -> tuple[LLMEssayTopic, str]:
    """按笔记本材料出一道小论文题。只有一次模型调用，不必建图。

    检索不到材料也照样出题（出课程通用题），返回的材料为空，由调用方如实告诉前端。
    """
    context = essay_context(deps, hint, fallback, notebook_ids)
    prompt = build_topic_prompt(
        context,
        hint,
        min_chars=ESSAY_TOPIC_MIN_SUGGESTED_CHARS,
        max_chars=ESSAY_TOPIC_MAX_SUGGESTED_CHARS,
    )
    result = json_call(
        deps,
        prompt,
        LLMEssayTopic,
        max_tokens=500,
        limit=ESSAY_TOPIC_LLM_TIMEOUT,
        floor=ESSAY_TOPIC_MIN_ATTEMPT_TIMEOUT,
    )
    return result, context

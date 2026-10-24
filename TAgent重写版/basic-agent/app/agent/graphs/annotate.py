"""逐句批注。

核心是 annotate_sentences：给带编号的句子 → 问一次模型 → 校验编号与定额 →
挂上原文区间。两处共用它：

- 整卷大题的按需批注（本文件的图）；
- 小论文批改的条件下钻（essay.py 的 drill_down 节点）。

文件编辑（edit.py）是同一套做法：修改建议就是批注加一个「改成什么」字段。

模型只回句子编号，永不回原文片段或字符下标；区间由 split_sentences 切句时
存好，这里查表。零匹配、零猜测。
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.agent.nodes import json_call
from app.agent.runtime import AgentDeps
from app.errors.exam_errors import UpstreamLLMError
from app.schema.essay import (
    Annotation,
    LLMAnnotationBatch,
    attach_spans,
    validate_annotations,
)


def annotate_sentences(
    deps: AgentDeps,
    prompt: str,
    sentences: list[Any],
    *,
    max_issues: int,
    max_praises: int,
    limit: float,
    floor: float,
    full_credit: bool = False,
) -> list[Annotation]:
    """问一次模型拿批注，挂上原文区间。失败降级成空列表。

    批注是锦上添花：分数和评语在这之前已经拿到了，没必要因为多标几句
    失败就把整次判失败——少几条下划线，比一片红字好。
    """
    known = {sentence.id for sentence in sentences}
    try:
        batch = json_call(
            deps,
            prompt,
            LLMAnnotationBatch,
            max_tokens=200 + 160 * (max_issues + max_praises),
            limit=limit,
            floor=floor,
            # 编错句号、超定额都该重试一次，而不是抛给用户
            post_validate=lambda value: validate_annotations(
                value,
                known,
                max_issues=max_issues,
                max_praises=max_praises,
                full_credit=full_credit,
            ),
        )
    except UpstreamLLMError:
        return []
    return attach_spans(batch, sentences)


class AnnotateState(TypedDict, total=False):
    prompt: str
    sentences: list[Any]
    max_issues: int
    max_praises: int
    full_credit: bool
    limit: float
    floor: float
    annotations: list[Annotation]


def _annotate_node(state: AnnotateState, runtime: Runtime[AgentDeps]) -> dict:
    return {
        "annotations": annotate_sentences(
            runtime.context,
            state["prompt"],
            state["sentences"],
            max_issues=state["max_issues"],
            max_praises=state["max_praises"],
            limit=state["limit"],
            floor=state["floor"],
            full_credit=state.get("full_credit", False),
        )
    }


def build_annotate_graph():
    graph = StateGraph(AnnotateState, context_schema=AgentDeps)
    graph.add_node("annotate", _annotate_node)
    graph.add_edge(START, "annotate")
    graph.add_edge("annotate", END)
    return graph.compile()


ANNOTATE_GRAPH = build_annotate_graph()

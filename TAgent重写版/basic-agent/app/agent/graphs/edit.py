"""文件编辑：给一段文字 → 带原文区间的修改建议 → 用户采纳的几条应用回去。

    START → suggest → END

**这一轮只铺路**：后端 + 单测，还没接上传、存储和界面，也没接路由。
下一轮接的时候要先定文件存在哪——后端现在没有任何文件存储；输入框的
「上传文件」只记了文件名、内容根本没读。

流程和逐句批注是同一套（annotate.py）：切句编号 → 问一次模型 → 校验编号与定额 →
挂原文区间。应用修改是纯函数 apply_edits（app/schema/edit.py），不经模型。

和批注的一处不同：批注失败降级成空列表（锦上添花，分数早就有了）；修改建议失败
要报错——用户是专门来要建议的，回一个空列表等于告诉他「没什么好改的」，是误导。
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.agent.nodes import json_call
from app.agent.runtime import AgentDeps
from app.config import EDIT_LLM_TIMEOUT, EDIT_MAX_SUGGESTIONS, EDIT_MIN_ATTEMPT_TIMEOUT
from app.prompts.edit_prompts import build_edit_prompt
from app.schema.edit import EditSuggestion, LLMEditBatch, attach_edit_spans, validate_edits
from app.schema.essay import numbered_text
from app.util.text import split_sentences


def suggest_edits(
    deps: AgentDeps,
    source: str,
    *,
    instruction: str | None = None,
    max_edits: int = EDIT_MAX_SUGGESTIONS,
) -> list[EditSuggestion]:
    sentences = split_sentences(source)
    if not sentences:
        return []
    batch = json_call(
        deps,
        build_edit_prompt(numbered_text(sentences), instruction=instruction, max_edits=max_edits),
        LLMEditBatch,
        # 每条要写一整句改写，比批注长
        max_tokens=300 + 300 * max_edits,
        limit=EDIT_LLM_TIMEOUT,
        floor=EDIT_MIN_ATTEMPT_TIMEOUT,
        # 编错句号、超定额、改了等于没改，都在重试圈里重来
        post_validate=lambda value: validate_edits(value, sentences, max_edits=max_edits),
    )
    return attach_edit_spans(batch, sentences)


class EditState(TypedDict, total=False):
    source: str
    instruction: str | None
    suggestions: list[EditSuggestion]


def _suggest(state: EditState, runtime: Runtime[AgentDeps]) -> dict:
    return {
        "suggestions": suggest_edits(
            runtime.context, state["source"], instruction=state.get("instruction")
        )
    }


def build_edit_graph():
    graph = StateGraph(EditState, context_schema=AgentDeps)
    graph.add_node("suggest", _suggest)
    graph.add_edge(START, "suggest")
    graph.add_edge("suggest", END)
    return graph.compile()


EDIT_GRAPH = build_edit_graph()

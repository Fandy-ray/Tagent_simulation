"""答疑：理解问题 → 检索 → 生成。流式和非流式走同一张图。

    START → understand → retrieve ─┬─（非流式）→ generate → END
                                   └─（流式）──→ END，调用方接着逐块生成

三步各管一件事，原因都来自实测：

1. **理解问题**（understand）
   追问「那它的前提呢」里没有任何可检索的实词，直接拿去检索会命中
   「Pareto 前沿」这类毫不相干的东西（实测检索到了供应链和 COVID-19）。
   生成那一步有完整对话历史所以答得出来，但材料是错的——一旦问到教材里
   才有的内容就会露馅。这一步把上文的话题词补进检索词，**不调模型**。

2. **检索**（retrieve）

3. **生成**（generate），外加每次请求的可调参数（answer_client）。

为什么流式在检索之后就出图、由调用方自己逐块生成：LangGraph 的 stream 在消费方
中途关掉时，会**等节点跑完**才返回（实测：读了 2 块就关，关的那一下等到 10 块全写完）。
逐块生成要是放在节点里，学生点「停止」或断开之后，模型照样生成到底、照样计费，
请求线程也一直被占着。调用方自己拿着上游的流，一关就断。

两条路共用前两步和 answer_client / prompt_messages，同一个问题检索词一样、
提示词一样、可调参数一样，只差最后是一次拿完还是逐块拿。
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.agent.runtime import AgentDeps
from app.infra.model_client_factory import tuning_bind_kwargs
from app.prompts.chat_prompts import build_prompt_messages
from app.rag.followup import resolve_query
from app.util.text import content_text


# 回答被长度上限（「控制」里的 max_tokens，或模型自己的上限）截断时补的一句。
# 不补的话学生只看到话说到一半，常常还停在半截公式上，分不清是被截断了还是
# 模型就这么答的（2026-10-24 页面实测：结尾留着一个 $$，后面什么都没有）。
TRUNCATED_NOTE = "\n\n（回答到了长度上限，后面被截掉了。想看完整回答，可以在「控制」里把 max_tokens 调大再重新生成。）"


def truncation_tail(text: str) -> str:
    """截断时接在回答后面的内容：先把截在半中间的公式收尾，再补说明。

    公式不收尾的话，后面那句说明会被当成公式的一部分，渲染出来一团乱。
    """
    tail = ""
    if text.count("$$") % 2:
        tail += "\n$$"
    if text.replace("$$", "").count("$") % 2:
        tail += "$"
    return tail + TRUNCATED_NOTE


class AnswerState(TypedDict, total=False):
    messages: list[dict[str, str]]
    query: str
    # 前端显式给的检索词（论文模式）不该再补上文，补了只会冲淡它
    query_is_explicit: bool
    notebook_ids: list[str]
    mode: str
    # True：检索完就出图，生成交给调用方逐块做
    stream: bool
    retrieved_context: str
    retrieved_documents: list[Any]
    content: str
    step_log: list[str]


def answer_client(deps: AgentDeps):
    """答疑用的客户端，绑上这次请求的可调参数（温度、最大长度……）。"""
    client = deps.client_factory.get(deps.provider)
    bind_kwargs = tuning_bind_kwargs(deps.provider, deps.tuning)
    if bind_kwargs:
        # 绑在缓存好的 client 上，不进缓存键——否则换个温度就多一个连接池
        client = client.bind(**bind_kwargs)
    return client


def prompt_messages(state: AnswerState) -> list[dict[str, str]]:
    return build_prompt_messages(
        state["messages"], state["retrieved_context"], mode=state.get("mode", "qa")
    )


def _understand(state: AnswerState) -> dict:
    """把指代型追问补成能检索的问题。前端显式给了检索词时让它优先。"""
    asked = state.get("query", "")
    log = state.get("step_log", [])
    if state.get("query_is_explicit"):
        return {"step_log": [*log, "Using the caller's retrieval query."]}
    resolved = resolve_query(state.get("messages") or [], asked)
    if resolved == asked:
        return {"step_log": [*log, "Question is self-contained."]}
    return {
        "query": resolved,
        "step_log": [*log, "Resolved a follow-up question against the conversation."],
    }


def _retrieve(state: AnswerState, runtime: Runtime[AgentDeps]) -> dict:
    context, documents = runtime.context.knowledge_base.retrieve(
        state["query"], notebook_ids=state.get("notebook_ids")
    )
    return {
        "retrieved_context": context,
        "retrieved_documents": documents,
        "step_log": [*state.get("step_log", []), f"Retrieved {len(documents)} knowledge chunks."],
    }


def _generate(state: AnswerState, runtime: Runtime[AgentDeps]) -> dict:
    response = answer_client(runtime.context).invoke(prompt_messages(state))
    content = content_text(response.content)
    metadata = getattr(response, "response_metadata", None) or {}
    if metadata.get("finish_reason") == "length":
        content += truncation_tail(content)
    return {
        "content": content,
        "step_log": [*state.get("step_log", []), "Generated the answer."],
    }


def _after_retrieve(state: AnswerState) -> str:
    return END if state.get("stream") else "generate"


def build_answer_graph():
    graph = StateGraph(AnswerState, context_schema=AgentDeps)
    graph.add_node("understand", _understand)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("generate", _generate)
    graph.add_edge(START, "understand")
    graph.add_edge("understand", "retrieve")
    graph.add_conditional_edges("retrieve", _after_retrieve, ["generate", END])
    graph.add_edge("generate", END)
    return graph.compile()


ANSWER_GRAPH = build_answer_graph()

"""答疑子图：理解问题 → 检索 → 生成。

图本身不持有业务状态，依赖由 build_answer_graph 闭包注入，
这样 ChatService 只需要拿到一个编译好的 graph。

三步各管一件事，原因都来自实测：

1. **理解问题**（understand_question）
   追问「那它的前提呢」里没有任何可检索的实词，直接拿去检索会命中
   「Pareto 前沿」这类毫不相干的东西（实测检索到了供应链和 COVID-19）。
   生成那一步有完整对话历史所以答得出来，但材料是错的——一旦问到教材里
   才有的内容就会露馅。这一步把上文的话题词补进检索词，**不调模型**。

2. **检索**（retrieve_context）
   原样保留。

3. **生成**（generate_answer）
   原样保留，外加每次请求的可调参数。

流式回答不走这张图（它要逐块 yield），但**第一步是共用的**：
ChatService.stream_answer 调同一个 resolve_query，否则流式和非流式会按
两套检索词取材，同一个问题两条路给出的依据不一样。
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.infra.model_client_factory import tuning_bind_kwargs
from app.prompts.chat_prompts import build_prompt_messages
from app.rag.followup import resolve_query
from app.schema.provider import ModelProvider
from app.util.text import content_text


class RAGState(TypedDict, total=False):
    messages: list[dict[str, str]]
    provider: ModelProvider
    tuning: dict
    query: str
    # 前端显式给的检索词（论文模式）不该再补上文，补了只会冲淡它
    query_is_explicit: bool
    notebook_ids: list[str]
    mode: str
    retrieved_context: str
    retrieved_documents: list[Any]
    content: str
    step_log: list[str]


def build_answer_graph(knowledge_base, client_factory):
    def understand_node(state: RAGState):
        """把指代型追问补成能检索的问题。前端显式给了检索词时让它优先。"""
        asked = state.get("query", "")
        if state.get("query_is_explicit"):
            return {"step_log": [*state.get("step_log", []), "Using the caller's retrieval query."]}
        resolved = resolve_query(state.get("messages") or [], asked)
        if resolved == asked:
            return {"step_log": [*state.get("step_log", []), "Question is self-contained."]}
        return {
            "query": resolved,
            "step_log": [
                *state.get("step_log", []),
                "Resolved a follow-up question against the conversation.",
            ],
        }

    def retrieve_node(state: RAGState):
        context, documents = knowledge_base.retrieve(
            state["query"], notebook_ids=state.get("notebook_ids")
        )
        return {
            "retrieved_context": context,
            "retrieved_documents": documents,
            "step_log": [*state.get("step_log", []), f"Retrieved {len(documents)} knowledge chunks."],
        }

    def answer_node(state: RAGState):
        messages = build_prompt_messages(
            state["messages"], state["retrieved_context"], mode=state.get("mode", "qa")
        )
        client = client_factory.get(state["provider"])
        bind_kwargs = tuning_bind_kwargs(state["provider"], state.get("tuning"))
        if bind_kwargs:
            client = client.bind(**bind_kwargs)
        response = client.invoke(messages)
        return {
            "content": content_text(response.content),
            "step_log": [*state.get("step_log", []), "Generated the answer."],
        }

    builder = StateGraph(RAGState)
    builder.add_node("understand_question", understand_node)
    builder.add_node("retrieve_context", retrieve_node)
    builder.add_node("generate_answer", answer_node)
    builder.add_edge(START, "understand_question")
    builder.add_edge("understand_question", "retrieve_context")
    builder.add_edge("retrieve_context", "generate_answer")
    builder.add_edge("generate_answer", END)
    return builder.compile()

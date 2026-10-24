"""RAG 对话服务。

service 层规则：不 import flask，不认识 request/current_app。
收普通参数，返回普通对象；流式接口返回裸生成器，
由 api 层用 stream_with_context 包起来。
"""

from __future__ import annotations

import math
from typing import Any, Callable

from app.agent.graphs.answer import ANSWER_GRAPH, answer_client, prompt_messages
from app.agent.runtime import AgentDeps
from app.errors.api_errors import AgentAPIError
from app.infra.upstream_errors import translate_upstream_error
from app.prompts.chat_prompts import last_user_message
from app.rag.citations import citations_from_documents
from app.schema.provider import ModelProvider
from app.util.text import content_text


# 上游没说「答完了」就断了流：多半是连接中途断开。不补这一句，前端会把半截回答
# 当成完整回答显示，还带着追问建议（压测 F3）。
STREAM_INTERRUPTED_NOTE = "\n\n（回答中断：和模型服务的连接断开了，可以点「重新生成」再试一次。）"
# 上游没给 finish_reason 就断了：内部用这个值标出来（学习记录里如实记「没答完」），
# 发给前端时 openai_view 会换回标准的 "stop"，OpenAI 兼容的客户端不认识自造的值
FINISH_INTERRUPTED = "interrupted"
# 流到一半服务端出错时发给前端的那一句（openai_view 用）
STREAM_FAILED_NOTE = "\n\n（回答中断：模型服务出错了，可以点「重新生成」再试一次。）"


def _retrieval_query(messages: list[dict[str, str]], retrieval_query: str | None) -> tuple[str, bool]:
    """返回 (检索词, 是不是前端显式给的)。

    前端显式给的（论文模式的「题目 + 关键词」）要原样用，**不能**再去补上文：
    它本来就是替代原问题的检索提示，补一遍只会把它冲淡。

    没给的时候返回原问题，由图里「理解问题」那一步决定要不要补上文。

    last_user_message 无论如何都要调——没有用户消息的请求照旧 400。
    """
    question = last_user_message(messages)
    if retrieval_query:
        return retrieval_query, True
    return question, False


class ChatService:
    """答疑的门面。流程在 app/agent/graphs/answer.py；答疑不走闸门。"""

    def __init__(self, knowledge_base, client_factory):
        self.knowledge_base = knowledge_base
        self.client_factory = client_factory

    def _run(
        self,
        messages: list[dict[str, str]],
        provider: ModelProvider,
        notebook_ids: list[str] | None,
        *,
        mode: str,
        retrieval_query: str | None,
        tuning: dict[str, Any] | None,
        stream: bool,
    ) -> tuple[dict[str, Any], AgentDeps]:
        """跑一遍答疑图。stream=True 时检索完就返回，生成留给调用方逐块做。"""
        deps = AgentDeps(
            knowledge_base=self.knowledge_base,
            client_factory=self.client_factory,
            provider=provider,
            # 答疑不设总预算：回答多长由学生定，单次调用的超时由模型客户端自己管
            deadline=math.inf,
            tuning=tuning or {},
        )
        query, explicit = _retrieval_query(messages, retrieval_query)
        state = ANSWER_GRAPH.invoke(
            {
                "messages": messages,
                "query": query,
                "query_is_explicit": explicit,
                "notebook_ids": notebook_ids or [],
                "mode": mode,
                "stream": stream,
                "step_log": [],
            },
            context=deps,
        )
        return state, deps

    def answer(
        self,
        messages: list[dict[str, str]],
        provider: ModelProvider,
        notebook_ids: list[str] | None = None,
        *,
        mode: str = "qa",
        retrieval_query: str | None = None,
        tuning: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            result, _ = self._run(
                messages, provider, notebook_ids,
                mode=mode, retrieval_query=retrieval_query, tuning=tuning, stream=False,
            )
            return {
                "content": result["content"],
                "retrieved_context": result.get("retrieved_context", ""),
                "citations": citations_from_documents(result.get("retrieved_documents") or []),
                "step_log": result.get("step_log", []),
            }
        except AgentAPIError:
            raise
        except Exception as exc:
            raise translate_upstream_error(exc) from exc

    def stream_answer(
        self,
        messages: list[dict[str, str]],
        provider: ModelProvider,
        notebook_ids: list[str] | None = None,
        *,
        mode: str = "qa",
        retrieval_query: str | None = None,
        tuning: dict[str, Any] | None = None,
        on_citations: Callable[[list[dict[str, Any]]], None] | None = None,
    ):
        """产出 (文字, 结束原因)。检索完、开始生成之前，用到的材料的出处交给 on_citations。

        出处不混进产出里：别处都按两元组读这个生成器。
        逐块生成在这里而不在图里，原因见 app/agent/graphs/answer.py 开头：
        学生点停止、生成器被关掉时，上游的流要跟着立刻断。
        """
        try:
            state, deps = self._run(
                messages, provider, notebook_ids,
                mode=mode, retrieval_query=retrieval_query, tuning=tuning, stream=True,
            )
            if on_citations is not None:
                on_citations(citations_from_documents(state.get("retrieved_documents") or []))
            finish_reason = None
            for chunk in answer_client(deps).stream(prompt_messages(state)):
                metadata = getattr(chunk, "response_metadata", None) or {}
                # A final usage-only chunk can contain finish_reason=None.
                # It must not erase the preceding stop/length/filter reason.
                if metadata.get("finish_reason"):
                    finish_reason = metadata["finish_reason"]
                content = content_text(chunk.content)
                if content:
                    yield content, None
            if finish_reason is None:
                yield STREAM_INTERRUPTED_NOTE, None
                finish_reason = FINISH_INTERRUPTED
            yield "", finish_reason
        except AgentAPIError:
            raise
        except Exception as exc:
            raise translate_upstream_error(exc) from exc

"""OpenAI 兼容线格式的响应组装（含 SSE 流）。

放在 api 层而不是 service：这里做的全是"把 service 的返回值摆成 OpenAI 的样子"，
是表示层的事。/v1/chat/completions 与 /internal/v1/chat/completions 共用本模块，
两个 controller 因此不必互相 import。

注意 stream_with_context 必须留在本层：service 只返回裸生成器，
一旦生成器跨出请求上下文再被消费，Flask 的 request 就没了。
"""

from __future__ import annotations

import json
import time
import uuid

from flask import Response, jsonify, stream_with_context

from app.api.deps import get_chat_service
from app.api.learner import current_learner, note_chat
from app.service.chat_service import FINISH_INTERRUPTED, STREAM_FAILED_NOTE
from app.api.validators import (
    chat_mode,
    chat_retrieval_query,
    chat_tuning,
    optional_notebook_ids,
    validate_messages,
)


def _chunk(
    chat_id: str,
    created: int,
    model: str,
    content: str | None,
    finish_reason=None,
    *,
    role: str | None = None,
):
    if role is not None:
        delta = {"role": role}
    else:
        delta = {} if content is None else {"content": content}
    return {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def _citations_chunk(chat_id: str, created: int, model: str, citations: list) -> dict:
    """出处单独一帧：delta 为空，OpenAI 兼容的客户端照常跳过；前端从顶层的 citations 读。"""
    return {**_chunk(chat_id, created, model, None), "citations": list(citations)}


def chat_completion_response(data, provider):
    messages = validate_messages(data.get("messages"))
    notebook_ids = optional_notebook_ids(data)
    options = {
        "mode": chat_mode(data),
        "retrieval_query": chat_retrieval_query(data),
        "tuning": chat_tuning(data),
    }
    service = get_chat_service()
    chat_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    # 认人要趁现在：流式回答的生成器是在这个函数返回之后才被消费的
    learner = current_learner()
    started_at = time.monotonic()

    def remember(answer: str, finish_reason: str) -> None:
        note_chat(
            learner,
            provider,
            mode=options["mode"],
            messages=messages,
            answer=answer,
            finish_reason=finish_reason,
            notebook_ids=notebook_ids,
            started_at=started_at,
        )

    if not data.get("stream", False):
        result = service.answer(messages, provider, notebook_ids=notebook_ids, **options)
        remember(result["content"], "stop")
        return jsonify(
            {
                "id": chat_id,
                "object": "chat.completion",
                "created": created,
                "model": provider.served_model_id,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": result["content"]},
                        "logprobs": None,
                        "finish_reason": "stop",
                    }
                ],
                # 不是 OpenAI 的标准字段，客户端不认识会忽略；前端拿它列「参考资料」
                "citations": result.get("citations", []),
            }
        )

    def generate():
        # 检索一完成 stream_answer 就把出处交过来，这里在第一段文字之前单独发一帧
        citations: list = []
        iterator = iter(
            service.stream_answer(
                messages,
                provider,
                notebook_ids=notebook_ids,
                on_citations=citations.extend,
                **options,
            )
        )
        finish_reason = "stop"
        # 记进学习记录的那份回答。学生中途点了「停止」或刷新（GeneratorExit）、上游出错，
        # 也把已经说出来的部分记下，并如实标成 interrupted / error，而不是当成答完了。
        spoken: list[str] = []
        outcome = "interrupted"
        try:
            role_chunk = _chunk(
                chat_id,
                created,
                provider.served_model_id,
                None,
                role="assistant",
            )
            yield f"data: {json.dumps(role_chunk, ensure_ascii=False)}\n\n"
            for item in iterator:
                if citations:
                    frame = _citations_chunk(chat_id, created, provider.served_model_id, citations)
                    yield f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"
                    citations.clear()
                if isinstance(item, tuple) and len(item) == 2:
                    token, item_finish_reason = item
                else:
                    token, item_finish_reason = item, None
                if item_finish_reason:
                    finish_reason = item_finish_reason
                if token:
                    spoken.append(str(token))
                    payload = _chunk(
                        chat_id,
                        created,
                        provider.served_model_id,
                        str(token),
                    )
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            outcome = finish_reason
        except GeneratorExit:
            raise
        except Exception:
            outcome = "error"
            payload = _chunk(
                chat_id,
                created,
                provider.served_model_id,
                STREAM_FAILED_NOTE,
            )
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            close = getattr(iterator, "close", None)
            if callable(close):
                close()
            remember("".join(spoken), outcome)
        final_chunk = _chunk(
            chat_id,
            created,
            provider.served_model_id,
            None,
            # 线上只发 OpenAI 认识的值；中断已经用正文末尾的说明告诉学生了
            "stop" if finish_reason == FINISH_INTERRUPTED else finish_reason,
        )
        yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

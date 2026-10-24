"""共用节点。出题、闪卡、判卷、批改、批注、文件编辑都从这里调模型。

只有一个函数真正碰模型：json_call。它把「算超时 → 取客户端 → 绑输出上限 →
带校验地调用」这一串收在一处，原来各条链路各写一遍。

校验一律走 post_validate：放在 call_json_llm 的重试圈**里面**，不合格就重试；
放在外面的话一次不合格就直接 500（批改那边实测踩过）。
"""

from __future__ import annotations

import time
from typing import Any, Callable

from app.agent.runtime import AgentDeps, attempt_timeout
from app.infra import llm_json


def json_call(
    deps: AgentDeps,
    prompt: str,
    model_cls: Any,
    *,
    max_tokens: int,
    limit: float,
    floor: float,
    post_validate: Callable[[Any], None] | None = None,
    budget: float | None = None,
    started: float | None = None,
) -> Any:
    """带预算、带校验的一次 JSON 调用。

    budget 默认是「离截止时间还剩多少」。判卷那种要把剩余预算按批次平分的，
    显式传进来（并传 started），别让靠前的批次吃掉整个预算。
    """
    if budget is None:
        started = time.monotonic()
        budget = max(0.0, deps.deadline - started)
    timeout = attempt_timeout(limit, floor, budget)
    client = deps.client_factory.get(
        deps.provider, timeout_seconds=int(timeout), max_retries=0
    ).bind(max_tokens=max_tokens)
    # 经由模块属性调用，单测才能 monkeypatch app.infra.llm_json.call_json_llm
    return llm_json.call_json_llm(
        client,
        prompt,
        model_cls,
        attempt_timeout=timeout,
        budget_seconds=budget,
        post_validate=post_validate,
        start_time=started,
    )


def search_text(
    deps: AgentDeps,
    query: str,
    *,
    k: int,
    piece_chars: int,
    char_limit: int,
    notebook_ids: list[str] | None = None,
) -> str:
    """检索并拼成一段参考材料。检索失败给空串，不让整次运行跟着失败。

    只给「材料是辅助」的链路用（批改、出小论文题）：没材料也还能评、还能出题，
    只是判得保守些、题目泛一些。出卷没材料就出不了题，走 sample_exam_context。
    """
    try:
        documents = deps.knowledge_base.search(query, k=k, notebook_ids=notebook_ids)
    except Exception:
        return ""
    joined = "\n\n---\n\n".join(d.page_content[:piece_chars] for d in documents)
    return joined[:char_limit]

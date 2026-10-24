"""共用节点。出题、闪卡、判卷、批改、批注、文件编辑都从这里调模型。

只有一个函数真正碰模型：json_call。它把「算超时 → 取客户端 → 绑输出上限 →
带校验地调用」这一串收在一处，原来各条链路各写一遍。

校验一律走 post_validate：放在 call_json_llm 的重试圈**里面**，不合格就重试；
放在外面的话一次不合格就直接 500（批改那边实测踩过）。
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable

from pydantic import ValidationError

from app.agent.runtime import AgentDeps, attempt_timeout
from app.config import UPSTREAM_STALL_SECONDS
from app.errors.exam_errors import InvalidExamRequestError
from app.infra import llm_json
from app.util.json_items import JsonItemScanner

log = logging.getLogger(__name__)


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
    open_reader: Callable[[], Callable[[str], None]] | None = None,
) -> Any:
    """带预算、带校验的一次 JSON 调用。

    budget 默认是「离截止时间还剩多少」。判卷那种要把剩余预算按批次平分的，
    显式传进来（并传 started），别让靠前的批次吃掉整个预算。
    open_reader 给了就边收边读（见 llm_json.StreamingClient），返回值不变。

    **一律流式读**，两个超时各管一件事：
    - 客户端的读超时 = UPSTREAM_STALL_SECONDS：流式读时它量的是「两段数据之间隔了多久」，
      隔这么久一个字节都没有就是上游卡住了（llm_json 会在预算内重试一次）；
    - 单次总上限 = attempt_timeout（limit 封顶），由 invoke_with_deadline 硬截断。
      先思考的模型（Qwen3、GLM、DeepSeek 推理模式）一次要几十秒是正常的，它们一直在吐
      思考的内容，不会被当成卡住。
    以前不流式，读超时只能设成总上限（出卷 150 秒），上游卡住时要干等满 150 秒。
    客户端按固定的读超时取，缓存里每个模型只有这一个，不再随剩余预算变来变去。
    """
    if budget is None:
        started = time.monotonic()
        budget = max(0.0, deps.deadline - started)
    timeout = attempt_timeout(limit, floor, budget)
    client = deps.client_factory.get(
        deps.provider, timeout_seconds=UPSTREAM_STALL_SECONDS, max_retries=0
    ).bind(max_tokens=max_tokens)
    client = llm_json.StreamingClient(client, open_reader or _skip_pieces)
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


def _skip_pieces() -> Callable[[str], None]:
    """不需要边收边读时的 reader：流式读只是为了用上卡住检测。"""
    return lambda _piece: None


_FINISHED = object()


def json_call_streaming(
    deps: AgentDeps,
    prompt: str,
    model_cls: Any,
    *,
    item_cls: Any,
    on_item: Callable[[Any], None],
    on_title: Callable[[str], None] | None = None,
    **kwargs: Any,
) -> Any:
    """和 json_call 一样调、一样校验、一样返回整段；另外边写边把写完的每一项交出去。

    模型每写完数组里的一项，就用 item_cls 校验，合格的交给 on_item；顶层的 title
    一写完交给 on_title。不合格的那一项跳过（整段校验时自有定论）。

    on_item / on_title 在**调用方自己的线程**里执行：LangGraph 的 stream writer
    只认节点自己的线程（换个线程调会报 outside of a runnable context）。所以调用
    放到一个工作线程里跑，这边一边等一边把收到的项转交出去。

    重试时上一次已经交出去的项不收回；调用方要自己去重。
    """
    events: queue.SimpleQueue = queue.SimpleQueue()

    def open_reader() -> Callable[[str], None]:
        scanner = JsonItemScanner()
        titled = False

        def read(piece: str) -> None:
            nonlocal titled
            for raw in scanner.feed(piece):
                events.put(("item", raw))
            if not titled and scanner.title is not None:
                titled = True
                events.put(("title", scanner.title))

        return read

    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["value"] = json_call(deps, prompt, model_cls, open_reader=open_reader, **kwargs)
        except BaseException as exc:  # noqa: BLE001 —— 原样带回调用方的线程再抛
            outcome["error"] = exc
        finally:
            events.put((_FINISHED, None))

    threading.Thread(target=run, name="json-call-streaming", daemon=True).start()
    while True:
        kind, value = events.get()
        if kind is _FINISHED:
            break
        if kind == "title":
            if on_title is not None:
                on_title(value)
            continue
        try:
            item = item_cls.model_validate_json(value)
        except ValidationError as exc:
            log.info("边写边读时跳过一项不合格的：%s", exc.errors()[0].get("msg", "") if exc.errors() else "")
            continue
        on_item(item)
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


# 论文片段的来源标记（app/rag/references.py）
PAPER_SOURCE = "reference"


def sample_quiz_material(
    deps: AgentDeps, topic: str | None, notebook_ids: list[str] | None
) -> tuple[list[str], list[str]]:
    """抽出题材料，返回 (全部片段, 填空选择用的片段)。整卷和闪卡共用。

    填空、选择只用教材片段，论文片段只给大题：材料切得小，分到论文片段的那一路
    只能从论文里挑，出来的是「小区开放后的改善率怎么定义」这类论文独有的细节
    （整卷评委统计每卷 2.1 道，只给教材后 0 道）。一片教材都没有（例如只选了论文）
    时只好全用上。

    一片材料都没有就当场 422。不拦的话各路照样去调模型，「仅依据参考材料出题」
    却没有材料，白等一轮之后多半是 502，学生还不知道是笔记本选错了。
    """
    pieces = [
        (text, source)
        for text, source in deps.knowledge_base.sample_exam_pieces(topic, notebook_ids=notebook_ids)
        if (text or "").strip()
    ]
    if not pieces:
        raise InvalidExamRequestError("所选知识范围里没有可出题的材料，请换一个笔记本或来源")
    texts = [text for text, _ in pieces]
    textbook = [text for text, source in pieces if source != PAPER_SOURCE]
    return texts, textbook or texts


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
    只是判得保守些、题目泛一些。出卷、出闪卡没材料就出不了题，走 sample_quiz_material（没材料当场 422）。
    """
    try:
        documents = deps.knowledge_base.search(query, k=k, notebook_ids=notebook_ids)
    except Exception:
        return ""
    joined = "\n\n---\n\n".join(d.page_content[:piece_chars] for d in documents)
    return joined[:char_limit]

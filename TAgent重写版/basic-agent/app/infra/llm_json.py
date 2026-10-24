"""结构化 JSON LLM 调用封装（出题/判分共用）。

设计约束：
- 操作级硬 deadline：预算可从 generate/review 操作入口起算（start_time，
  把知识库采样、FAISS 检索的耗时也计入），每次 LLM 调用再用
  asyncio.wait_for 施加硬墙钟截断——ChatOpenAI(timeout=..) 底层是 HTTPX
  的 connect/read/write 分阶段超时，不是总墙钟上限，慢 token 流可以无限拖；
- 每次尝试都做完整验证：空内容检查 → JSON/Pydantic 解析 → post_validate
  （判分 ID 集校验等），任何一步失败都算本次尝试失败，可在预算内重试；
- 错误脱敏：Pydantic ValidationError 可能回显 input_value（含试卷答案），
  详细错误只写日志，对外异常只携带固定文案。

不依赖 langchain，llm 只需提供 .ainvoke(prompt) 协程（返回值带 .content），
可离线单测。
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
import types
from typing import Callable, Optional

import openai

from app.config import AgentConfig
from app.errors.exam_errors import ExamBusyError, UpstreamLLMError, UpstreamTimeoutError
from app.util.text import content_text

log = logging.getLogger(__name__)


_OUTER_FENCE = re.compile(r"^```[A-Za-z]*\s*(.*)```\s*$", re.DOTALL)


def extract_json(text: str) -> str:
    """兜底：模型偶尔无视 JSON mode 包一层代码块时，剥出其中的 JSON。

    只剥**最外层**的包装。以前是在全文里找第一个 ``` 代码块：教材里有 C 代码，
    模型把 ```c ... ``` 写进了大题的参考答案（JSON 字符串里），结果取出来的是那段 C 代码，
    整卷连着两次「输出结构异常」出不了卷（2026-10-02 实测）。
    """
    stripped = (text or "").strip()
    if stripped[:1] in ("{", "["):
        return stripped  # 本身就是 JSON：字符串里的 ``` 是内容，不是包装
    fenced = _OUTER_FENCE.match(stripped)
    if fenced:
        return fenced.group(1).strip()  # 贪婪到最后一个 ```：里面再有代码块也整段保留
    # 前后夹了说明文字：取第一个 { / [ 到最后一个 } / ]
    starts = [i for i in (stripped.find("{"), stripped.find("[")) if i >= 0]
    end = max(stripped.rfind("}"), stripped.rfind("]"))
    if starts and end > min(starts):
        return stripped[min(starts) : end + 1]
    return stripped


# ====================== 硬墙钟超时调用 ======================
_loop_lock = threading.Lock()
_shared_loop: Optional[asyncio.AbstractEventLoop] = None


def _get_shared_loop() -> asyncio.AbstractEventLoop:
    """常驻后台事件循环（懒创建，daemon 线程驱动）。

    AsyncOpenAI 的 HTTPX 连接池绑定创建它的 loop：若每次调用 asyncio.run
    新建 loop，第二次调用会复用属于已关闭 loop 的连接（Event loop is closed），
    因此所有异步 LLM 调用固定提交到同一个后台 loop 执行。
    """
    global _shared_loop
    with _loop_lock:
        if _shared_loop is None or _shared_loop.is_closed():
            loop = asyncio.new_event_loop()
            threading.Thread(
                target=loop.run_forever, name="llm-json-loop", daemon=True
            ).start()
            _shared_loop = loop
        return _shared_loop


# 孤儿任务额度：取消失败（协程吞掉 CancelledError）的底层调用仍在后台消耗
# 付费额度，且已不受 LLMGate 约束。在其真正结束前计入独立额度并封顶，
# 额度满时拒绝发起新调用（429），保证付费并发总量 ≤ 闸门容量 + 孤儿上限。
MAX_ORPHAN_TASKS = AgentConfig.from_env().llm_max_orphan_tasks
_orphan_lock = threading.Lock()
_orphan_tasks: set = set()


def orphan_task_count() -> int:
    with _orphan_lock:
        return len(_orphan_tasks)


def _register_orphan(task, loop) -> None:
    """把仍在运行的 loop 侧任务登记为孤儿；任务真正结束时自动摘除。

    注意必须追踪 asyncio.Task 本身：concurrent.futures.Future.cancel()
    会把外层 future 立即置为 CANCELLED（done() 变 True），但底层任务
    可能还活着。add_done_callback 非线程安全，经 call_soon_threadsafe 注册。
    """

    def _cleanup(t):
        with _orphan_lock:
            _orphan_tasks.discard(t)
        log.warning(f"孤儿 LLM 任务已结束并释放额度（剩余孤儿数 {orphan_task_count()}）")

    with _orphan_lock:
        _orphan_tasks.add(task)
    loop.call_soon_threadsafe(task.add_done_callback, _cleanup)
    log.error(f"LLM 调用取消失败，任务转为孤儿继续占用额度（当前孤儿数 {orphan_task_count()}）")


def invoke_with_deadline(
    runnable, input_data, timeout_seconds: float, cancel_grace_seconds: float = 5.0
):
    """带硬墙钟上限地调用 runnable.ainvoke：到点取消底层 HTTP 请求并抛 TimeoutError。

    同步接口（内部 wait_for + 取消），供 Flask 线程直接调用。

    双层兜底：wait_for 在 timeout_seconds 处发起取消；若协程延迟/吞掉
    CancelledError（wait_for 会一直等取消完成），外层 result() 再宽限
    cancel_grace_seconds 后强制返回——Flask 线程与并发闸门绝不无限等待。
    未能取消的底层任务注册为孤儿并占用独立额度（见 MAX_ORPHAN_TASKS），
    真实 ChatOpenAI 不会吞取消，孤儿只在极端情况下出现。
    """
    if orphan_task_count() >= MAX_ORPHAN_TASKS:
        raise ExamBusyError("出题/判分请求过多，请稍后再试")
    loop = _get_shared_loop()
    inner_holder: dict = {}

    async def _run():
        inner = asyncio.ensure_future(runnable.ainvoke(input_data))
        inner_holder["task"] = inner
        return await asyncio.wait_for(inner, timeout=timeout_seconds)

    future = asyncio.run_coroutine_threadsafe(_run(), loop)
    try:
        # 3.11+ 里 concurrent.futures.TimeoutError 与 asyncio.TimeoutError
        # 都是内置 TimeoutError 的别名，一个 except 同时覆盖两种来源
        return future.result(timeout=timeout_seconds + cancel_grace_seconds)
    except TimeoutError:
        future.cancel()  # 请求取消 loop 侧 _run（连带底层调用）后不再等待
        inner = inner_holder.get("task")
        if inner is not None and not inner.done():
            _register_orphan(inner, loop)
        raise


class StreamingClient:
    """把 ainvoke 换成边收边读：每收到一块就交给 reader，收完照样返回整条消息。

    给「写完一项先用一项」的调用用（闪卡第一张立马出，见 app/agent/nodes.py
    json_call_streaming）。call_json_llm 的超时、重试、校验一行不改：它看到的仍是一个
    ainvoke 返回整条消息的对象，超时取消的也照样是底层那次请求。

    每次 ainvoke（包括重试）先调 open_reader() 拿一个新的 reader，上一次读了一半的
    状态不会带进下一次。reader 在后台事件循环的线程里被调用，里面别做慢事。
    """

    def __init__(self, llm, open_reader: Callable[[], Callable[[str], None]]):
        self._llm = llm
        self._open_reader = open_reader

    @property
    def kwargs(self):
        # _with_more_tokens 靠它读出原来给的输出额度
        return getattr(self._llm, "kwargs", None)

    def bind(self, **kwargs):
        return StreamingClient(self._llm.bind(**kwargs), self._open_reader)

    async def ainvoke(self, prompt):
        read = self._open_reader()
        if not hasattr(self._llm, "astream"):
            # 不会流式的替身（单测）：整段当成一块
            message = await self._llm.ainvoke(prompt)
            read(content_text(message.content))
            return message
        whole = None
        async for chunk in self._llm.astream(prompt):
            # 消息块相加会把正文接起来、把 finish_reason 这些元数据并进来
            whole = chunk if whole is None else whole + chunk
            piece = content_text(chunk.content)
            if piece:
                read(piece)
        return whole if whole is not None else types.SimpleNamespace(content="", response_metadata={})


def invoke_legacy_llm(runnable, input_data, timeout_seconds: float):
    """旧版单题接口的 LLM 调用：硬墙钟超时 + 异常映射为 Upstream 错误。

    provider 异常不包进 200 响应，由路由层映射为 502/504。
    放在本模块（而非 service 层）以便离线单测覆盖映射语义。
    """
    try:
        return invoke_with_deadline(runnable, input_data, timeout_seconds)
    except (TimeoutError, openai.APITimeoutError) as e:
        raise UpstreamTimeoutError("AI 服务响应超时，请稍后重试") from e
    except openai.OpenAIError as e:
        log.warning(f"旧接口 LLM 调用失败：{e!r}")
        raise UpstreamLLMError("AI 服务暂时不可用，请稍后重试") from e


def call_json_llm(
    llm,
    prompt_text: str,
    model_cls,
    attempt_timeout: float,
    budget_seconds: float,
    post_validate: Optional[Callable] = None,
    clock: Callable[[], float] = time.monotonic,
    max_attempts: int = 2,
    start_time: Optional[float] = None,
    cancel_grace_seconds: float = 5.0,
):
    """JSON-mode 调用：空内容检查 + 预算内有限重试 + Pydantic/业务校验。

    预算从 start_time（操作入口时刻，缺省为当前时刻）起算：单次调用的最坏
    耗时是 attempt_timeout + cancel_grace_seconds（取消宽限也是真实墙钟），
    发起新尝试前检查剩余预算是否放得下这个最坏值，与 invoke_with_deadline
    的硬截断共同保证总耗时 ≤ budget_seconds，严格先于代理层超时结束。
    超时 → UpstreamTimeoutError(504)；孤儿额度满 → ExamBusyError(429)；
    连续失败 → UpstreamLLMError(502)。
    """
    start = clock() if start_time is None else start_time
    attempt_worst = attempt_timeout + cancel_grace_seconds
    last_err: Optional[Exception] = None
    truncated = False

    for attempt in range(max_attempts):
        remaining = budget_seconds - (clock() - start)
        if remaining < attempt_worst:
            if attempt == 0:
                # 预算配置错误，或调用前的采样/检索已耗尽预算
                raise UpstreamTimeoutError("服务繁忙，请稍后重试")
            break

        if truncated:
            # 上一次是被 max_tokens 截断的：同样的额度再来一次只会原样再断，加额度再试
            llm = _with_more_tokens(llm)
            truncated = False

        try:
            message = invoke_with_deadline(llm, prompt_text, attempt_timeout, cancel_grace_seconds)
        except ExamBusyError:
            raise  # 孤儿额度满：立刻 429，不重试
        except (TimeoutError, openai.APITimeoutError) as e:
            # 单次已耗尽 attempt_timeout（wait_for 硬截断或 SDK 超时），
            # 代理侧也在计时，不再重试
            log.warning(f"LLM 调用超时（attempt {attempt}）：{e!r}")
            raise UpstreamTimeoutError("AI 服务响应超时，请稍后重试") from e
        except Exception as e:
            log.warning(f"LLM 调用失败（attempt {attempt}）：{e!r}")
            if isinstance(e, openai.APIStatusError) and e.status_code in _FINAL_STATUS:
                # Key 不对、地址不对、请求本身不合法：重试也一样，别再白等一轮
                raise UpstreamLLMError(_status_message(e)) from e
            last_err = e
            continue

        raw = message.content
        text = str(raw).strip() if raw else ""
        truncated = _finish_reason(message) == "length"
        if truncated:
            log.warning(f"LLM 输出被 max_tokens 截断（attempt {attempt}，正文 {len(text)} 字）")
        if not text:
            log.warning(f"LLM 返回空内容（attempt {attempt}）")
            last_err = ValueError("LLM 返回空内容")
            continue

        try:
            result = model_cls.model_validate_json(extract_json(text))
            if post_validate is not None:
                post_validate(result)
            return result
        except Exception as e:
            # 详细错误（可能含试卷答案的 input_value 回显）只入日志
            log.warning(f"LLM 输出校验失败（attempt {attempt}）：{e!r}")
            last_err = e
            continue

    # 连不上上游和"上游回了但结构不对"是两码事。以前一律报"输出结构异常"，
    # 会把人引去查 prompt，而真正该查的是网络或 base_url/Key。
    if isinstance(last_err, openai.APIConnectionError):
        raise UpstreamLLMError("连不上模型服务，请检查网络，或确认模型的地址与 Key 可用") from last_err
    # 上游明确回了错误码，同样不是「输出结构」的问题（压测 S5：上游 500 被报成结构异常）
    if isinstance(last_err, openai.APIStatusError):
        raise UpstreamLLMError(_status_message(last_err)) from last_err
    if truncated:
        raise UpstreamLLMError(TRUNCATED_MESSAGE) from last_err
    raise UpstreamLLMError("AI 输出结构异常，请稍后重试") from last_err


# 会先思考的模型（DeepSeek 推理模式、Qwen3、GLM 等）把思考也算进 max_tokens：
# 额度给 256 时思考就用了 258，正文是空的（2026-10-07 Windows 测试报告）。
# 被截断（finish_reason == "length"）后下一次尝试加这么多额度，再封个顶，
# 免得一个回答拖满整段超时。
#
# 注意：langchain 的 ChatOpenAI 会把 max_tokens 改名成 max_completion_tokens 再发出去，
# 而 DeepSeek 只认 max_tokens（2026-10-08 实测：max_tokens=8 截在 8 个 token，
# max_completion_tokens=8 照常写了 96 个）。所以在 DeepSeek 上各处 bind 的额度并不生效，
# 也就不会被截断；认这个参数的上游（OpenAI 等）才会，这里的加额度重试是为它们准备的。
TRUNCATION_EXTRA_TOKENS = 4096
MAX_ESCALATED_TOKENS = 8192
TRUNCATED_MESSAGE = (
    "模型的输出被截断了：会先思考的模型可能把篇幅都用在了思考上。"
    "请稍后重试；经常出现的话，可在模型登记里关闭思考，或换用不思考的模型"
)


def _finish_reason(message) -> str:
    metadata = getattr(message, "response_metadata", None)
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get("finish_reason") or "")


def _with_more_tokens(llm):
    """调用方都是 client.bind(max_tokens=N) 传进来的；bind 会合并参数，再 bind 一次就覆盖掉 N。

    没 bind 过额度的（拿不到 N）原样返回：不知道原来给了多少，也就无从加。
    """
    current = (getattr(llm, "kwargs", None) or {}).get("max_tokens")
    if not isinstance(current, int) or not hasattr(llm, "bind"):
        return llm
    raised = min(current + TRUNCATION_EXTRA_TOKENS, MAX_ESCALATED_TOKENS)
    if raised <= current:
        return llm
    log.warning(f"上次输出被截断，max_tokens {current} → {raised} 再试")
    return llm.bind(max_tokens=raised)


# 重试也不会变好的上游状态码
_FINAL_STATUS = {400, 401, 403, 404, 422}


def _status_message(err: "openai.APIStatusError") -> str:
    code = err.status_code
    if code in (401, 403):
        return "模型服务拒绝了当前 Key，请重新登记模型"
    if code == 429:
        return "模型服务那边限流了，请稍后再试"
    if code >= 500:
        return f"模型服务暂时不可用（上游返回 {code}），请稍后再试"
    return f"模型服务拒绝了这次请求（上游返回 {code}），请检查模型配置"

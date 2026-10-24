"""app.infra.llm_json.call_json_llm 单测：预算控制、硬 deadline、重试语义、错误脱敏。离线运行。"""

import json
import asyncio
import threading
import time
import types

import httpx
import openai
import pytest
from pydantic import BaseModel, ConfigDict

from app.infra import llm_json
from app.errors.exam_errors import ExamBusyError, UpstreamLLMError, UpstreamTimeoutError
from app.infra.llm_json import (
    call_json_llm,
    extract_json,
    invoke_legacy_llm,
    invoke_with_deadline,
    orphan_task_count,
)


def wait_for_condition(cond, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


class ReleasableStubbornLLM:
    """吞掉取消、直到 release 置位才结束——验证孤儿登记与注销。"""

    def __init__(self):
        self.release = threading.Event()
        self.calls = 0

    async def ainvoke(self, prompt):
        self.calls += 1
        while not self.release.is_set():
            try:
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                pass  # 拒绝取消
        return types.SimpleNamespace(content='{"value": "late"}')


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeLLM:
    """脚本化 LLM：每次 invoke 依次消费 script 中的一项。

    项可以是：字符串（作为 content 返回）、异常实例（抛出）、
    (内容, 耗时) 元组——配合 FakeClock 模拟调用耗时。
    """

    def __init__(self, script, clock=None):
        self.script = list(script)
        self.clock = clock
        self.calls = 0

    def invoke(self, prompt):
        self.calls += 1
        item = self.script.pop(0)
        cost = 0.0
        if isinstance(item, tuple):
            item, cost = item
        if self.clock is not None:
            self.clock.now += cost
        if isinstance(item, Exception):
            raise item
        return types.SimpleNamespace(content=item)

    async def ainvoke(self, prompt):
        # 生产代码统一走 ainvoke（invoke_with_deadline 硬截断）
        return self.invoke(prompt)


def test_success_first_attempt():
    llm = FakeLLM(['{"value": "ok"}'])
    result = call_json_llm(llm, "p", Payload, attempt_timeout=80, budget_seconds=170)
    assert result.value == "ok"
    assert llm.calls == 1


def test_retry_on_invalid_json_within_budget():
    clock = FakeClock()
    llm = FakeLLM([("not json", 10.0), ('{"value": "ok"}', 10.0)], clock)
    result = call_json_llm(
        llm, "p", Payload, attempt_timeout=80, budget_seconds=170, clock=clock
    )
    assert result.value == "ok"
    assert llm.calls == 2


def test_no_retry_when_budget_exhausted():
    clock = FakeClock()
    # 第一次尝试耗时 100s：剩余 70 < attempt_timeout 80，不得发起第二次
    llm = FakeLLM([("not json", 100.0), ('{"value": "ok"}', 1.0)], clock)
    with pytest.raises(UpstreamLLMError):
        call_json_llm(llm, "p", Payload, attempt_timeout=80, budget_seconds=170, clock=clock)
    assert llm.calls == 1


def test_budget_smaller_than_one_attempt_raises_timeout():
    llm = FakeLLM(['{"value": "ok"}'])
    with pytest.raises(UpstreamTimeoutError):
        call_json_llm(llm, "p", Payload, attempt_timeout=80, budget_seconds=50)
    assert llm.calls == 0


def test_a_stalled_upstream_is_retried_once_within_budget():
    # 握手超时 / 太久没收到一个字节：上游卡住了，多半是一阵子的事，预算内重试一次
    llm = FakeLLM([openai.APITimeoutError(request=httpx.Request("POST", "http://t")), '{"value": "ok"}'])
    assert call_json_llm(llm, "p", Payload, attempt_timeout=80, budget_seconds=170).value == "ok"
    assert llm.calls == 2


def test_a_stall_while_streaming_counts_too():
    # 流式读到一半卡住时，SDK 不包装、原样抛 httpx 的读超时
    llm = FakeLLM([httpx.ReadTimeout("no bytes"), '{"value": "ok"}'])
    assert call_json_llm(llm, "p", Payload, attempt_timeout=80, budget_seconds=170).value == "ok"
    assert llm.calls == 2


def test_stalling_every_time_is_a_timeout_not_a_structure_error():
    stall = openai.APITimeoutError(request=httpx.Request("POST", "http://t"))
    llm = FakeLLM([stall, httpx.ReadTimeout("no bytes")])
    with pytest.raises(UpstreamTimeoutError):
        call_json_llm(llm, "p", Payload, attempt_timeout=80, budget_seconds=170)
    assert llm.calls == 2


def test_hard_deadline_cancels_slow_call():
    # ChatOpenAI 的 timeout 只是 HTTPX 分阶段超时，不是墙钟上限：
    # 一个 30s 都不返回的调用必须在 attempt_timeout 处被 wait_for 硬截断
    class SlowLLM:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, prompt):
            self.calls += 1
            await asyncio.sleep(30)
            return types.SimpleNamespace(content='{"value": "late"}')

    llm = SlowLLM()
    t0 = time.monotonic()
    with pytest.raises(UpstreamTimeoutError):
        call_json_llm(llm, "p", Payload, attempt_timeout=0.2, budget_seconds=10)
    assert time.monotonic() - t0 < 5  # 远小于 30s：调用被真实取消而非等到自然返回
    assert llm.calls == 1  # 超时不重试


def test_invoke_with_deadline_returns_result_within_limit():
    class QuickLLM:
        async def ainvoke(self, prompt):
            return types.SimpleNamespace(content="ok")

    assert invoke_with_deadline(QuickLLM(), "p", 5).content == "ok"


def test_uncancellable_coroutine_returns_and_registers_orphan():
    # wait_for 发起取消后会一直等协程真正退出；协程吞掉 CancelledError 时，
    # 外层 result(timeout) 必须在宽限期后强制返回（线程/闸门不挂死），
    # 且未死掉的任务被登记为孤儿、真正结束后自动摘除
    llm = ReleasableStubbornLLM()
    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        invoke_with_deadline(llm, "p", 0.2, cancel_grace_seconds=0.3)
    assert time.monotonic() - t0 < 3  # 0.2 + 0.3 宽限后强制返回，而非卡死
    assert llm.calls == 1
    assert orphan_task_count() == 1  # 后台任务仍在跑：计入孤儿额度

    llm.release.set()
    assert wait_for_condition(lambda: orphan_task_count() == 0)  # 结束后摘除


def test_orphan_quota_blocks_new_paid_calls(monkeypatch):
    monkeypatch.setattr(llm_json, "MAX_ORPHAN_TASKS", 1)

    stubborn = ReleasableStubbornLLM()
    with pytest.raises(TimeoutError):
        invoke_with_deadline(stubborn, "p", 0.1, cancel_grace_seconds=0.2)
    assert orphan_task_count() == 1

    # 孤儿额度已满：新调用立刻 429，绝不发起新的付费请求
    good = FakeLLM(['{"value": "ok"}'])
    with pytest.raises(ExamBusyError):
        call_json_llm(good, "p", Payload, attempt_timeout=1, budget_seconds=100)
    assert good.calls == 0

    # 孤儿真正结束后额度恢复
    stubborn.release.set()
    assert wait_for_condition(lambda: orphan_task_count() == 0)
    result = call_json_llm(good, "p", Payload, attempt_timeout=1, budget_seconds=100)
    assert result.value == "ok"


def test_budget_accounts_for_cancel_grace():
    # 单次最坏耗时是 attempt+grace：剩余 83 >= 80 但 < 85，不得发起第二次尝试
    clock = FakeClock()
    llm = FakeLLM([("not json", 87.0), ('{"value": "ok"}', 1.0)], clock)
    with pytest.raises(UpstreamLLMError):
        call_json_llm(llm, "p", Payload, attempt_timeout=80, budget_seconds=170, clock=clock)
    assert llm.calls == 1


# ====================== 旧接口调用封装 ======================
def test_invoke_legacy_llm_maps_openai_error_to_502():
    class BrokenLLM:
        async def ainvoke(self, prompt):
            raise openai.APIConnectionError(request=httpx.Request("POST", "http://t"))

    with pytest.raises(UpstreamLLMError) as exc_info:
        invoke_legacy_llm(BrokenLLM(), "p", 5)
    assert exc_info.value.status_code == 502


def test_invoke_legacy_llm_maps_timeouts_to_504():
    class TimeoutLLM:
        async def ainvoke(self, prompt):
            raise openai.APITimeoutError(request=httpx.Request("POST", "http://t"))

    with pytest.raises(UpstreamTimeoutError):
        invoke_legacy_llm(TimeoutLLM(), "p", 5)

    class SlowLLM:
        async def ainvoke(self, prompt):
            await asyncio.sleep(30)

    t0 = time.monotonic()
    with pytest.raises(UpstreamTimeoutError):
        invoke_legacy_llm(SlowLLM(), "p", 0.2)
    assert time.monotonic() - t0 < 6  # 硬墙钟截断（0.2s + 默认 5s 宽限内返回）


def test_budget_counts_from_operation_start():
    # 预算从操作入口起算：采样/检索已花掉 120s 时，剩余 50 < attempt_timeout 80，
    # 一次尝试都不允许发起，直接 504
    clock = FakeClock()
    clock.now = 120.0
    llm = FakeLLM(['{"value": "ok"}'])
    with pytest.raises(UpstreamTimeoutError):
        call_json_llm(
            llm, "p", Payload, attempt_timeout=80, budget_seconds=170,
            clock=clock, start_time=0.0,
        )
    assert llm.calls == 0


def test_post_validate_failure_counts_as_attempt_and_retries():
    llm = FakeLLM(['{"value": "bad-ids"}', '{"value": "good"}'])
    attempts = []

    def validate(result):
        attempts.append(result.value)
        if result.value == "bad-ids":
            raise ValueError("判分结果 ID 不匹配")

    result = call_json_llm(
        llm, "p", Payload, attempt_timeout=80, budget_seconds=170, post_validate=validate
    )
    assert result.value == "good"
    assert attempts == ["bad-ids", "good"]


def test_post_validate_persistent_failure_maps_to_502_not_500():
    llm = FakeLLM(['{"value": "bad"}', '{"value": "bad"}'])

    def validate(_result):
        raise ValueError("判分结果 ID 不匹配")

    with pytest.raises(UpstreamLLMError) as exc_info:
        call_json_llm(
            llm, "p", Payload, attempt_timeout=80, budget_seconds=170, post_validate=validate
        )
    assert exc_info.value.status_code == 502


def test_error_message_does_not_echo_llm_output():
    # 模型输出里混着"答案"字样：对外异常不得回显（防 ValidationError 带出 input_value）
    secret = '{"value": 123, "accept": ["绝密答案WRAPUP"]}'
    llm = FakeLLM([secret, secret])
    with pytest.raises(UpstreamLLMError) as exc_info:
        call_json_llm(llm, "p", Payload, attempt_timeout=80, budget_seconds=170)
    message = str(exc_info.value)
    assert "WRAPUP" not in message
    assert "accept" not in message
    assert message == "AI 输出结构异常，请稍后重试"


def test_empty_content_retries_then_fails_generic():
    llm = FakeLLM(["", "   "])
    with pytest.raises(UpstreamLLMError):
        call_json_llm(llm, "p", Payload, attempt_timeout=80, budget_seconds=170)
    assert llm.calls == 2


def test_extract_json_strips_code_fence():
    assert extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert extract_json('{"a": 1}') == '{"a": 1}'


# 2026-10-02 实测：教材里有 C 代码，模型把 ```c 代码块写进了参考答案，旧实现取出来的是那段 C 代码
CODE_IN_ANSWER = {"essay": [{"question": "写出事件调度的时间推进函数", "reference_answer": "```c\nvoid timing()\n{\n  min_time = 1e29;\n}\n```"}]}


def test_code_fences_inside_json_strings_are_content_not_wrappers():
    raw = json.dumps(CODE_IN_ANSWER, ensure_ascii=False)
    assert json.loads(extract_json(raw)) == CODE_IN_ANSWER


def test_an_outer_fence_with_inner_code_blocks_keeps_the_whole_json():
    raw = "```json\n" + json.dumps(CODE_IN_ANSWER, ensure_ascii=False, indent=2) + "\n```"
    assert json.loads(extract_json(raw)) == CODE_IN_ANSWER


def test_json_surrounded_by_chatter_is_found():
    raw = "好的，下面是题目：\n" + json.dumps({"a": [1, 2]}) + "\n希望有帮助。"
    assert json.loads(extract_json(raw)) == {"a": [1, 2]}


def test_connection_error_is_not_reported_as_a_structure_problem():
    """连不上上游和"上游回了但结构不对"要分开说，否则会把人引去查 prompt。"""
    from app.infra.llm_json import call_json_llm

    class Unreachable:
        def bind(self, **_kwargs):
            return self

        async def ainvoke(self, _prompt):
            raise openai.APIConnectionError(request=None)

    with pytest.raises(UpstreamLLMError) as excinfo:
        call_json_llm(
            Unreachable(),
            "prompt",
            Payload,
            attempt_timeout=1.0,
            budget_seconds=30.0,
        )

    assert "连不上模型服务" in str(excinfo.value)
    assert "结构异常" not in str(excinfo.value)


class _Status:
    """上游明确回了错误码（HTTP 4xx/5xx），不是连不上、也不是输出坏了。"""

    def __init__(self, status):
        self.status = status
        self.calls = 0

    def bind(self, **_kwargs):
        return self

    async def ainvoke(self, _prompt):
        self.calls += 1
        response = httpx.Response(self.status, request=httpx.Request("POST", "http://upstream/v1/chat/completions"))
        raise openai.APIStatusError("upstream said no", response=response, body=None)


def _call(llm):
    return call_json_llm(llm, "prompt", Payload, attempt_timeout=1.0, budget_seconds=30.0)


def test_upstream_5xx_is_reported_as_unavailable_not_as_bad_output():
    # 压测 S5：上游 500 以前被报成「AI 输出结构异常」，会把人引去查 prompt
    llm = _Status(500)
    with pytest.raises(UpstreamLLMError) as excinfo:
        _call(llm)
    assert "暂时不可用" in str(excinfo.value)
    assert "结构异常" not in str(excinfo.value)
    assert llm.calls == 2, "5xx 可能是一时的，按原来的规矩重试一次"


def test_rejected_key_fails_fast_without_retrying():
    llm = _Status(401)
    with pytest.raises(UpstreamLLMError) as excinfo:
        _call(llm)
    assert "Key" in str(excinfo.value)
    assert llm.calls == 1, "Key 不对重试也一样，别再白等一轮"


def test_upstream_rate_limit_is_named_as_such():
    with pytest.raises(UpstreamLLMError) as excinfo:
        _call(_Status(429))
    assert "限流" in str(excinfo.value)



# ---------------- 会先思考的模型：max_tokens 被思考用光 ----------------


class BoundLLM:
    """仿 client.bind(max_tokens=N)：bind 合并参数；记下每次调用时的额度。

    replies 按调用次序给 (content, finish_reason)，或一个要抛出的异常。
    """

    def __init__(self, replies, max_tokens=900, calls=None):
        self.replies = replies
        self.kwargs = {"max_tokens": max_tokens, "stop": ["END"]}
        self.calls = calls if calls is not None else []

    def bind(self, **kwargs):
        clone = BoundLLM(self.replies, calls=self.calls)
        clone.kwargs = {**self.kwargs, **kwargs}
        return clone

    async def ainvoke(self, prompt):
        self.calls.append(self.kwargs["max_tokens"])
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        content, reason = reply
        return types.SimpleNamespace(content=content, response_metadata={"finish_reason": reason})


def test_output_cut_off_by_max_tokens_retries_with_a_bigger_budget():
    # Windows 报告的情形：思考用光额度，正文为空
    llm = BoundLLM([("", "length"), ('{"value": "ok"}', "stop")])
    result = call_json_llm(llm, "p", Payload, attempt_timeout=80, budget_seconds=170)
    assert result.value == "ok"
    assert llm.calls == [900, 900 + llm_json.TRUNCATION_EXTRA_TOKENS]


def test_half_written_json_cut_off_also_gets_a_bigger_budget():
    llm = BoundLLM([('{"val', "length"), ('{"value": "ok"}', "stop")])
    assert call_json_llm(llm, "p", Payload, attempt_timeout=80, budget_seconds=170).value == "ok"
    assert llm.calls[1] > llm.calls[0]


def test_ordinary_bad_json_retries_with_the_same_budget():
    llm = BoundLLM([("not json", "stop"), ('{"value": "ok"}', "stop")])
    call_json_llm(llm, "p", Payload, attempt_timeout=80, budget_seconds=170)
    assert llm.calls == [900, 900]


def test_still_cut_off_says_so_instead_of_blaming_the_output_structure():
    llm = BoundLLM([("", "length"), ('{"val', "length")])
    with pytest.raises(UpstreamLLMError) as exc_info:
        call_json_llm(llm, "p", Payload, attempt_timeout=80, budget_seconds=170)
    assert str(exc_info.value) == llm_json.TRUNCATED_MESSAGE
    assert "关闭思考" in str(exc_info.value)


def test_cut_off_then_other_failure_is_not_reported_as_cut_off():
    llm = BoundLLM([("", "length"), ("not json", "stop")])
    with pytest.raises(UpstreamLLMError) as exc_info:
        call_json_llm(llm, "p", Payload, attempt_timeout=80, budget_seconds=170)
    assert str(exc_info.value) == "AI 输出结构异常，请稍后重试"


def test_cut_off_then_a_failed_call_is_not_reported_as_cut_off():
    llm = BoundLLM([("", "length"), RuntimeError("boom")])
    with pytest.raises(UpstreamLLMError) as exc_info:
        call_json_llm(llm, "p", Payload, attempt_timeout=80, budget_seconds=170)
    assert str(exc_info.value) == "AI 输出结构异常，请稍后重试"


def test_cut_off_with_no_budget_left_for_a_retry_still_names_the_cause():
    clock = FakeClock()

    class Slow(BoundLLM):
        async def ainvoke(self, prompt):
            clock.now += 60
            return await super().ainvoke(prompt)

    llm = Slow([("", "length")])
    with pytest.raises(UpstreamLLMError) as exc_info:
        call_json_llm(llm, "p", Payload, attempt_timeout=80, budget_seconds=100, clock=clock)
    assert str(exc_info.value) == llm_json.TRUNCATED_MESSAGE
    assert llm.calls == [900]


def test_escalation_is_capped_and_keeps_other_bound_arguments():
    llm = BoundLLM([("", "length"), ('{"value": "ok"}', "stop")], max_tokens=6000)
    call_json_llm(llm, "p", Payload, attempt_timeout=80, budget_seconds=170)
    assert llm.calls == [6000, llm_json.MAX_ESCALATED_TOKENS]
    assert llm_json._with_more_tokens(llm).kwargs["stop"] == ["END"]
    at_cap = BoundLLM([], max_tokens=llm_json.MAX_ESCALATED_TOKENS)
    assert llm_json._with_more_tokens(at_cap) is at_cap


def test_cut_off_from_an_llm_without_a_known_budget_just_retries():
    class Unbound:
        calls = 0

        async def ainvoke(self, prompt):
            Unbound.calls += 1
            if Unbound.calls == 1:
                return types.SimpleNamespace(content="", response_metadata={"finish_reason": "length"})
            return types.SimpleNamespace(content='{"value": "ok"}')

    assert call_json_llm(Unbound(), "p", Payload, attempt_timeout=80, budget_seconds=170).value == "ok"


def test_real_chat_client_reports_the_cut_off_and_sends_the_bigger_budget():
    """走真的 ChatOpenAI.bind(...)：finish_reason 要能传到 response_metadata，加的额度要真的发到上游。"""
    from langchain_openai import ChatOpenAI

    sent = []

    def handler(request):
        body = json.loads(request.content)
        # langchain 把 max_tokens 改名成 max_completion_tokens 发出去（见 llm_json 里的说明）
        sent.append(body["max_completion_tokens"])
        cut = len(sent) == 1
        return httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "created": 0,
                "model": "m",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "" if cut else '{"value": "ok"}'},
                        "finish_reason": "length" if cut else "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    client = ChatOpenAI(
        model="m",
        api_key="k",
        base_url="http://upstream.test/v1",
        max_retries=0,
        http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    ).bind(max_tokens=900)
    result = call_json_llm(client, "p", Payload, attempt_timeout=80, budget_seconds=170)
    assert result.value == "ok"
    assert sent == [900, 900 + llm_json.TRUNCATION_EXTRA_TOKENS]

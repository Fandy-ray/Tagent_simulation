"""共用积木：预算算法与带校验的模型调用。

这些原来在 exam_service / essay_service 里抄了 7 份，收进 app/agent 之后，
所有链路的超时行为都由这里决定，所以要单独钉死。
"""

from __future__ import annotations

import json
import time
import types

import pytest
from pydantic import BaseModel

from app.agent.nodes import json_call
from app.agent.runtime import ATTEMPT_MARGIN_SECONDS, AgentDeps, attempt_timeout
from app.config import UPSTREAM_STALL_SECONDS
from app.errors.exam_errors import UpstreamLLMError
from app.infra import llm_json


# ====================== 预算算法 ======================


def test_attempt_timeout_is_capped_by_the_limit():
    assert attempt_timeout(150, 30, 480) == 150


def test_attempt_timeout_leaves_a_margin_below_the_budget():
    # call_json_llm 在「剩余 < 单次超时 + 取消宽限」时一次都不试就 504，必须留余量
    assert attempt_timeout(150, 30, 100) == 100 - ATTEMPT_MARGIN_SECONDS


def test_attempt_timeout_never_drops_below_the_floor():
    assert attempt_timeout(150, 30, 20) == 30


@pytest.mark.parametrize(
    "limit,floor,budget",
    [(150, 30, 480), (90, 25, 200), (55, 20, 190), (45, 20, 70), (90, 25, 10)],
)
def test_matches_the_formula_that_was_copied_seven_times(limit, floor, budget):
    assert attempt_timeout(limit, floor, budget) == min(limit, max(floor, budget - 15.0))


def test_deps_count_down_from_start():
    deps = AgentDeps.start(knowledge_base=None, client_factory=None, provider=None, budget_seconds=60)
    assert 59 < deps.remaining() <= 60


def test_remaining_never_goes_negative():
    deps = AgentDeps(knowledge_base=None, client_factory=None, provider=None, deadline=0.0)
    assert deps.remaining() == 0.0


# ====================== json_call ======================


class Answer(BaseModel):
    value: int


class RecordingClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.bound: dict = {}
        self.prompts: list[str] = []

    def bind(self, **kwargs):
        self.bound = kwargs
        return self

    async def ainvoke(self, prompt):
        self.prompts.append(prompt)
        return types.SimpleNamespace(content=json.dumps(self.payloads.pop(0)))


class RecordingFactory:
    def __init__(self, client):
        self.client = client
        self.calls: list[dict] = []

    def get(self, provider, **kwargs):
        self.calls.append({"provider": provider, **kwargs})
        return self.client


def deps_with(client, budget=120.0):
    factory = RecordingFactory(client)
    deps = AgentDeps(
        knowledge_base=None,
        client_factory=factory,
        provider="test-provider",
        deadline=time.monotonic() + budget,
    )
    return deps, factory


def test_json_call_returns_the_validated_model():
    client = RecordingClient([{"value": 7}])
    deps, _ = deps_with(client)
    result = json_call(deps, "出题", Answer, max_tokens=500, limit=90, floor=25)
    assert result == Answer(value=7)


def test_json_call_binds_the_output_cap_and_uses_the_run_provider():
    client = RecordingClient([{"value": 1}])
    deps, factory = deps_with(client)
    json_call(deps, "出题", Answer, max_tokens=1234, limit=90, floor=25)
    assert client.bound == {"max_tokens": 1234}
    (call,) = factory.calls
    assert call["provider"] == "test-provider"
    assert call["max_retries"] == 0


@pytest.fixture
def attempt_caps(monkeypatch):
    """记下每次交给 call_json_llm 的单次总上限（invoke_with_deadline 按它硬截断）。"""
    seen = []
    real = llm_json.call_json_llm

    def recording(llm, prompt, model_cls, *, attempt_timeout, **kwargs):
        seen.append(attempt_timeout)
        return real(llm, prompt, model_cls, attempt_timeout=attempt_timeout, **kwargs)

    monkeypatch.setattr(llm_json, "call_json_llm", recording)
    return seen


def test_json_call_derives_the_attempt_cap_from_the_remaining_budget(attempt_caps):
    client = RecordingClient([{"value": 1}])
    deps, _ = deps_with(client, budget=40.0)
    json_call(deps, "出题", Answer, max_tokens=500, limit=90, floor=25)
    # 剩 40 秒：40 - 15 = 25，正好落在下限上
    assert attempt_caps == [25]


def test_the_client_read_timeout_is_the_stall_threshold_not_the_attempt_cap():
    # 一律流式读：读超时量的是两段数据之间的间隔，上游卡住时不用干等满单次上限。
    # 也不随剩余预算变，缓存里每个模型只留这一个客户端
    client = RecordingClient([{"value": 1}, {"value": 2}])
    deps, factory = deps_with(client, budget=40.0)
    json_call(deps, "出题", Answer, max_tokens=500, limit=90, floor=25)
    deps2, factory2 = deps_with(client, budget=300.0)
    json_call(deps2, "出题", Answer, max_tokens=500, limit=90, floor=25)
    assert factory.calls[0]["timeout_seconds"] == UPSTREAM_STALL_SECONDS
    assert factory2.calls[0]["timeout_seconds"] == UPSTREAM_STALL_SECONDS


def test_post_validate_runs_inside_the_retry_loop():
    # 校验放在重试圈里：第一次不合格就重来，而不是直接报错
    client = RecordingClient([{"value": -1}, {"value": 3}])
    deps, _ = deps_with(client)

    def positive(value):
        if value.value < 0:
            raise ValueError("要正数")

    result = json_call(deps, "出题", Answer, max_tokens=500, limit=90, floor=25, post_validate=positive)
    assert result.value == 3
    assert len(client.prompts) == 2


def test_a_persistently_invalid_answer_becomes_502_not_500():
    client = RecordingClient([{"value": -1}, {"value": -2}])
    deps, _ = deps_with(client)

    def positive(value):
        if value.value < 0:
            raise ValueError("要正数")

    with pytest.raises(UpstreamLLMError):
        json_call(deps, "出题", Answer, max_tokens=500, limit=90, floor=25, post_validate=positive)


def test_an_explicit_budget_overrides_the_deadline(attempt_caps):
    # 判卷把剩余预算按批次平分时会显式传 budget
    client = RecordingClient([{"value": 1}])
    deps, _ = deps_with(client, budget=480.0)
    json_call(
        deps, "判卷", Answer, max_tokens=500, limit=55, floor=20,
        budget=50.0, started=time.monotonic(),
    )
    assert attempt_caps == [35]  # 50 - 15

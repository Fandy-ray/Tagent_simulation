"""前端超时、后端预算、排队上限是一套数，改一个要一起改。

前端等不到就报「后端没响应」；它必须比后端最多会花的时间长，否则后端明明还在正常干活
（或刚排到），前端已经放弃了，学生看到的是一个假的失败。

排队的时间算在后端预算里（截止时间从进门算起），闸门最多排到截止前还留 LLM_GATE_MIN_RUN_SECONDS，
所以后端最多花一个预算的时间：前端比预算多等一点就行。留的那段要够至少调一次模型——
每次调模型前，剩余预算不到「单次超时下限 + 5 秒」就直接判超时（见 app/agent/nodes.py）。

前端常量从 tagentnote 源码里读。只有后端的仓库（gitee 的 tagent）里没有前端目录，这一条跳过。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.config import (
    ANNOTATE_LLM_BUDGET,
    ANNOTATE_MIN_ATTEMPT_TIMEOUT,
    ESSAY_LLM_BUDGET,
    ESSAY_MIN_ATTEMPT_TIMEOUT,
    ESSAY_TOPIC_LLM_BUDGET,
    ESSAY_TOPIC_MIN_ATTEMPT_TIMEOUT,
    EXAM_LLM_BUDGET,
    EXAM_MIN_ATTEMPT_TIMEOUT,
    FLASH_LLM_BUDGET,
    FLASH_MIN_ATTEMPT_TIMEOUT,
    GRADE_LLM_BUDGET,
    GRADE_MIN_ATTEMPT_TIMEOUT,
    LLM_GATE_MIN_RUN_SECONDS,
)

FRONTEND = Path(__file__).resolve().parents[3] / "tagentnote" / "src"
MARGIN_SECONDS = 10  # 网络、代理来回的余量
# call_json_llm 在剩余预算不到「单次超时 + 5 秒」时一次都不试（见 app/agent/nodes.py 的取消宽限）
CANCEL_GRACE_SECONDS = 5


def frontend_ms(relative: str, name: str) -> int:
    text = (FRONTEND / relative).read_text(encoding="utf-8")
    match = re.search(rf"{name}\s*=\s*([\d_]+)", text)
    assert match, f"{relative} 里找不到 {name}"
    return int(match.group(1).replace("_", ""))


@pytest.mark.skipif(not FRONTEND.exists(), reason="只有后端的仓库里没有前端源码")
@pytest.mark.parametrize(
    "relative, name, budget",
    [
        ("lib/components/quiz/FullExamPanel.svelte", "CLIENT_TIMEOUT_MS", EXAM_LLM_BUDGET),
        ("lib/components/quiz/FlashcardPanel.svelte", "CLIENT_TIMEOUT_MS", FLASH_LLM_BUDGET),
        ("lib/data/essay.ts", "ESSAY_CLIENT_TIMEOUT_MS", ESSAY_LLM_BUDGET),
    ],
)
def test_the_frontend_waits_longer_than_the_backend_can_take(relative, name, budget):
    waits = frontend_ms(relative, name) / 1000
    assert waits >= budget + MARGIN_SECONDS, (
        f"{relative} 的 {name} 只等 {waits:.0f} 秒，后端最多要 {budget} 秒（排队也算在里面）"
    )


@pytest.mark.parametrize(
    "budget, floor",
    [
        (EXAM_LLM_BUDGET, EXAM_MIN_ATTEMPT_TIMEOUT),
        (FLASH_LLM_BUDGET, FLASH_MIN_ATTEMPT_TIMEOUT),
        (GRADE_LLM_BUDGET, GRADE_MIN_ATTEMPT_TIMEOUT),
        (ESSAY_LLM_BUDGET, ESSAY_MIN_ATTEMPT_TIMEOUT),
        (ANNOTATE_LLM_BUDGET, ANNOTATE_MIN_ATTEMPT_TIMEOUT),
        (ESSAY_TOPIC_LLM_BUDGET, ESSAY_TOPIC_MIN_ATTEMPT_TIMEOUT),
    ],
)
def test_whoever_gets_through_the_gate_has_time_to_run(budget, floor):
    # 排到时至少还剩 LLM_GATE_MIN_RUN_SECONDS：要够调一次模型，不然排到了也是立刻超时
    assert LLM_GATE_MIN_RUN_SECONDS >= floor + CANCEL_GRACE_SECONDS
    # 预算本身比留的那段长，才谈得上排队
    assert budget > LLM_GATE_MIN_RUN_SECONDS

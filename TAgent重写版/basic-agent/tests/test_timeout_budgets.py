"""前端超时、后端预算、排队上限是一套数，改一个要一起改。

前端等不到就报「后端没响应」；它必须比「后端预算 + 排队最多等的时间」长，否则后端明明
还在正常干活（或刚排到），前端已经放弃了，学生看到的是一个假的失败。
排队上限 LLM_GATE_WAIT_SECONDS 就是从这个余量里推出来的（见 app/config.py 那段注释）。

前端常量从 tagentnote 源码里读。只有后端的仓库（gitee 的 tagent）里没有前端目录，跳过。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.config import (
    ESSAY_LLM_BUDGET,
    EXAM_LLM_BUDGET,
    FLASH_LLM_BUDGET,
    LLM_GATE_WAIT_SECONDS,
)

FRONTEND = Path(__file__).resolve().parents[3] / "tagentnote" / "src"
MARGIN_SECONDS = 10  # 网络、代理来回的余量

pytestmark = pytest.mark.skipif(not FRONTEND.exists(), reason="只有后端的仓库里没有前端源码")


def frontend_ms(relative: str, name: str) -> int:
    text = (FRONTEND / relative).read_text(encoding="utf-8")
    match = re.search(rf"{name}\s*=\s*([\d_]+)", text)
    assert match, f"{relative} 里找不到 {name}"
    return int(match.group(1).replace("_", ""))


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
    assert waits >= budget + LLM_GATE_WAIT_SECONDS + MARGIN_SECONDS, (
        f"{relative} 的 {name} 只等 {waits:.0f} 秒，后端最多要 {budget} 秒预算 + "
        f"排队 {LLM_GATE_WAIT_SECONDS:.0f} 秒"
    )

"""出卷前的考点规划。

要解决的是实测到的跨段重复：三段并发，彼此看不见对方出了什么，于是
填空问「ρ 的计算公式」、选择又问「ρ 的表达式」——同一个考点问了两遍，
而两道题的文字并不相同，事后去重做不到。
"""

from __future__ import annotations

import json
import types

import pytest
from pydantic import ValidationError

from app.schema.exam import (
    CHOICE_COUNT_RANGE,
    CLOZE_COUNT_RANGE,
    ESSAY_COUNT_RANGE,
    ExamPlan,
    split_plan,
)
from tests.test_flash_service import TEST_PROVIDER, ShardedKnowledgeBase, make_service


# ====================== 清单本身 ======================


def test_duplicate_points_are_collapsed():
    plan = ExamPlan(points=["ρ 的计算", "Little 公式", "ρ 的计算"])
    assert plan.points == ["ρ 的计算", "Little 公式"]


def test_case_and_spacing_do_not_create_duplicates():
    plan = ExamPlan(points=["Little 公式", "little  公式", "ρ"])
    assert plan.points == ["Little 公式", "ρ"]


def test_blank_points_are_dropped():
    assert ExamPlan(points=["ρ", "   ", ""]).points == ["ρ"]


def test_an_all_blank_plan_is_rejected():
    with pytest.raises(ValidationError):
        ExamPlan(points=["  ", ""])


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        ExamPlan(points=["ρ"], difficulty="hard")


# ====================== 分配 ======================


def test_groups_are_disjoint():
    points = [f"考点{i}" for i in range(12)]
    groups = split_plan(points, [5, 4, 3])
    flat = [p for group in groups for p in group]
    assert len(flat) == len(set(flat)), "同一个考点被分给了两段"


def test_each_group_respects_its_quota():
    groups = split_plan([f"考点{i}" for i in range(12)], [5, 4, 3])
    assert [len(g) for g in groups] == [5, 4, 3]


def test_important_points_are_spread_not_hoarded_by_the_first_stage():
    # 模型会把最核心的考点排在前面。按顺序切块的话第一段独占全部核心考点，
    # 后面两段只能捡边角——所以要轮流发。
    points = [f"考点{i}" for i in range(12)]
    groups = split_plan(points, [5, 4, 3])
    assert points[0] in groups[0]
    assert points[1] in groups[1]
    assert points[2] in groups[2]


def test_fewer_points_than_quota_just_gives_shorter_groups():
    groups = split_plan(["甲", "乙"], [5, 4, 3])
    assert sum(len(g) for g in groups) == 2


def test_empty_plan_yields_empty_groups():
    assert split_plan([], [5, 4, 3]) == [[], [], []]


# ====================== 接线 ======================
#
# 规划现在默认开着，但这里仍然显式打开：这些用例测的是这套机制本身，
# 不该因为有人把开关关了就悄悄变成什么都没测。


@pytest.fixture(autouse=True)
def _enable_planning(monkeypatch):
    monkeypatch.setattr("app.service.exam_service.EXAM_PLAN_POINTS", True)


class PlanningLLM:
    """先回考点清单，之后照常回题目。"""

    def __init__(self, *, plan_fails=False):
        self.prompts: list[str] = []
        self.plan_fails = plan_fails
        self.points = [f"考点{i}" for i in range(21)]

    def bind(self, **_kwargs):
        return self

    async def ainvoke(self, prompt):
        self.prompts.append(prompt)
        if "只列考点" in prompt:
            if self.plan_fails:
                raise RuntimeError("规划这一步翻车了")
            return types.SimpleNamespace(
                content=json.dumps({"points": self.points}, ensure_ascii=False)
            )
        return await _exam_body(prompt)

    def plan_prompts(self):
        return [p for p in self.prompts if "只列考点" in p]

    def stage_prompts(self):
        return [p for p in self.prompts if "只列考点" not in p]


async def _exam_body(prompt: str):
    """照着 prompt 要的题型和题量回一份合法草稿。"""
    if "**填空题**" in prompt:
        items = [
            {
                "cue": f"提示{i}",
                "text": f"第 {i} 句的空格填 ____ 即可。",
                "accept": [f"答案{i}"],
                "match_mode": "text",
                "explanation": "解析",
                "points": 3,
            }
            for i in range(CLOZE_COUNT_RANGE[1])
        ]
        payload = {"title": "排队论", "cloze": items}
    elif "**选择题**" in prompt:
        items = [
            {
                "question": f"第 {i} 题的正确项是哪个？",
                "options": [f"答案{i}", "干扰甲", "干扰乙", "干扰丙"],
                "correct_index": 0,
                "explanation": "解析",
                "points": 5,
            }
            for i in range(CHOICE_COUNT_RANGE[1])
        ]
        payload = {"choice": items}
    else:
        items = [
            {
                "question": f"论述第 {i} 题",
                "reference_answer": "参考答案",
                "rubric": "①要点一②要点二③要点三",
                "points": 10,
            }
            for i in range(ESSAY_COUNT_RANGE[1])
        ]
        payload = {"essay": items}
    return types.SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))


def test_planning_runs_once_before_the_three_stages():
    llm = PlanningLLM()
    make_service(ShardedKnowledgeBase(), llm).generate_exam("排队论", TEST_PROVIDER)
    assert len(llm.plan_prompts()) == 1, "规划该只跑一次"
    assert len(llm.stage_prompts()) == 3
    assert llm.prompts[0] == llm.plan_prompts()[0], "规划要在三段之前"


def test_each_stage_is_told_a_different_set_of_points():
    llm = PlanningLLM()
    make_service(ShardedKnowledgeBase(), llm).generate_exam("排队论", TEST_PROVIDER)

    assigned = []
    for prompt in llm.stage_prompts():
        assert "本段只在下面这些考点范围内出题" in prompt, "考点清单没进 prompt"
        assigned.append({p for p in llm.points if f"- {p}\n" in prompt})

    for i in range(len(assigned)):
        for j in range(i + 1, len(assigned)):
            assert not (assigned[i] & assigned[j]), (
                f"第 {i} 段和第 {j} 段分到了同一个考点：{assigned[i] & assigned[j]}"
            )
    assert all(assigned), "有段落一个考点都没分到"


def test_a_failed_plan_still_produces_an_exam():
    # 规划只是锦上添花。拿不到清单时三段按老样子各自出题，
    # 顶多回到「偶尔撞考点」，总好过给用户一个 502
    llm = PlanningLLM(plan_fails=True)
    exam = make_service(ShardedKnowledgeBase(), llm).generate_exam("排队论", TEST_PROVIDER)
    assert len(exam.cloze) >= CLOZE_COUNT_RANGE[0]
    assert len(exam.choice) >= CHOICE_COUNT_RANGE[0]
    assert len(exam.essay) >= ESSAY_COUNT_RANGE[0]
    for prompt in llm.stage_prompts():
        assert "本段只在下面这些考点范围内出题" not in prompt


def test_planning_asks_for_as_many_points_as_the_exam_has_questions():
    llm = PlanningLLM()
    make_service(ShardedKnowledgeBase(), llm).generate_exam("排队论", TEST_PROVIDER)
    total = CLOZE_COUNT_RANGE[1] + CHOICE_COUNT_RANGE[1] + ESSAY_COUNT_RANGE[1]
    assert f"**最多** {total} 个考点" in llm.plan_prompts()[0]


def test_a_stage_with_too_few_points_is_left_unconstrained():
    """规划常常只返回十几个考点（它被要求「宁可少给」）。

    分到填空段不够出 8 道时，硬按清单出会出到刚好下限，再被违规过滤
    删掉一两道就跌破下限 → 整段重试 → 502（实测过）。这时干脆不给清单。
    """
    llm = PlanningLLM()
    llm.points = [f"考点{i}" for i in range(9)]  # 少得分不出三段的量
    make_service(ShardedKnowledgeBase(), llm).generate_exam("排队论", TEST_PROVIDER)

    cloze_prompt = next(p for p in llm.stage_prompts() if "**填空题**" in p)
    assert "本段只在下面这些考点范围内出题" not in cloze_prompt, (
        "考点不够时不该还把填空段框死"
    )


def test_a_stage_with_enough_points_is_still_constrained():
    llm = PlanningLLM()
    make_service(ShardedKnowledgeBase(), llm).generate_exam("排队论", TEST_PROVIDER)
    cloze_prompt = next(p for p in llm.stage_prompts() if "**填空题**" in p)
    assert "本段只在下面这些考点范围内出题" in cloze_prompt

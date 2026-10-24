"""整卷出题的分路：七路同时起步、各管一块，组卷时去重并保证题数。

为什么这么分见 app/agent/graphs/exam.py 开头；这里钉住的是那几条取舍本身，
谁改回「先定考点」「大题一路三道」「填空选择拿论文片段」，这里会红。
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import types

import pytest

from app.errors.exam_errors import InvalidExamRequestError, UpstreamLLMError
from app.prompts.exam_prompts import _LANE_NOTES, LANE_CORE, LANE_OTHER
from app.schema.exam import CHOICE_COUNT_RANGE, CLOZE_COUNT_RANGE, ESSAY_COUNT_RANGE, ESSAY_GROUPS
from tests.test_flash_service import (
    TEST_PROVIDER,
    EmptyKnowledgeBase,
    ShardedKnowledgeBase,
    make_service,
)


def kind_of(prompt: str) -> str:
    if "**填空题**" in prompt:
        return "cloze"
    if "**选择题**" in prompt:
        return "choice"
    return "essay"


def material_of(prompt: str) -> set[str]:
    """这一路拿到了哪几段材料（ShardedKnowledgeBase 的片段以「材料N 」开头）。"""
    return set(re.findall(r"材料\d+ ", prompt))


class ExamLLM:
    """照着提示词要的题型和题量回一份合法草稿；每一路的题目互不相同。"""

    def __init__(self, *, slow: dict | None = None, failing_essay: str | None = None, same_cloze=False):
        self.prompts: list[str] = []
        self.events: list[tuple[str, str, float]] = []
        self.slow = slow or {}
        self.failing_essay = failing_essay  # 这一类的大题每次都回坏 JSON
        self.same_cloze = same_cloze  # 各路填空回一模一样的题（测跨路去重）

    def bind(self, **_kwargs):
        return self

    async def ainvoke(self, prompt):
        kind = kind_of(prompt)
        self.prompts.append(prompt)
        self.events.append((kind, "start", time.monotonic()))
        await asyncio.sleep(self.slow.get(kind, 0))
        self.events.append((kind, "end", time.monotonic()))
        tag = "同" if self.same_cloze and kind == "cloze" else f"{len(self.prompts)}"
        if kind == "cloze":
            hi = int(re.search(r"填空题 \d+~(\d+) 道", prompt).group(1))
            items = [
                {"text": f"第 {tag}-{i} 句的空格填 ____ 即可。", "accept": [f"答案{tag}-{i}"],
                 "match_mode": "text", "explanation": "解析", "points": 3}
                for i in range(hi)
            ]
            payload = {"title": "排队论", "cloze": items}
        elif kind == "choice":
            hi = int(re.search(r"选择题 \d+~(\d+) 道", prompt).group(1))
            items = [
                {"question": f"第 {tag}-{i} 题选哪个？", "options": [f"选项{tag}-{i}", "乙", "丙", "丁"],
                 "correct_index": 0, "explanation": "解析", "points": 5}
                for i in range(hi)
            ]
            payload = {"choice": items}
        else:
            if self.failing_essay and self.failing_essay in prompt:
                return types.SimpleNamespace(content="不是 JSON")
            payload = {"essay": [{"question": f"论述第 {tag} 题", "reference_answer": "参考答案",
                                  "rubric": "①要点一②要点二③要点三", "points": 15}]}
        return types.SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))

    def of(self, kind):
        return [p for p in self.prompts if kind_of(p) == kind]


def generate(llm, kb=None):
    return make_service(kb or ShardedKnowledgeBase(), llm).generate_exam("排队论", TEST_PROVIDER)


# ====================== 七路同时起步 ======================


def test_every_call_starts_before_any_finishes():
    # 谁也不等谁：没有「先定考点」挡在前面，七路同时发出去
    llm = ExamLLM(slow={"cloze": 0.2, "choice": 0.2, "essay": 0.2})
    generate(llm)
    starts = [t for _, edge, t in llm.events if edge == "start"]
    ends = [t for _, edge, t in llm.events if edge == "end"]
    assert len(starts) == 7
    assert max(starts) < min(ends), "有一路等别的路写完才开始"


def test_the_exam_takes_as_long_as_the_slowest_call_not_the_sum():
    llm = ExamLLM(slow={"cloze": 0.3, "choice": 0.3, "essay": 0.3})
    started = time.perf_counter()
    exam = generate(llm)
    assert time.perf_counter() - started < 0.8
    assert len(exam.cloze) >= CLOZE_COUNT_RANGE[0] and len(exam.choice) >= CHOICE_COUNT_RANGE[0]


# ====================== 大题：三路各一道 ======================


def test_three_essay_calls_each_ask_for_one_question_of_their_own_kind():
    llm = ExamLLM()
    exam = generate(llm)
    prompts = llm.of("essay")
    assert len(prompts) == len(ESSAY_GROUPS) == 3
    assert all("1 道「" in p for p in prompts)
    firsts = sorted(p.splitlines()[0] for p in prompts)
    assert len(set(firsts)) == 3, "三路大题要的是同一类"
    assert len(exam.essay) == ESSAY_COUNT_RANGE[1]


def test_non_calculation_essays_are_told_not_to_be_calculations():
    # 只在规则末尾写类型时，「建模」那一路 6 次全出成了计算题（2026-10-24 实测）
    llm = ExamLLM()
    generate(llm)
    for prompt in llm.of("essay"):
        forbids = "不能**是「给定参数、求各项指标」的计算题" in prompt
        assert forbids == ("「计算类」" not in prompt.splitlines()[0])


def test_one_failed_essay_call_still_yields_an_exam():
    # 三路大题少一路，剩下两道仍够一张卷，别为它让整卷失败
    llm = ExamLLM(failing_essay="「建模/设计类」")
    exam = generate(llm)
    assert len(exam.essay) == 2 == ESSAY_COUNT_RANGE[0]


def test_too_few_essays_is_an_upstream_error():
    class TwoFailing(ExamLLM):
        async def ainvoke(self, prompt):
            if kind_of(prompt) == "essay" and "「计算类」" not in prompt:
                self.prompts.append(prompt)
                return types.SimpleNamespace(content="不是 JSON")
            return await super().ainvoke(prompt)

    with pytest.raises(UpstreamLLMError):
        generate(TwoFailing())


# ====================== 填空、选择：分材料、分路 ======================


def test_cloze_and_choice_calls_each_get_different_material():
    llm = ExamLLM()
    generate(llm, ShardedKnowledgeBase(pieces=8))
    objective = llm.of("cloze") + llm.of("choice")
    assert len(objective) == 4
    materials = [material_of(p) for p in objective]
    assert all(materials)
    assert all(a.isdisjoint(b) for i, a in enumerate(materials) for b in materials[i + 1 :])


def test_only_the_first_cloze_call_owns_the_core_concepts():
    # 核心概念每片材料里都有，不点名就每一路都挑它们出
    llm = ExamLLM()
    generate(llm)
    objective = llm.of("cloze") + llm.of("choice")
    core = [p for p in objective if _LANE_NOTES[LANE_CORE].strip() in p]
    others = [p for p in objective if _LANE_NOTES[LANE_OTHER].strip() in p]
    assert len(core) == 1 and kind_of(core[0]) == "cloze"
    assert len(others) == 3


def test_papers_only_go_to_the_essays():
    # 材料切得小，分到论文片段的那一路只能从论文里挑，出来的是论文独有的细节
    kb = ShardedKnowledgeBase(pieces=8)
    kb.sources = ["textbook", "reference"] * 4
    llm = ExamLLM()
    generate(llm, kb)
    papers = {f"材料{i} " for i in range(1, 8, 2)}
    for prompt in llm.of("cloze") + llm.of("choice"):
        assert not (material_of(prompt) & papers), "填空、选择拿到了论文片段"
    for prompt in llm.of("essay"):
        assert papers <= material_of(prompt), "大题要拿全部材料"


def test_with_only_papers_the_objective_calls_still_get_material():
    kb = ShardedKnowledgeBase(pieces=4)
    kb.sources = ["reference"] * 4
    llm = ExamLLM()
    generate(llm, kb)
    assert all(material_of(p) for p in llm.of("cloze") + llm.of("choice"))


def test_cross_call_duplicates_are_removed_but_the_exam_keeps_its_counts():
    # 两路填空回了一模一样的题：去重后跌破下限，就把近似题补回来，好过整卷 502
    llm = ExamLLM(same_cloze=True)
    exam = generate(llm)
    texts = [q.text for q in exam.cloze]
    per_call = int(re.search(r"填空题 \d+~(\d+) 道", llm.of("cloze")[0]).group(1))
    assert len(set(texts)) == per_call, "两路一模一样的题没被去重"
    assert len(texts) == CLOZE_COUNT_RANGE[0], "去重后没把题数补回下限"


def test_counts_land_inside_the_ranges():
    exam = generate(ExamLLM())
    assert CLOZE_COUNT_RANGE[0] <= len(exam.cloze) <= CLOZE_COUNT_RANGE[1]
    assert CHOICE_COUNT_RANGE[0] <= len(exam.choice) <= CHOICE_COUNT_RANGE[1]
    assert ESSAY_COUNT_RANGE[0] <= len(exam.essay) <= ESSAY_COUNT_RANGE[1]


def test_empty_material_is_a_request_error_before_any_model_call():
    # 和闪卡一致：选了个空笔记本就当场 422，不去白调七路模型
    llm = ExamLLM()
    with pytest.raises(InvalidExamRequestError):
        generate(llm, EmptyKnowledgeBase())
    assert llm.prompts == []


def test_cloze_drafts_no_longer_ask_for_a_cue():
    # cue 以前是题干的原样复述；改成考点名后常常就是答案，被判泄题删掉
    llm = ExamLLM()
    generate(llm)
    assert all('"cue"' not in p for p in llm.of("cloze"))

"""出题质量过滤：指代材料、答案泄漏。

用例大多直接取自实测出来的坏题（填「排队论」出的那张卷子、那组闪卡）。
"""

from __future__ import annotations

import pytest

from app.schema.exam import DraftChoiceQuestion, DraftClozeQuestion, DraftEssayQuestion
from app.schema.exam_quality import clean_questions, drop_violating, violations


def cloze(cue="提示", text="句子 ____ 结束。", accept=("答案甲",)):
    return DraftClozeQuestion(cue=cue, text=text, accept=list(accept), points=3)


def choice(question="问题？", options=("甲", "乙", "丙", "丁"), correct_index=0):
    return DraftChoiceQuestion(
        question=question, options=list(options), correct_index=correct_index, points=5
    )


def essay(question="请论述排队论的应用。"):
    return DraftEssayQuestion(
        question=question, reference_answer="参考答案", rubric="评分要点", points=18
    )


# ====================== 指代材料 ======================


@pytest.mark.parametrize(
    "stem",
    [
        "根据材料，主路常数 m 的取值为多少？",
        "材料中提到的改善率约为多少？",
        "如图 4.9 所示，楼梯宽度应取多少？",
        "见表 2，排班人数是多少？",
        "图 3.1 中的曲线说明了什么？",
        "表 5-2 所示的数据反映了什么？",
        "根据上文的推导，结论是什么？",
        "文献[12] 的作者提出了什么方法？",
    ],
)
def test_flags_questions_that_point_at_unseen_material(stem):
    assert any("看不到的材料" in reason for reason in violations(choice(question=stem)))


@pytest.mark.parametrize(
    "stem",
    [
        "M/M/1 模型中服务强度的定义是什么？",
        "绘制系统流程图的第一步是什么？",
        "下列关于列表调度的说法，哪个正确？",
        "事件调度法与进程交互法的区别是什么？",
    ],
)
def test_does_not_flag_legitimate_questions(stem):
    # 「流程图」「列表」里带图/表字，不该被误伤
    assert violations(choice(question=stem)) == []


def test_flags_material_reference_in_a_cloze_body():
    bad = cloze(text="根据材料，服务强度记作 ____。", accept=["ρ"])
    assert any("看不到的材料" in r for r in violations(bad))


def test_flags_material_reference_in_an_essay():
    assert any("看不到的材料" in r for r in violations(essay("请结合上文分析该模型。")))


def test_flags_material_reference_hidden_in_an_option():
    # 题干干净但选项里露馅，一样做不了
    bad = choice(question="下列说法正确的是？", options=("如图 2 所示的情形", "乙", "丙", "丁"))
    assert any("看不到的材料" in r for r in violations(bad))


# ====================== 答案泄漏 ======================


def test_flags_a_cloze_whose_stem_contains_its_own_answer():
    # 实测的 F1：题干里直接写了「排队系统」，答案也是它
    bad = cloze(
        cue="排队系统的组成",
        text="排队系统由到达过程、服务过程和 ____ 三部分组成。",
        accept=["排队系统"],
    )
    assert any("答案写在题干里" in r for r in violations(bad))


def test_flags_leak_through_any_accepted_spelling():
    # accept 是等价写法的穷举，任何一条露在题干里都算
    bad = cloze(text="泊松分布描述的是 ____ 过程。", accept=["到达", "泊松分布"])
    assert any("答案写在题干里" in r for r in violations(bad))


def test_ignores_whitespace_when_detecting_a_leak():
    bad = cloze(text="排 队 系统由三部分组成，其中之一是 ____。", accept=["排队系统"])
    assert any("答案写在题干里" in r for r in violations(bad))


def test_single_character_answers_are_not_treated_as_leaks():
    # ρ、λ 这种单字符在题干里正常出现太常见，按泄漏判会大面积误伤
    ok = cloze(text="服务强度 ρ 的计算式是 ____。", accept=["ρ"])
    assert violations(ok) == []


def test_flags_a_choice_whose_stem_contains_the_correct_option():
    bad = choice(
        question="先进先出（FIFO）的中文全称是什么？",
        options=("先进先出", "后进先出", "随机服务", "优先级服务"),
        correct_index=0,
    )
    assert any("答案写在题干里" in r for r in violations(bad))


def test_a_distractor_appearing_in_the_stem_is_not_a_leak():
    # 只有**正确**选项出现在题干才算泄漏，干扰项不算
    ok = choice(
        question="与后进先出相对的排队规则是什么？",
        options=("先进先出", "后进先出", "随机服务", "优先级服务"),
        correct_index=0,
    )
    assert violations(ok) == []


def test_options_themselves_do_not_count_as_leaking():
    # 正确选项当然会出现在选项列表里，那不是泄漏
    assert violations(choice(question="服务强度是什么？")) == []


def test_blank_placeholder_is_not_mistaken_for_content():
    ok = cloze(text="____ 是排队论的核心指标。", accept=["平均等待时间"])
    assert violations(ok) == []


# ====================== 分堆 ======================


def test_drop_violating_splits_and_explains():
    good = cloze(text="服务强度的计算式是 ____。", accept=["λ/μ"])
    bad = choice(question="根据材料，m 为多少？")
    kept, dropped = drop_violating([good, bad, good])

    assert len(kept) == 2
    assert len(dropped) == 1
    question, reasons = dropped[0]
    assert question is bad
    assert reasons and all(isinstance(r, str) for r in reasons)


def test_a_question_can_break_more_than_one_rule():
    bad = cloze(
        text="根据材料，排队系统由到达、服务和 ____ 组成。", accept=["排队系统"]
    )
    assert len(violations(bad)) == 2


def test_drop_violating_handles_an_empty_batch():
    assert drop_violating([]) == ([], [])


def test_all_clean_keeps_everything():
    batch = [cloze(), choice(), essay()]
    kept, dropped = drop_violating(batch)
    assert len(kept) == 3 and dropped == []


# ====================== 出题余量 ======================
#
# 没有余量时，模型多给一道就整段重试；而出完题还要过违规过滤，
# 删掉两三道就跌破下限 → 重试 → 还不够 → 502（接考点规划时实测到过）。


def test_a_stage_draft_accepts_a_few_extra_questions():
    from app.schema.exam import CLOZE_COUNT_RANGE, DRAFT_OVERSHOOT, ClozeExamDraft

    extra = CLOZE_COUNT_RANGE[1] + DRAFT_OVERSHOOT
    ClozeExamDraft(cloze=[cloze(text=f"第 {i} 句填 ____ 即可。") for i in range(extra)])


def test_a_stage_draft_still_rejects_an_absurd_count():
    from pydantic import ValidationError

    from app.schema.exam import CLOZE_COUNT_RANGE, DRAFT_OVERSHOOT, ClozeExamDraft

    too_many = CLOZE_COUNT_RANGE[1] + DRAFT_OVERSHOOT + 1
    with pytest.raises(ValidationError):
        ClozeExamDraft(cloze=[cloze(text=f"第 {i} 句填 ____ 即可。") for i in range(too_many)])


def test_the_final_exam_is_still_strictly_within_range():
    # 放宽的只是中间产物；组好的卷子必须仍然落在 COUNT_RANGE 内
    from pydantic import ValidationError

    from app.schema.exam import (
        CHOICE_COUNT_RANGE,
        CLOZE_COUNT_RANGE,
        ESSAY_COUNT_RANGE,
        GeneratedExamDraft,
    )

    with pytest.raises(ValidationError):
        GeneratedExamDraft(
            title="t",
            cloze=[cloze(text=f"第 {i} 句填 ____ 即可。") for i in range(CLOZE_COUNT_RANGE[1] + 1)],
            choice=[choice(question=f"第 {i} 题？") for i in range(CHOICE_COUNT_RANGE[0])],
            essay=[essay() for _ in range(ESSAY_COUNT_RANGE[0])],
        )


def test_extra_questions_are_trimmed_not_rejected():
    batch = [cloze(text=f"第 {i} 句填 ____ 即可。") for i in range(13)]
    assert len(clean_questions(batch, "填空", 10)) == 10


def test_trimming_happens_after_dropping_not_before():
    # 先裁后删的话，裁掉的名额会被违规题白白占掉
    batch = [cloze(text=f"第 {i} 句填 ____ 即可。") for i in range(10)]
    batch += [choice(question="根据材料，下列哪项正确？") for _ in range(3)]
    assert len(clean_questions(batch, "混合", 10)) == 10


# ====================== 泄漏判定的误伤 ======================
#
# 下面两条都是实测抓到的误判：过滤器把合格的题删了，删到题数不够下限，
# 整段重试、最后 502。误删好题比漏判一道坏题代价大得多。


def test_latex_commands_are_not_treated_as_leaked_text():
    # 题干里的 $1/\mu$ 让答案「mu」命中了——那是 LaTeX 命令名，
    # 不是题干在把答案告诉学生
    ok = cloze(
        text=r"若服务时间服从均值为 $1/\mu$ 的指数分布，则服务率可表示为____。",
        accept=[r"$\mu$", "mu", "μ"],
    )
    assert violations(ok) == []


def test_a_word_appearing_in_the_premise_is_not_a_leak():
    # 「增大」出现在前提从句（到达率增大）里，不是答案泄漏；
    # 两字中文词几乎都栽在这上面
    ok = cloze(
        text="在M/M/1排队系统中，若服务率 μ 不变而到达率 λ 增大，则平均等待时间会____。",
        accept=["增大", "增加", "变大", "上升"],
    )
    assert violations(ok) == []


def test_a_real_leak_is_still_caught_after_loosening():
    # 放宽之后真泄漏不能漏判——F1 那种「答案就是题干里的词」照样要删
    bad = cloze(
        cue="排队系统的组成",
        text="排队系统由到达过程、服务过程和 ____ 三部分组成。",
        accept=["排队系统"],
    )
    assert any("答案写在题干里" in r for r in violations(bad))


def test_a_formula_spelled_out_in_the_stem_is_still_a_leak():
    # 真正的公式泄漏都远长于符号门槛，照样抓得住
    bad = cloze(
        text=r"已知 $L=\frac{\rho}{1-\rho}$。则平均队长的表达式为____。",
        accept=[r"\frac{\rho}{1-\rho}"],
    )
    assert any("答案写在题干里" in r for r in violations(bad))


def test_short_acronyms_in_the_stem_are_a_known_blind_spot():
    """已知缺口，而且是**有意**留的。

    符号类答案的门槛是 6 个字符，为的是别被题干里正常出现的 $\mu$、mu 误伤
    （实测那类误伤会把题数删到跌破下限、整段重试、最后 502）。
    代价就是 FIFO 这种四字符缩写被写进题干时漏判。

    两害相权：漏判一道坏题，学生顶多白得一分；误删好题会让整次出卷失败。
    """
    missed = choice(
        question="先进先出（FIFO）的英文缩写是什么？",
        options=("FIFO", "LIFO", "SIRO", "PRI"),
        correct_index=0,
    )
    assert violations(missed) == []

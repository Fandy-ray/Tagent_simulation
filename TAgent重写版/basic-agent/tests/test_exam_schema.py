"""app.schema.exam 纯逻辑单测：归一化、匹配、脱敏、判分模型。不依赖 LLM。"""

import json

import pytest
from pydantic import ValidationError

from app.schema.exam import (
    CHOICE_COUNT_RANGE,
    CLOZE_COUNT_RANGE,
    ESSAY_COUNT_RANGE,
    DraftChoiceQuestion,
    DraftClozeQuestion,
    DraftEssayQuestion,
    ExamReview,
    GeneratedExamDraft,
    LLMGradeBatch,
    LLMGradeItem,
    QuestionResult,
    SectionScore,
    TOTAL_POINTS,
    TYPE_SHARE_BOUNDS,
    _largest_remainder,
    _project_type_totals,
    cloze_matches,
    normalize_draft,
    ratio_to_score,
    to_public,
    validate_grade_batch,
    verdict_from_score,
)


def make_draft(
    n_cloze=CLOZE_COUNT_RANGE[0],
    n_choice=CHOICE_COUNT_RANGE[0],
    n_essay=ESSAY_COUNT_RANGE[0],
    cloze_pts=3.0,
    choice_pts=5.0,
    essay_pts=18.0,
):
    return GeneratedExamDraft(
        title="测试卷",
        cloze=[
            DraftClozeQuestion(
                cue=f"提示{i}", text=f"句子 {i} 中的 ____ 是答案",
                accept=[f"答案{i}"], points=cloze_pts,
            )
            for i in range(n_cloze)
        ],
        choice=[
            DraftChoiceQuestion(
                question=f"选择题{i}", options=["甲", "乙", "丙", "丁"],
                correct_index=i % 4, explanation="解析", points=choice_pts,
            )
            for i in range(n_choice)
        ],
        essay=[
            DraftEssayQuestion(
                question=f"大题{i}", reference_answer="参考答案", rubric="要点",
                points=essay_pts,
            )
            for i in range(n_essay)
        ],
    )


# ====================== 归一化 ======================
def test_normalize_total_is_100_and_each_at_least_1():
    exam = normalize_draft(make_draft(), "eid")
    all_q = exam.all_questions()
    assert sum(q.points for q in all_q) == TOTAL_POINTS
    assert all(q.points >= 1 for q in all_q)
    assert [q.id for q in exam.cloze] == [f"C{i + 1}" for i in range(CLOZE_COUNT_RANGE[0])]
    assert [q.id for q in exam.choice] == [f"M{i + 1}" for i in range(CHOICE_COUNT_RANGE[0])]
    assert [q.id for q in exam.essay] == [f"E{i + 1}" for i in range(ESSAY_COUNT_RANGE[0])]


def test_normalize_holds_at_max_counts():
    """题量取上界时每题仍分得 >=1 分——题量/分值区间是否相容的回归防线。"""
    exam = normalize_draft(
        make_draft(
            n_cloze=CLOZE_COUNT_RANGE[1],
            n_choice=CHOICE_COUNT_RANGE[1],
            n_essay=ESSAY_COUNT_RANGE[1],
        ),
        "eid",
    )
    assert sum(q.points for q in exam.all_questions()) == TOTAL_POINTS
    assert all(q.points >= 1 for q in exam.all_questions())


def test_bounds_stay_consistent():
    from app.schema.exam import _assert_bounds_consistent

    _assert_bounds_consistent()  # 调参把区间改到无解时，这里先炸


def test_normalize_projects_skewed_type_totals_into_bounds():
    # 填空分值极端偏大：必须被投影回 [20,35]
    exam = normalize_draft(make_draft(cloze_pts=100.0, choice_pts=1.0, essay_pts=1.0), "eid")
    for key, items in (("cloze", exam.cloze), ("choice", exam.choice), ("essay", exam.essay)):
        lo, hi = TYPE_SHARE_BOUNDS[key]
        assert lo <= sum(q.points for q in items) <= hi
    assert sum(q.points for q in exam.all_questions()) == TOTAL_POINTS


def test_project_type_totals_zero_weights():
    totals = _project_type_totals({"cloze": 0.0, "choice": 0.0, "essay": 0.0})
    assert sum(totals.values()) == TOTAL_POINTS
    for key, value in totals.items():
        lo, hi = TYPE_SHARE_BOUNDS[key]
        assert lo <= value <= hi


def test_largest_remainder_exact_sum_and_min_one():
    result = _largest_remainder([0.01, 0.01, 100.0, 100.0], 20)
    assert sum(result) == 20
    assert all(p >= 1 for p in result)
    result2 = _largest_remainder([1.0] * 6, 35)
    assert sum(result2) == 35


def test_largest_remainder_rejects_insufficient_total():
    with pytest.raises(ValueError):
        _largest_remainder([1.0, 1.0, 1.0], 2)


# ====================== 草稿结构校验 ======================
def test_draft_rejects_bad_counts():
    with pytest.raises(ValidationError):
        make_draft(n_cloze=CLOZE_COUNT_RANGE[0] - 1)
    with pytest.raises(ValidationError):
        make_draft(n_cloze=CLOZE_COUNT_RANGE[1] + 1)
    with pytest.raises(ValidationError):
        make_draft(n_essay=ESSAY_COUNT_RANGE[1] + 1)
    with pytest.raises(ValidationError):
        make_draft(n_choice=CHOICE_COUNT_RANGE[0] - 1)


def test_cloze_requires_exactly_one_blank():
    with pytest.raises(ValidationError):
        DraftClozeQuestion(cue="c", text="没有空", accept=["a"], points=1)
    with pytest.raises(ValidationError):
        DraftClozeQuestion(cue="c", text="两个 ____ 空 ____", accept=["a"], points=1)


def test_choice_requires_four_options_and_valid_index():
    with pytest.raises(ValidationError):
        DraftChoiceQuestion(question="q", options=["a", "b", "c"], correct_index=0, points=1)
    with pytest.raises(ValidationError):
        DraftChoiceQuestion(question="q", options=["a", "b", "c", "d"], correct_index=4, points=1)


# ====================== 公开卷脱敏（递归断言） ======================
SENSITIVE_KEYS = {"accept", "correct_index", "reference_answer", "rubric", "explanation"}


def walk_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from walk_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_keys(item)


def test_public_exam_has_no_sensitive_fields_recursively():
    exam = normalize_draft(make_draft(), "eid")
    public = to_public(exam)
    tree = json.loads(public.model_dump_json())
    leaked = SENSITIVE_KEYS & set(walk_keys(tree))
    assert not leaked, f"公开卷泄露字段：{leaked}"
    # 数量与分值保留
    assert (
        len(tree["cloze"]) == CLOZE_COUNT_RANGE[0]
        and len(tree["choice"]) == CHOICE_COUNT_RANGE[0]
        and len(tree["essay"]) == ESSAY_COUNT_RANGE[0]
    )
    assert tree["total_points"] == TOTAL_POINTS


# ====================== 填空匹配 ======================
def test_cloze_text_mode_is_lenient():
    assert cloze_matches(" 排队延迟。 ", ["排队延迟"], "text")
    assert cloze_matches("QUEUING", ["queuing"], "text")
    assert cloze_matches("ｑｕｅｕｉｎｇ", ["queuing"], "text")  # 全角
    assert not cloze_matches("传播延迟", ["排队延迟"], "text")
    assert not cloze_matches("", ["排队延迟"], "text")


def test_cloze_exact_mode_preserves_case():
    assert cloze_matches("mW", ["mW"], "exact")
    assert not cloze_matches("MW", ["mW"], "exact")
    assert cloze_matches(" mW ", ["mW"], "exact")  # 首尾空白仍可清理


def test_only_text_mode_goes_to_llm_recheck():
    from app.schema.exam import needs_llm_recheck

    # exact 未匹配必须直接判错，送 LLM 会让 mW/MW 被语义"翻案"
    assert needs_llm_recheck("text")
    assert not needs_llm_recheck("exact")


def test_grade_cloze_locally_routes_like_review_exam():
    # review_exam 的填空分流直接调用本函数：这里测的就是线上路径
    from app.schema.exam import ClozeQuestion, grade_cloze_locally

    exact_q = ClozeQuestion(
        id="C1", cue="功率单位", text="信号功率约为 1 ____",
        accept=["mW"], match_mode="exact", points=5,
    )
    text_q = ClozeQuestion(
        id="C2", cue="延迟类型", text="____ 是分组在缓冲区等待造成的",
        accept=["排队延迟"], match_mode="text", points=5,
    )

    # 未作答 → 本地记 0，不送 LLM
    r = grade_cloze_locally(exact_q, "")
    assert r is not None and r.verdict == "unanswered" and r.score == 0

    # 匹配（首尾空白可清理）→ 满分
    r = grade_cloze_locally(exact_q, " mW ")
    assert r is not None and r.verdict == "correct" and r.score == 5

    # exact 未匹配 → 直接判错（返回结果而非 None），绝不进入 LLM 复核
    r = grade_cloze_locally(exact_q, "MW")
    assert r is not None and r.verdict == "wrong" and r.score == 0
    assert "精确作答" in r.feedback

    # text 未匹配 → None，交 LLM 语义复核
    assert grade_cloze_locally(text_q, "传播延迟") is None
    # text 宽松匹配（标点/空白）仍在本地完成
    r = grade_cloze_locally(text_q, " 排队延迟。")
    assert r is not None and r.verdict == "correct"


# ====================== 旧版单题接口输出解析 ======================
def test_parse_legacy_question_contract():
    from app.schema.exam import parse_legacy_question

    # 正常 JSON（多余字段忽略）
    ok = parse_legacy_question('{"title": "测验", "question": "什么是仿真？", "extra": 1}')
    assert ok == {"title": "测验", "question": "什么是仿真？"}
    # 纯文本 → 整段当题目（格式兜底）
    fallback = parse_legacy_question("什么是离散事件仿真？")
    assert fallback["question"] == "什么是离散事件仿真？"
    # 合法 JSON 但不是对象 / 字段缺失或空白 → None（上游 502，绝不 500）
    assert parse_legacy_question("[]") is None
    assert parse_legacy_question("null") is None
    assert parse_legacy_question('{"title": "x"}') is None
    assert parse_legacy_question('{"question": "   "}') is None
    assert parse_legacy_question("") is None


def test_parse_legacy_review_contract():
    from app.schema.exam import parse_legacy_review

    # "90"/"false" 这类可安全转换的类型必须被救回为正确契约类型
    ok = parse_legacy_review('{"is_correct": "false", "score": "90", "comment": "好", "correct_answer": "答案"}')
    assert ok == {"is_correct": False, "score": 90, "comment": "好", "correct_answer": "答案"}
    # 分数越界 → clamp 而非报错
    full = '{{"is_correct": true, "score": {score}, "comment": "", "correct_answer": ""}}'
    assert parse_legacy_review(full.format(score=150))["score"] == 100
    assert parse_legacy_review(full.format(score=-3))["score"] == 0
    # 纯文本是上游协议失败，必须走 502，不能伪装成一次合法的 0 分判题
    assert parse_legacy_review("回答不完整") is None
    # 四个契约字段全部必填：{}/缺字段不得变成"错误、0 分"的 200
    assert parse_legacy_review("{}") is None
    assert parse_legacy_review('{"unexpected": 1}') is None
    assert parse_legacy_review('{"is_correct": true, "score": 90}') is None
    # 布尔分数会被 float(True) 悄悄变 1 分，必须拒绝
    assert parse_legacy_review(full.format(score="true")) is None
    # []/null/NaN 类结构 → None（上游 502，绝不 AttributeError 落 500）
    assert parse_legacy_review("[]") is None
    assert parse_legacy_review("null") is None
    assert parse_legacy_review(full.format(score='"abc"')) is None
    assert parse_legacy_review(full.format(score='"Infinity"')) is None


# ====================== 判分模型 ======================
def test_grade_item_rejects_nan_and_infinity():
    with pytest.raises(ValidationError):
        LLMGradeItem(question_id="E1", score_ratio=float("nan"))
    with pytest.raises(ValidationError):
        LLMGradeItem(question_id="E1", score_ratio=float("inf"))


def test_grade_item_clamps_ratio():
    assert LLMGradeItem(question_id="E1", score_ratio=1.5).score_ratio == 1.0
    assert LLMGradeItem(question_id="E1", score_ratio=-0.2).score_ratio == 0.0


def test_grade_output_tolerates_extra_keys_the_model_adds():
    # 实测 DeepSeek 常在每条里多写这些；严格校验时一张卷约一半判卷 502
    raw = json.dumps({
        "items": [
            {"question_id": "E1", "question_id_note": "", "score_ratio": 0.7,
             "score_ratio_note": "2/3≈0.7", "feedback": "缺第三条要点"},
        ],
        "overall_comment": "", "summary": "多余的顶层字段",
    }, ensure_ascii=False)
    batch = LLMGradeBatch.model_validate_json(raw)
    (item,) = batch.items
    assert (item.question_id, item.score_ratio, item.feedback) == ("E1", 0.7, "缺第三条要点")
    validate_grade_batch(batch, {"E1"})


def test_grade_output_is_still_strict_where_it_matters():
    # 放宽的只是「多写的字段」：题号缺了、分数不是数，照样不合格
    with pytest.raises(ValidationError):
        LLMGradeBatch.model_validate_json('{"items": [{"score_ratio": 1}]}')
    with pytest.raises(ValidationError):
        LLMGradeBatch.model_validate_json('{"items": [{"question_id": "E1", "score_ratio": "满分"}]}')


def test_validate_grade_batch_id_set_must_match():
    batch = LLMGradeBatch(items=[LLMGradeItem(question_id="E1", score_ratio=0.5)])
    validate_grade_batch(batch, {"E1"})
    with pytest.raises(ValueError):
        validate_grade_batch(batch, {"E1", "E2"})  # 缺失
    with pytest.raises(ValueError):
        validate_grade_batch(batch, {"E9"})  # 多余
    dup = LLMGradeBatch(items=[
        LLMGradeItem(question_id="E1", score_ratio=0.5),
        LLMGradeItem(question_id="E1", score_ratio=0.7),
    ])
    with pytest.raises(ValueError):
        validate_grade_batch(dup, {"E1"})


def test_ratio_to_score_decimal_rounding():
    assert ratio_to_score(0.5, 25) == 13  # 12.5 → ROUND_HALF_UP
    assert ratio_to_score(0.0, 25) == 0
    assert ratio_to_score(1.0, 25) == 25


def test_verdict_from_score():
    assert verdict_from_score(0, 10, answered=False) == "unanswered"
    assert verdict_from_score(10, 10, answered=True) == "correct"
    assert verdict_from_score(5, 10, answered=True) == "partial"
    assert verdict_from_score(0, 10, answered=True) == "wrong"


def test_exam_review_totals_must_be_consistent():
    result = QuestionResult(
        id="C1", type="cloze", points=10, score=10, verdict="correct",
        my_answer="a", correct_answer="a",
    )
    with pytest.raises(ValidationError):
        ExamReview(
            exam_id="eid", total_score=99,
            sections={"cloze": SectionScore(earned=10, max=10)},
            results=[result],
        )

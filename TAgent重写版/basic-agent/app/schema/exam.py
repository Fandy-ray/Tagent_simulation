"""试卷数据模型与纯逻辑：LLM 草稿 → 分值归一化 → 私有卷 → 公开卷/判分结果。

设计约束（见评审意见）：
- 三段流水线：GeneratedExamDraft（只校验结构）→ normalize_draft（分值归一）→ PrivateExam（强制总分 100）；
- 题目 ID 由后端生成（C1/M1/E1），不信任 LLM 输出；
- PublicExam 用显式字段映射构造，递归排除 accept/correct_index/reference_answer/rubric/explanation；
- LLM 判分输出走 LLMGradeBatch 校验：ID 集合精确等于送评子集、拒绝非有限数、score_ratio clamp 0..1；
- 本文件不依赖 LLM/网络，全部可离线单测。
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Literal, Optional, Set, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

# ====================== 全局约束常量（出题 prompt 与校验共用） ======================
TOTAL_POINTS = 100
# 全卷 16~21 题：题量够铺满试卷版面，客观题占比提高后单题分值下降，
# 判错一道的损失变小，配合分批判分（ExamService._grade_batches）保证判分稳定。
CLOZE_COUNT_RANGE = (8, 10)
CHOICE_COUNT_RANGE = (6, 8)
ESSAY_COUNT_RANGE = (2, 3)
# 各题型总分上下界；sum(lo)=74 <= 100 <= sum(hi)=111，保证投影算法必然有解
TYPE_SHARE_BOUNDS: Dict[str, tuple] = {
    "cloze": (20, 30),
    "choice": (24, 36),
    "essay": (30, 45),
}


def _assert_bounds_consistent() -> None:
    """题量与分值区间的相容性检查，导入即执行。

    两条不变量一旦被后续调参破坏，故障会推迟到线上某次 normalize_draft 才
    暴露（且表现为 502），所以在导入期就炸掉：
    - sum(lo) <= 100 <= sum(hi)：_project_type_totals 的投影必然有解；
    - 每型 lo >= 该型最大题量：_largest_remainder 能给每题至少 1 分。
    """
    lo_sum = sum(lo for lo, _ in TYPE_SHARE_BOUNDS.values())
    hi_sum = sum(hi for _, hi in TYPE_SHARE_BOUNDS.values())
    if not (lo_sum <= TOTAL_POINTS <= hi_sum):
        raise RuntimeError(
            f"题型分值区间无解：sum(lo)={lo_sum}, sum(hi)={hi_sum}, total={TOTAL_POINTS}"
        )
    for key, (_, max_count) in (
        ("cloze", CLOZE_COUNT_RANGE),
        ("choice", CHOICE_COUNT_RANGE),
        ("essay", ESSAY_COUNT_RANGE),
    ):
        lo = TYPE_SHARE_BOUNDS[key][0]
        if lo < max_count:
            raise RuntimeError(f"{key} 最低总分 {lo} 不足以给 {max_count} 道题各 1 分")


_assert_bounds_consistent()

QuestionType = Literal["cloze", "choice", "essay"]
Verdict = Literal["correct", "partial", "wrong", "unanswered"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ====================== 题目模型（草稿 / 私有） ======================
class _ClozeBase(StrictModel):
    type: Literal["cloze"] = "cloze"
    cue: str = Field(min_length=1)          # 中文提示语（参照闪卡的 cue）
    text: str                                # 含恰好一个 ____ 的句子
    accept: List[str] = Field(min_length=1)  # 可接受答案列表
    # exact：公式/单位/代号等大小写敏感内容；text：普通文字答案
    match_mode: Literal["text", "exact"] = "text"
    explanation: str = ""

    @field_validator("text")
    @classmethod
    def _exactly_one_blank(cls, v: str) -> str:
        if v.count("____") != 1:
            raise ValueError("填空题 text 必须恰好包含一个 ____")
        return v

    @field_validator("accept")
    @classmethod
    def _accept_non_blank(cls, v: List[str]) -> List[str]:
        cleaned = [a for a in v if a and a.strip()]
        if not cleaned:
            raise ValueError("accept 不能为空")
        return cleaned


class _ChoiceBase(StrictModel):
    type: Literal["choice"] = "choice"
    question: str = Field(min_length=1)
    options: List[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: str = ""


class _EssayBase(StrictModel):
    type: Literal["essay"] = "essay"
    question: str = Field(min_length=1)
    reference_answer: str = Field(min_length=1)
    rubric: str = Field(min_length=1)  # 评分要点


class DraftClozeQuestion(_ClozeBase):
    id: Optional[str] = None  # LLM 若输出 id 则忽略，后端重新编号
    points: float = Field(gt=0)


class DraftChoiceQuestion(_ChoiceBase):
    id: Optional[str] = None
    points: float = Field(gt=0)


class DraftEssayQuestion(_EssayBase):
    id: Optional[str] = None
    points: float = Field(gt=0)


class ClozeQuestion(_ClozeBase):
    id: str
    points: int = Field(ge=1)


class ChoiceQuestion(_ChoiceBase):
    id: str
    points: int = Field(ge=1)


class EssayQuestion(_EssayBase):
    id: str
    points: int = Field(ge=1)


PrivateQuestion = Union[ClozeQuestion, ChoiceQuestion, EssayQuestion]


def _check_count(name: str, items: list, bounds: tuple) -> None:
    lo, hi = bounds
    if not (lo <= len(items) <= hi):
        raise ValueError(f"{name}题数量 {len(items)} 超出约束 [{lo}, {hi}]")


# 分段草稿里模型多给几道时**收下当余量**，别把整段判废。
#
# 两个理由：
# - 多给一道就整段重试，白等一轮模型，而那一道本来可以直接扔掉；
# - 出完题还要过 exam_quality 的闸（指代材料、答案写在题干里）。没有余量时
#   删掉两三道就跌破下限 → 重试 → 还不够 → 502（接规划那一步时实测到过）。
#
# 超出的部分在 exam_service 里裁掉，**最终试卷**（GeneratedExamDraft）仍然
# 严格落在 COUNT_RANGE 内——放宽的只是中间产物。
DRAFT_OVERSHOOT = 4


def _check_draft_count(name: str, items: list, bounds: tuple) -> None:
    lo, hi = bounds
    _check_count(name, items, (lo, hi + DRAFT_OVERSHOOT))


# 出卷按题型分三段生成。整卷 16~21 题一次输出上万 token，单次调用必然顶穿
# per-attempt 超时（实测 110s、拆两段后 100s 都仍被截断 → 前端 504）。
# 分三段后每段仅 2~3 千 token，各自都能在超时内跑完，且某段结构不合法时
# 只重试那一段，不用把整张卷子重出。
class ClozeExamDraft(StrictModel):
    """出卷第一段：填空题（顺带定卷名）。"""

    title: str = "知识点测评"
    cloze: List[DraftClozeQuestion]

    @model_validator(mode="after")
    def _count_ranges(self):
        _check_draft_count("填空", self.cloze, CLOZE_COUNT_RANGE)
        return self


class ChoiceExamDraft(StrictModel):
    """出卷第二段：选择题。"""

    choice: List[DraftChoiceQuestion]

    @model_validator(mode="after")
    def _count_ranges(self):
        _check_draft_count("选择", self.choice, CHOICE_COUNT_RANGE)
        return self


class EssayExamDraft(StrictModel):
    """出卷第三段：解答题（含 reference_answer 与 rubric，单题输出最长）。"""

    essay: List[DraftEssayQuestion]

    @model_validator(mode="after")
    def _count_ranges(self):
        _check_draft_count("大题", self.essay, ESSAY_COUNT_RANGE)
        return self


class GeneratedExamDraft(StrictModel):
    """两段合并后的完整草稿：只校验结构与题量，分值尚未归一。"""

    title: str = "知识点测评"
    cloze: List[DraftClozeQuestion]
    choice: List[DraftChoiceQuestion]
    essay: List[DraftEssayQuestion]

    @model_validator(mode="after")
    def _count_ranges(self):
        _check_count("填空", self.cloze, CLOZE_COUNT_RANGE)
        _check_count("选择", self.choice, CHOICE_COUNT_RANGE)
        _check_count("大题", self.essay, ESSAY_COUNT_RANGE)
        return self


class PrivateExam(StrictModel):
    """含答案的完整试卷（仅存服务端缓存，绝不直接返回给前端）。"""

    exam_id: str
    title: str
    cloze: List[ClozeQuestion]
    choice: List[ChoiceQuestion]
    essay: List[EssayQuestion]

    def all_questions(self) -> List[PrivateQuestion]:
        return [*self.cloze, *self.choice, *self.essay]

    @model_validator(mode="after")
    def _validate_exam(self):
        ids = [q.id for q in self.all_questions()]
        if len(ids) != len(set(ids)):
            raise ValueError("题目 ID 重复")
        for key, items in (("cloze", self.cloze), ("choice", self.choice), ("essay", self.essay)):
            lo, hi = TYPE_SHARE_BOUNDS[key]
            subtotal = sum(q.points for q in items)
            if not (lo <= subtotal <= hi):
                raise ValueError(f"{key} 题型总分 {subtotal} 超出区间 [{lo}, {hi}]")
        total = sum(q.points for q in self.all_questions())
        if total != TOTAL_POINTS:
            raise ValueError(f"总分必须为 {TOTAL_POINTS}，当前 {total}")
        return self


# ====================== 公开卷（脱敏）——显式字段映射，禁止拷贝后删字段 ======================
class PublicClozeQuestion(StrictModel):
    id: str
    type: Literal["cloze"] = "cloze"
    cue: str
    text: str
    points: int


class PublicChoiceQuestion(StrictModel):
    id: str
    type: Literal["choice"] = "choice"
    question: str
    options: List[str]
    points: int


class PublicEssayQuestion(StrictModel):
    id: str
    type: Literal["essay"] = "essay"
    question: str
    points: int


class PublicExam(StrictModel):
    exam_id: str
    title: str
    total_points: int
    cloze: List[PublicClozeQuestion]
    choice: List[PublicChoiceQuestion]
    essay: List[PublicEssayQuestion]


def to_public(exam: PrivateExam) -> PublicExam:
    """显式逐字段构造公开卷。新增私有字段时此处不写就不会泄露。"""
    return PublicExam(
        exam_id=exam.exam_id,
        title=exam.title,
        total_points=TOTAL_POINTS,
        cloze=[
            PublicClozeQuestion(id=q.id, cue=q.cue, text=q.text, points=q.points)
            for q in exam.cloze
        ],
        choice=[
            PublicChoiceQuestion(
                id=q.id, question=q.question, options=list(q.options), points=q.points
            )
            for q in exam.choice
        ],
        essay=[
            PublicEssayQuestion(id=q.id, question=q.question, points=q.points)
            for q in exam.essay
        ],
    )


# ====================== 分值归一化 ======================
def _project_type_totals(raw: Dict[str, float]) -> Dict[str, int]:
    """把 LLM 原始题型分值占比投影到 TYPE_SHARE_BOUNDS 内，且总和恰为 100。"""
    total_raw = sum(max(v, 0.0) for v in raw.values())
    totals: Dict[str, int] = {}
    for key, (lo, hi) in TYPE_SHARE_BOUNDS.items():
        if total_raw > 0:
            share = TOTAL_POINTS * max(raw.get(key, 0.0), 0.0) / total_raw
        else:
            share = TOTAL_POINTS / len(TYPE_SHARE_BOUNDS)
        totals[key] = int(min(max(round(share), lo), hi))

    diff = TOTAL_POINTS - sum(totals.values())
    while diff != 0:
        if diff > 0:
            key = max(TYPE_SHARE_BOUNDS, key=lambda k: TYPE_SHARE_BOUNDS[k][1] - totals[k])
            if TYPE_SHARE_BOUNDS[key][1] - totals[key] <= 0:
                raise ValueError("题型分值投影无解")  # sum(hi)>=100 时不可达
            totals[key] += 1
            diff -= 1
        else:
            key = max(TYPE_SHARE_BOUNDS, key=lambda k: totals[k] - TYPE_SHARE_BOUNDS[k][0])
            if totals[key] - TYPE_SHARE_BOUNDS[key][0] <= 0:
                raise ValueError("题型分值投影无解")  # sum(lo)<=100 时不可达
            totals[key] -= 1
            diff += 1
    return totals


def _largest_remainder(weights: List[float], total: int) -> List[int]:
    """按权重把 total 分成整数份，每份 >=1，总和严格等于 total（最大余数法）。"""
    n = len(weights)
    if n == 0:
        raise ValueError("题目列表为空")
    if total < n:
        raise ValueError(f"总分 {total} 不足以保证每题至少 1 分（共 {n} 题）")

    weight_sum = sum(max(w, 0.0) for w in weights) or float(n)
    quotas = [max(w, 0.0) / weight_sum * total for w in weights]
    floors = [max(1, math.floor(q)) for q in quotas]

    # 某些 quota<1 被提到 1 时可能挤爆总额：从最大份中扣回（最大份必 >1）
    while sum(floors) > total:
        i = max(range(n), key=lambda j: floors[j])
        floors[i] -= 1

    remainder = total - sum(floors)
    order = sorted(range(n), key=lambda j: quotas[j] - math.floor(quotas[j]), reverse=True)
    for k in range(remainder):
        floors[order[k % n]] += 1
    return floors


def normalize_draft(draft: GeneratedExamDraft, exam_id: str) -> PrivateExam:
    """草稿 → 私有卷：后端编号（C1/M1/E1）+ 分值归一到总分 100。"""
    type_totals = _project_type_totals(
        {
            "cloze": sum(q.points for q in draft.cloze),
            "choice": sum(q.points for q in draft.choice),
            "essay": sum(q.points for q in draft.essay),
        }
    )

    cloze_points = _largest_remainder([q.points for q in draft.cloze], type_totals["cloze"])
    choice_points = _largest_remainder([q.points for q in draft.choice], type_totals["choice"])
    essay_points = _largest_remainder([q.points for q in draft.essay], type_totals["essay"])

    return PrivateExam(
        exam_id=exam_id,
        title=draft.title.strip() or "知识点测评",
        cloze=[
            ClozeQuestion(
                id=f"C{i + 1}", cue=q.cue, text=q.text, accept=q.accept,
                match_mode=q.match_mode, explanation=q.explanation, points=p,
            )
            for i, (q, p) in enumerate(zip(draft.cloze, cloze_points))
        ],
        choice=[
            ChoiceQuestion(
                id=f"M{i + 1}", question=q.question, options=q.options,
                correct_index=q.correct_index, explanation=q.explanation, points=p,
            )
            for i, (q, p) in enumerate(zip(draft.choice, choice_points))
        ],
        essay=[
            EssayQuestion(
                id=f"E{i + 1}", question=q.question, reference_answer=q.reference_answer,
                rubric=q.rubric, points=p,
            )
            for i, (q, p) in enumerate(zip(draft.essay, essay_points))
        ],
    )


# ====================== 填空匹配（纯逻辑） ======================
_TEXT_STRIP_PUNCT = "。，,.;；:：!！?？、\"'“”‘’()（）[]【】"


def _normalize_text_answer(value: str) -> str:
    v = unicodedata.normalize("NFKC", value).casefold().strip()
    v = v.strip(_TEXT_STRIP_PUNCT).strip()
    v = re.sub(r"\s+", " ", v)
    return v


def _normalize_exact_answer(value: str) -> str:
    # exact 模式保留大小写（mW 与 MW 不同），只做宽度归一与首尾空白清理
    return unicodedata.normalize("NFKC", value).strip()


def needs_llm_recheck(match_mode: str) -> bool:
    """本地未匹配的填空是否送 LLM 语义复核。

    只有 text 模式允许复核同义表述；exact 模式（公式/单位/大小写敏感符号）
    必须严格匹配，送 LLM 会让 mW/MW 这类差异被错误"翻案"。
    """
    return match_mode == "text"


def cloze_matches(user_answer: str, accept: List[str], match_mode: str) -> bool:
    if not user_answer or not user_answer.strip():
        return False
    if match_mode == "exact":
        normalized = _normalize_exact_answer(user_answer)
        return any(normalized == _normalize_exact_answer(a) for a in accept)
    normalized = _normalize_text_answer(user_answer)
    if not normalized:
        return False
    return any(normalized == _normalize_text_answer(a) for a in accept)


# ====================== 判分模型 ======================
class LLMGradeItem(StrictModel):
    question_id: str
    score_ratio: float
    verdict: Optional[str] = None  # 接受但忽略：verdict 由后端按分数生成
    feedback: str = ""

    @field_validator("score_ratio", mode="before")
    @classmethod
    def _finite_and_clamped(cls, v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise ValueError("score_ratio 必须是数字")
        if not math.isfinite(f):
            raise ValueError("score_ratio 必须是有限数")
        return min(max(f, 0.0), 1.0)


class LLMGradeBatch(StrictModel):
    items: List[LLMGradeItem]
    overall_comment: str = ""


def validate_grade_batch(batch: LLMGradeBatch, expected_ids: Set[str]) -> None:
    """判分 LLM 的 ID 集合必须精确等于本次送评子集（不缺、不多、不重复）。"""
    got = [item.question_id for item in batch.items]
    if len(got) != len(set(got)):
        raise ValueError("判分结果存在重复题目 ID")
    if set(got) != expected_ids:
        missing = expected_ids - set(got)
        extra = set(got) - expected_ids
        raise ValueError(f"判分结果 ID 不匹配：缺失 {sorted(missing)}，多余 {sorted(extra)}")


# ====================== 旧版单题接口的 LLM 输出校验 ======================
class LegacyQuizQuestion(BaseModel):
    """旧出题输出。extra=ignore：模型多给字段不算错。"""

    model_config = ConfigDict(extra="ignore")
    title: str = "知识点测试"
    question: str

    @field_validator("question")
    @classmethod
    def _question_non_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question 不能为空白")
        return v


class LegacyQuizReview(BaseModel):
    """旧判题输出。四个契约字段全部必填（{}/缺字段 → ValidationError → 上游 502）；
    is_correct/score 宽松转换（"false"/"90" 可救），分数 clamp 0..100。"""

    model_config = ConfigDict(extra="ignore")
    is_correct: bool
    score: float
    comment: str
    correct_answer: str

    @field_validator("score", mode="before")
    @classmethod
    def _score_finite_clamped(cls, v):
        if isinstance(v, bool):
            # float(True)==1.0 会把布尔悄悄变成 1 分，必须显式拒绝
            raise ValueError("score 不能是布尔值")
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise ValueError("score 必须是数字")
        if not math.isfinite(f):
            raise ValueError("score 必须是有限数")
        return min(max(f, 0.0), 100.0)


def parse_legacy_question(text: str) -> Optional[Dict[str, str]]:
    """旧出题输出 → {"title", "question"}；结构无法救回时返回 None（上游应报 502）。

    非 JSON 的纯文本视为模型直接给了题目（格式兜底，不是错误路径）；
    合法 JSON 但不是对象（[]/null/字符串）、字段缺失或空白 → None，
    绝不让 .get() 落 AttributeError 变 500。
    """
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return {"title": "知识点测试", "question": raw}
    if not isinstance(data, dict):
        return None
    try:
        parsed = LegacyQuizQuestion.model_validate(data)
    except ValidationError:
        return None
    return {"title": parsed.title.strip() or "知识点测试", "question": parsed.question}


def parse_legacy_review(text: str) -> Optional[Dict[str, object]]:
    """旧判题输出 → 契约字段；结构无法救回时返回 None（上游应报 502）。

    非 JSON、合法 JSON 但不是对象，或 score/is_correct 无法安全转换 → None，
    绝不把上游协议失败伪装成一次合法的 0 分判题。
    """
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        parsed = LegacyQuizReview.model_validate(data)
    except ValidationError:
        return None
    return {
        "is_correct": parsed.is_correct,
        "score": int(round(parsed.score)),
        "comment": parsed.comment,
        "correct_answer": parsed.correct_answer,
    }


def ratio_to_score(ratio: float, points: int) -> int:
    """score_ratio × points，用 Decimal 四舍五入到整数分。"""
    return int(
        (Decimal(str(ratio)) * Decimal(points)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def verdict_from_score(score: int, points: int, answered: bool) -> Verdict:
    """verdict 由后端按得分生成，不信任 LLM 自报。"""
    if not answered:
        return "unanswered"
    if score >= points:
        return "correct"
    if score > 0:
        return "partial"
    return "wrong"


# ====================== 判分结果 ======================
class QuestionResult(StrictModel):
    id: str
    type: QuestionType
    points: int
    score: int = Field(ge=0)
    verdict: Verdict
    my_answer: Optional[str] = None       # 展示用（选择题存所选选项文本）
    correct_answer: str
    explanation: str = ""
    feedback: str = ""


class SectionScore(StrictModel):
    earned: int
    max: int


def grade_cloze_locally(question: ClozeQuestion, answer_text: str) -> Optional[QuestionResult]:
    """填空题本地判分；返回 None 表示 text 模式未匹配、需送 LLM 语义复核。

    exact 模式（公式/单位/大小写敏感符号）未匹配直接判错、绝不送 LLM，
    防止 mW/MW 这类差异被语义"翻案"。review_exam 与单测共用此函数，
    保证测试覆盖的就是线上分流路径。
    """
    correct_display = " / ".join(question.accept)
    if not answer_text:
        return QuestionResult(
            id=question.id, type="cloze", points=question.points, score=0,
            verdict="unanswered", my_answer=None,
            correct_answer=correct_display, explanation=question.explanation,
        )
    if cloze_matches(answer_text, question.accept, question.match_mode):
        return QuestionResult(
            id=question.id, type="cloze", points=question.points, score=question.points,
            verdict="correct", my_answer=answer_text,
            correct_answer=correct_display, explanation=question.explanation,
        )
    if not needs_llm_recheck(question.match_mode):
        return QuestionResult(
            id=question.id, type="cloze", points=question.points, score=0,
            verdict="wrong", my_answer=answer_text,
            correct_answer=correct_display, explanation=question.explanation,
            feedback="该题要求精确作答（公式/单位/符号），答案不匹配。",
        )
    return None


class ExamReview(StrictModel):
    exam_id: str
    total_score: int
    total_points: int = TOTAL_POINTS
    sections: Dict[str, SectionScore]
    results: List[QuestionResult]
    overall_comment: str = ""

    @model_validator(mode="after")
    def _totals_consistent(self):
        if self.total_score != sum(r.score for r in self.results):
            raise ValueError("total_score 必须等于逐题得分之和")
        if self.total_score != sum(s.earned for s in self.sections.values()):
            raise ValueError("total_score 必须等于分节得分之和")
        ids = [r.id for r in self.results]
        if len(ids) != len(set(ids)):
            raise ValueError("判分结果题目 ID 重复")
        return self


# ====================== 出卷前的考点规划 ======================
#
# 三段是并发跑的，彼此看不见对方出了什么，于是同一个考点会被问两遍
# （实测：填空问「ρ 的计算公式」，选择又问「ρ 的表达式」）。
#
# 仓库里有条压测结论是「把已考清单塞回 prompt 反而更重复」——那说的是**串行**
# 地把前一段的结果传给后一段。这里不一样：先一次性定好考点并**切成互不相交的
# 三份**，三段仍然并发，各自只认领到的那几个。代价是多一个模型来回。
class ExamPlan(StrictModel):
    """出卷前定下的考点清单。"""

    points: List[str] = Field(min_length=1)

    @field_validator("points")
    @classmethod
    def _distinct_and_clean(cls, value: List[str]) -> List[str]:
        cleaned: List[str] = []
        seen: Set[str] = set()
        for item in value:
            text = " ".join(str(item).split())
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(text)
        if not cleaned:
            raise ValueError("考点清单为空")
        return cleaned


def split_plan(points: List[str], shares: List[int]) -> List[List[str]]:
    """把考点轮流发给各段，发出来的几份互不相交。

    轮流发（而不是按顺序切块）是因为模型往往把最核心的考点排在前面；
    顺序切块会让第一段独占全部核心考点，后面两段只能捡边角。
    """
    groups: List[List[str]] = [[] for _ in shares]
    if not points or not shares:
        return groups

    quota = list(shares)
    index = 0
    for point in points:
        for _ in range(len(quota)):
            slot = index % len(quota)
            index += 1
            if quota[slot] > 0:
                groups[slot].append(point)
                quota[slot] -= 1
                break
        else:
            break
    return groups

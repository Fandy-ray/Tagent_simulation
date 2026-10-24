"""Production wiring tests for dynamic-provider exam grading."""

import asyncio
import json
import time
import types

import pytest

from app.service.exam_service import ExamService
from app.service.quiz_service import QuizService
from app.errors.api_errors import AgentAPIError
from app.schema.exam import (
    CHOICE_COUNT_RANGE,
    CLOZE_COUNT_RANGE,
    ESSAY_COUNT_RANGE,
    DraftChoiceQuestion,
    DraftClozeQuestion,
    DraftEssayQuestion,
    GeneratedExamDraft,
    normalize_draft,
    ratio_to_score,
)
from app.errors.exam_errors import InvalidExamRequestError, UpstreamLLMError
from app.repository.exam_cache import ExamCache, LLMGate, StoredExam
from app.schema.provider import ModelProvider


TEST_PROVIDER = ModelProvider(
    name="Test provider",
    served_model_id="test-provider",
    base_url="https://example.invalid/v1",
    upstream_model="test-upstream",
    auth_mode="bearer",
    api_key="test-key",
    temperature=0.1,
    created_at="2026-07-18T00:00:00Z",
    updated_at="2026-07-18T00:00:00Z",
)


def make_exam(exam_id="wiring-exam-1"):
    draft = GeneratedExamDraft(
        cloze=[
            DraftClozeQuestion(
                cue="功率单位",
                text="接收功率约 1 ____",
                accept=["mW"],
                match_mode="exact",
                points=5,
            ),
            DraftClozeQuestion(
                cue="延迟类型",
                text="____ 是分组排队等待造成的",
                accept=["排队延迟"],
                points=5,
            ),
            *[
                DraftClozeQuestion(
                    cue=f"c{i}", text=f"第 {i} 题 ____", accept=[f"答案{i}"], points=5
                )
                for i in range(3, CLOZE_COUNT_RANGE[0] + 1)
            ],
        ],
        choice=[
            DraftChoiceQuestion(
                question=f"选择题{i}",
                options=["甲", "乙", "丙", "丁"],
                correct_index=0,
                points=6,
            )
            for i in range(CHOICE_COUNT_RANGE[0])
        ],
        essay=[
            DraftEssayQuestion(
                question="论述离散事件仿真的核心流程",
                reference_answer="参考答案",
                rubric="要点覆盖",
                points=30,
            ),
            *[
                DraftEssayQuestion(
                    question=f"论述题 {i}",
                    reference_answer="参考答案",
                    rubric="要点覆盖",
                    points=30,
                )
                for i in range(1, ESSAY_COUNT_RANGE[0])
            ],
        ],
    )
    return normalize_draft(draft, exam_id)


class ScriptedGradeLLM:
    """按批作答的假模型。

    判分已按题型分批（见 app/agent/graphs/grade.py），每批的 ID 集合都要精确
    匹配，所以默认只回本批待评 JSON 中的题号——照搬整份 payload 会被
    validate_grade_batch 判为"多余 ID"。verbatim=True 用于故意回错题号的用例。
    """

    def __init__(self, payload, verbatim=False):
        self.payload = payload
        self.verbatim = verbatim
        self.calls = 0
        self.prompts = []

    def bind(self, **_kwargs):
        return self

    async def ainvoke(self, prompt):
        self.calls += 1
        self.last_prompt = prompt
        self.prompts.append(prompt)
        payload = self.payload
        if not self.verbatim:
            # prompt 的输出格式示例也包含 E1/C1，不能把示例题号算进待评集合。
            requested_ids = {
                item["question_id"]
                for item in json.loads(prompt.split("待评题目：\n", 1)[1])
            }
            payload = {
                **payload,
                "items": [
                    item
                    for item in payload["items"]
                    if item["question_id"] in requested_ids
                ],
            }
        return types.SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))


class RejectingFactory:
    def get(self, *_args, **_kwargs):
        raise AssertionError("Local-only grading must not construct an LLM client")


class StaticFactory:
    def __init__(self, client):
        self.client = client

    def get(self, selected, **_kwargs):
        assert selected.served_model_id == TEST_PROVIDER.served_model_id
        return self.client


class FakeKnowledgeBase:
    """判卷路径不碰知识库；retrieve 只为单题判分那条用例提供片段。"""

    def retrieve(self, _query, notebook_ids=None):
        return "教材片段", []

    def sample_exam_context(self, topic=None, notebook_ids=None) -> str:
        return "教材片段"

    def search(self, _query, *, k=3):
        return [types.SimpleNamespace(page_content="教材片段")]


def make_sim(exam, client=None):
    cache = ExamCache()
    cache.put(
        exam.exam_id,
        StoredExam(exam=exam, served_model_id=TEST_PROVIDER.served_model_id),
    )
    return ExamService(
        FakeKnowledgeBase(),
        StaticFactory(client) if client is not None else RejectingFactory(),
        exam_cache=cache,
        llm_gate=LLMGate(max_concurrent=2),
    )


def test_local_only_paths_never_construct_llm():
    exam = make_exam()
    sim = make_sim(exam)
    review = sim.review_exam(
        exam.exam_id,
        {"C1": "MW", "C2": " 排队延迟。", "M1": 0, "M2": 1},
        TEST_PROVIDER,
    )
    by_id = {result.id: result for result in review.results}
    assert by_id["C1"].verdict == "wrong"
    assert by_id["C2"].verdict == "correct"
    assert by_id["M1"].verdict == "correct"
    assert by_id["M2"].verdict == "wrong"
    assert by_id["E1"].verdict == "unanswered"
    assert review.total_score == sum(result.score for result in review.results)


def test_text_mismatch_and_essay_are_graded_in_separate_typed_batches():
    """填空复核与解答题必须分批送评：两套评分尺度不能挤在同一条 prompt 里。"""
    exam = make_exam("wiring-exam-2")
    client = ScriptedGradeLLM(
        {
            "items": [
                {"question_id": "C2", "score_ratio": 0, "feedback": "语义不符"},
                {"question_id": "E1", "score_ratio": 0.5, "feedback": "覆盖部分要点"},
            ],
            "overall_comment": "总体一般",
        }
    )
    review = make_sim(exam, client).review_exam(
        exam.exam_id,
        {"C2": "传播延迟", "E1": "事件调度、时钟推进、状态更新"},
        TEST_PROVIDER,
    )
    assert client.calls == 2  # 一批解答题 + 一批填空复核
    essay_prompts = [p for p in client.prompts if "只判**解答题**" in p]
    cloze_prompts = [p for p in client.prompts if "只判**填空题**" in p]
    assert len(essay_prompts) == 1 and len(cloze_prompts) == 1
    # 每批只看见自己的题号，互不串味
    assert '"E1"' in essay_prompts[0] and '"C2"' not in essay_prompts[0]
    assert '"C2"' in cloze_prompts[0] and '"E1"' not in cloze_prompts[0]

    by_id = {result.id: result for result in review.results}
    assert by_id["C2"].feedback == "语义不符"
    assert by_id["E1"].score == ratio_to_score(0.5, exam.essay[0].points)
    assert "已作答 2/16 题，14 题未作答" in review.overall_comment
    assert f"总分 {review.total_score}/100" in review.overall_comment
    assert "1 题部分得分，1 题未得分" in review.overall_comment
    assert "总体一般" not in review.overall_comment
    assert "传播延迟" in cloze_prompts[0]


def make_report_exam():
    """Windows 报告：21 题，C1/M1/E1 分别为 3/4/15 分。"""
    return normalize_draft(
        GeneratedExamDraft(
            cloze=[
                DraftClozeQuestion(
                    cue=f"填空 {i}", text=f"填空 {i} ____", accept=[f"答案{i}"],
                    match_mode="exact", points=3,
                )
                for i in range(10)
            ],
            choice=[
                DraftChoiceQuestion(
                    question=f"选择 {i}", options=["甲", "乙", "丙", "丁"],
                    correct_index=0, points=3,
                )
                for i in range(8)
            ],
            essay=[
                DraftEssayQuestion(
                    question=f"解答 {i}", reference_answer="参考答案",
                    rubric="评分要点", points=15,
                )
                for i in range(3)
            ],
        ),
        "windows-report-exam",
    )


def test_sparse_exam_summary_covers_all_questions_and_preserves_essay_feedback():
    exam = make_report_exam()
    essay_feedback = "本题作答完整准确，四个得分要点全部命中，计算过程和结论均正确"
    client = ScriptedGradeLLM({
        "items": [{"question_id": "E1", "score_ratio": 1, "feedback": essay_feedback}],
        "overall_comment": essay_feedback,
    })

    review = make_sim(exam, client).review_exam(
        exam.exam_id, {"C1": "答案0", "M1": 0, "E1": "全部要点的答案"}, TEST_PROVIDER,
    )

    assert client.calls == 1
    assert review.total_score == 22
    assert "已作答 3/21 题，18 题未作答，总分 22/100" in review.overall_comment
    assert "填空题 3/30 分，选择题 4/25 分，解答题 15/45 分" in review.overall_comment
    assert "已答题中，3 题满分" in review.overall_comment
    assert "补齐未作答题目" in review.overall_comment
    assert essay_feedback not in review.overall_comment
    by_id = {result.id: result for result in review.results}
    assert by_id["E1"].feedback == essay_feedback
    assert by_id["E1"].score == by_id["E1"].points == 15


def test_blank_exam_summary_counts_null_and_whitespace_as_unanswered_without_llm():
    exam = make_report_exam()
    review = make_sim(exam).review_exam(
        exam.exam_id, {"C1": " \t", "M1": None, "E1": "\n "}, TEST_PROVIDER,
    )

    assert review.total_score == 0
    assert "已作答 0/21 题，21 题未作答，总分 0/100" in review.overall_comment
    assert all(result.verdict == "unanswered" for result in review.results)
    assert "补齐未作答题目" in review.overall_comment


@pytest.mark.parametrize("last_essay_ratio", [1, 0.5])
def test_complete_exam_summary_includes_results_from_every_grading_batch(last_essay_ratio):
    exam = make_report_exam()
    client = ScriptedGradeLLM({
        "items": [
            {"question_id": question.id,
             "score_ratio": last_essay_ratio if question.id == "E3" else 1,
             "feedback": f"{question.id} 的单题反馈"}
            for question in exam.essay
        ],
        "overall_comment": "仅适用于当前批次的评语",
    })
    answers = {
        **{question.id: question.accept[0] for question in exam.cloze},
        **{question.id: question.correct_index for question in exam.choice},
        **{question.id: "作答内容" for question in exam.essay},
    }
    review = make_sim(exam, client).review_exam(exam.exam_id, answers, TEST_PROVIDER)

    assert client.calls == 2
    assert "已作答 21/21 题，0 题未作答" in review.overall_comment
    assert "仅适用于当前批次的评语" not in review.overall_comment
    assert "补齐未作答题目" not in review.overall_comment
    assert review.results[-1].feedback == "E3 的单题反馈"
    if last_essay_ratio == 1:
        assert review.total_score == 100
        assert "总分 100/100" in review.overall_comment
        assert "21 题满分，0 题部分得分，0 题未得分" in review.overall_comment
        assert "全部作答且均获满分" in review.overall_comment
    else:
        assert review.total_score == 93
        assert "总分 93/100" in review.overall_comment
        assert "20 题满分，1 题部分得分，0 题未得分" in review.overall_comment
        assert "复习失分知识点" in review.overall_comment


def test_grading_batches_run_at_the_same_time():
    # 三道大题切成两批（每批 2 道）。批与批互不依赖，总耗时该是最慢的一批，不是相加
    class SlowGradeLLM(ScriptedGradeLLM):
        async def ainvoke(self, prompt):
            await asyncio.sleep(0.3)
            return await super().ainvoke(prompt)

    exam = make_report_exam()
    client = SlowGradeLLM({
        "items": [
            {"question_id": q.id, "score_ratio": 1, "feedback": "好"} for q in exam.essay
        ],
        "overall_comment": "",
    })
    answers = {question.id: "作答内容" for question in exam.essay}
    started = time.perf_counter()
    review = make_sim(exam, client).review_exam(exam.exam_id, answers, TEST_PROVIDER)
    assert time.perf_counter() - started < 0.5
    assert client.calls == 2
    assert all(r.feedback == "好" for r in review.results if r.type == "essay")


def test_a_failed_reference_search_does_not_fail_grading():
    # 只配一个知识来源时它挂了 search 会抛错；参考材料只是辅助，照样判
    class DownKnowledgeBase(FakeKnowledgeBase):
        def search(self, _query, *, k=3):
            raise RuntimeError("笔记本服务连不上")

    exam = make_exam("wiring-exam-down")
    client = ScriptedGradeLLM({
        "items": [{"question_id": "E1", "score_ratio": 0.5, "feedback": "覆盖部分要点"}],
        "overall_comment": "",
    })
    cache = ExamCache()
    cache.put(exam.exam_id, StoredExam(exam=exam, served_model_id=TEST_PROVIDER.served_model_id))
    sim = ExamService(DownKnowledgeBase(), StaticFactory(client), exam_cache=cache,
                      llm_gate=LLMGate(max_concurrent=2))
    review = sim.review_exam(exam.exam_id, {"E1": "事件调度、时钟推进"}, TEST_PROVIDER)
    by_id = {result.id: result for result in review.results}
    assert by_id["E1"].feedback == "覆盖部分要点"
    assert '"knowledge_context": []' in client.prompts[0]


def test_grade_llm_wrong_ids_retry_then_502():
    exam = make_exam("wiring-exam-3")
    client = ScriptedGradeLLM(
        {
            "items": [{"question_id": "E999", "score_ratio": 1, "feedback": "x"}],
            "overall_comment": "",
        },
        verbatim=True,
    )
    with pytest.raises(UpstreamLLMError) as exc_info:
        make_sim(exam, client).review_exam(
            exam.exam_id,
            {"E1": "作答内容"},
            TEST_PROVIDER,
        )
    assert exc_info.value.status_code == 502
    assert client.calls == 2


def test_unknown_or_mistyped_answers_rejected_before_llm():
    exam = make_exam("wiring-exam-4")
    sim = make_sim(exam)
    for answers in ({"Z9": "x"}, {"C1": 123}, {"M1": True}):
        with pytest.raises(InvalidExamRequestError):
            sim.review_exam(exam.exam_id, answers, TEST_PROVIDER)


def test_single_question_plain_text_maps_to_stable_502():
    class PlainTextClient:
        def invoke(self, _messages):
            return types.SimpleNamespace(content="回答正确，100 分")

    sim = QuizService(FakeKnowledgeBase(), StaticFactory(PlainTextClient()))
    with pytest.raises(AgentAPIError) as exc_info:
        sim.review_quiz("什么是系统仿真？", "回答", TEST_PROVIDER)
    assert exc_info.value.status == 502

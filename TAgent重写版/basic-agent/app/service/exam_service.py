"""整卷服务：三段并发出卷、本地+LLM 分批判卷。

关键约束（改动前务必读 app/config.py 里的压测注释，连同开头那段"数据出处"警示
一起读——里面的秒数是导入前某个未记录模型上的旧值，只能当相对结论用）：
- 出卷按题型分三段并发，整卷一次性输出会顶穿单次调用超时；
- 闪卡只出能本地判定的题型（填空 + 选择），按材料分片并发（generate_flash_deck），卡组不计分；
- 判卷先本地判客观题，只把语义题按题型分批送给模型；
- 试卷缓存里锁定了出卷用的模型，判卷必须用同一个，否则 ModelMismatchError。
"""

from __future__ import annotations

import json
import time
from typing import Any

from app.config import (
    EXAM_LLM_BUDGET,
    GRADE_CLOZE_BATCH,
    GRADE_ESSAY_BATCH,
    GRADE_LLM_BUDGET,
    GRADE_LLM_TIMEOUT,
    GRADE_MIN_ATTEMPT_TIMEOUT,
    FLASH_LLM_BUDGET,
)
from app.errors.exam_errors import (
    InvalidExamRequestError,
    ModelMismatchError,
)
from app.agent.graphs.exam import EXAM_GRAPH
from app.agent.graphs.flash import FLASH_GRAPH
from app.agent.runtime import AgentDeps
from app.infra.llm_json import call_json_llm
from app.prompts.exam_prompts import (
    build_cloze_grade_prompt,
    build_essay_grade_prompt,
)
from app.repository.exam_cache import ExamCache, LLMGate, StoredExam
from app.schema.exam import (
    ExamReview,
    LLMGradeBatch,
    LLMGradeItem,
    PrivateExam,
    PublicExam,
    QuestionResult,
    SectionScore,
    grade_cloze_locally,
    ratio_to_score,
    to_public,
    validate_grade_batch,
    verdict_from_score,
)
from app.schema.flash import (
    PublicFlashDeck,
    to_public_deck,
)
from app.schema.provider import ModelProvider
from app.util.text import chunked


def _build_exam_overall_comment(
    results: list[QuestionResult], sections: dict[str, SectionScore]
) -> str:
    """整卷总评只使用全量判分事实，避免把某一评分批次的评语当作整卷结论。"""
    unanswered = sum(result.verdict == "unanswered" for result in results)
    answered = len(results) - unanswered
    total_score = sum(result.score for result in results)
    total_points = sum(result.points for result in results)
    parts = [
        f"整卷已作答 {answered}/{len(results)} 题，{unanswered} 题未作答，"
        f"总分 {total_score}/{total_points}。",
        "，".join(
            f"{label} {sections[kind].earned}/{sections[kind].max} 分"
            for kind, label in (("cloze", "填空题"), ("choice", "选择题"), ("essay", "解答题"))
        ) + "。",
    ]
    correct = sum(result.verdict == "correct" for result in results)
    partial = sum(result.verdict == "partial" for result in results)
    wrong = sum(result.verdict == "wrong" for result in results)
    if answered:
        parts.append(f"已答题中，{correct} 题满分，{partial} 题部分得分，{wrong} 题未得分。")
    if unanswered:
        parts.append("建议先补齐未作答题目，再结合逐题反馈复习。")
    elif partial or wrong:
        parts.append("建议结合逐题反馈复习失分知识点。")
    else:
        parts.append("本卷全部作答且均获满分。")
    return "".join(parts)



class ExamService:
    def __init__(self, knowledge_base, client_factory, *, exam_cache=None, llm_gate=None,
                 max_concurrent_llm: int = 2):
        self.knowledge_base = knowledge_base
        self.client_factory = client_factory
        self.exam_cache = exam_cache if exam_cache is not None else ExamCache()
        self.llm_gate = llm_gate if llm_gate is not None else LLMGate(max_concurrent=max_concurrent_llm)

    def generate_exam(
        self,
        topic: str | None,
        provider: ModelProvider,
        notebook_ids: list[str] | None = None,
    ) -> PublicExam:
        """出一张私有卷存进缓存，返回不带答案的公开投影。流程见 app/agent/graphs/exam.py。"""
        deps = self._deps(provider, EXAM_LLM_BUDGET)
        # 注意：闸门按「一次出卷」计名额，而一次出卷会并发发出 3 路上游调用
        # （大题与规划同时起步，规划完换成填空 + 选择，任一时刻最多 3 路）。
        # 即上游并发峰值 = EXAM_MAX_CONCURRENT_LLM × 3（默认 5×3=15），
        # 不等于闸门容量本身。调整闸门容量时按这个倍数换算。闪卡也是 × 3。
        with self.llm_gate.acquire():
            exam = EXAM_GRAPH.invoke(
                {"topic": topic, "notebook_ids": notebook_ids}, context=deps
            )["exam"]
        self.exam_cache.put(
            exam.exam_id,
            StoredExam(exam=exam, served_model_id=provider.served_model_id),
        )
        return to_public(exam)

    def generate_flash_deck(
        self,
        topic: str | None,
        provider: ModelProvider,
        notebook_ids: list[str] | None = None,
    ) -> PublicFlashDeck:
        """闪卡组：填空 + 选择两类，按材料分片并发，卡组不计分。流程见 app/agent/graphs/flash.py。"""
        deps = self._deps(provider, FLASH_LLM_BUDGET)
        # 闸门照旧按「一次出卡组」计一个名额，上游并发峰值 = 容量 × FLASH_SHARD_COUNT
        with self.llm_gate.acquire():
            deck = FLASH_GRAPH.invoke(
                {"topic": topic, "notebook_ids": notebook_ids}, context=deps
            )["deck"]

        # 卡组**不进任何缓存**：答案随 to_public_deck 一起发给了前端，判定也在
        # 浏览器本地做，服务端没有任何一条路径会再读它。真要加回服务端复核，
        # 那时再开一个独立的 ExamCache 实例——绝不能借用 exam_cache，
        # review_exam 会对取出的对象调 all_questions()，卡组掉进去就是类型混淆。
        return to_public_deck(deck)

    def _deps(self, provider: ModelProvider, budget_seconds: float) -> AgentDeps:
        """一次运行的依赖。截止时间从进门算起，排队等闸门的时间也算在预算里。"""
        return AgentDeps.start(
            knowledge_base=self.knowledge_base,
            client_factory=self.client_factory,
            provider=provider,
            budget_seconds=budget_seconds,
        )

    def _grade_batches(
        self,
        llm_items: list[dict[str, Any]],
        provider: ModelProvider,
        operation_started: float,
    ) -> list[LLMGradeItem]:
        """按题型把送评题目切成小批逐批评分，返回打平的评分条目。

        分批而不是一次评完，是题量提高后判分准确性的主要保障：
        - 填空复核与解答题各用一套互不干扰的准则（二值判定 vs 逐要点计数），
          混在同一条 prompt 里时两种尺度会互相污染；
        - 每批 ID 集合小，validate_grade_batch 的"不多不少"更容易满足，
          少一次整批重试就少一次评分漂移；
        - max_tokens 按批内题数给，避免十几条 feedback 撑爆输出导致 JSON 截断。

        预算按"剩余时间 / 剩余批数"平分：靠前的批次（含其内部重试）吃不掉
        整个 GRADE_LLM_BUDGET，最后一批不会必然 504。
        """
        essay_items = [item for item in llm_items if item["type"] == "essay"]
        cloze_items = [item for item in llm_items if item["type"] == "cloze"]

        batches: list[tuple[str, list[dict[str, Any]]]] = [
            ("essay", chunk) for chunk in chunked(essay_items, GRADE_ESSAY_BATCH)
        ]
        batches += [("cloze", chunk) for chunk in chunked(cloze_items, GRADE_CLOZE_BATCH)]

        graded: list[LLMGradeItem] = []
        deadline = operation_started + GRADE_LLM_BUDGET

        with self.llm_gate.acquire():
            if essay_items:
                for item in essay_items:
                    documents = self.knowledge_base.search(item["question"], k=3)
                    item["knowledge_context"] = [
                        document.page_content[:600] for document in documents
                    ]

            for index, (kind, chunk) in enumerate(batches):
                batch_started = time.monotonic()
                slice_budget = max(0.0, (deadline - batch_started) / (len(batches) - index))
                # 同 generate_exam：余量必须大于 cancel_grace(5s)，否则批次可能
                # 一次都不尝试就因"预算放不下最坏耗时"直接 504
                attempt_timeout = min(
                    GRADE_LLM_TIMEOUT, max(GRADE_MIN_ATTEMPT_TIMEOUT, slice_budget - 15.0)
                )
                expected_ids = {item["question_id"] for item in chunk}
                build_prompt = (
                    build_essay_grade_prompt if kind == "essay" else build_cloze_grade_prompt
                )
                client = self.client_factory.get(
                    provider,
                    timeout_seconds=int(attempt_timeout),
                    max_retries=0,
                ).bind(max_tokens=600 + 500 * len(chunk))
                batch = call_json_llm(
                    client,
                    build_prompt(json.dumps(chunk, ensure_ascii=False, indent=1)),
                    LLMGradeBatch,
                    attempt_timeout=attempt_timeout,
                    budget_seconds=slice_budget,
                    # 默认参数绑定当前批的 ID 集合：闭包会让所有批都校验最后一批
                    post_validate=lambda value, ids=expected_ids: validate_grade_batch(value, ids),
                    start_time=batch_started,
                )
                graded.extend(batch.items)

        return graded

    def essay_question_for_annotation(
        self, exam_id: str, question_id: str, provider: ModelProvider
    ) -> tuple[str, str]:
        """取某道大题的题干与评分要点，供逐句批注用。返回 (question, rubric)。

        题干与要点一律**从缓存的私有试卷里取**，不接受客户端传值——那等于让
        学生自己定评分标准。学生的作答由他自己传没问题：批注不参与算分，
        分数在 review_exam 那一步就已经定死了。
        """
        cached = self.exam_cache.get_copy(exam_id)
        exam: PrivateExam = cached.exam if isinstance(cached, StoredExam) else cached
        if isinstance(cached, StoredExam) and provider.served_model_id != cached.served_model_id:
            raise ModelMismatchError("批注模型必须与生成试卷时使用的模型一致")

        for question in exam.essay:
            if question.id == question_id:
                return question.question, question.rubric
        raise InvalidExamRequestError(f"{question_id} 不是这份试卷里的大题")

    def review_exam(
        self,
        exam_id: str,
        answers: dict[str, object],
        provider: ModelProvider | None = None,
    ) -> ExamReview:
        """Grade locally or in typed LLM batches, then summarize the entire exam."""
        operation_started = time.monotonic()
        cached = self.exam_cache.get_copy(exam_id)
        if isinstance(cached, StoredExam):
            if provider is None or provider.served_model_id != cached.served_model_id:
                raise ModelMismatchError("判卷模型必须与生成试卷时使用的模型一致")
            exam: PrivateExam = cached.exam
        else:
            # Compatibility for pre-v1 in-memory tests; production writes StoredExam only.
            exam = cached

        valid_ids = {question.id for question in exam.all_questions()}
        extra_ids = set(answers) - valid_ids
        if extra_ids:
            raise InvalidExamRequestError(f"存在未知题号：{sorted(extra_ids)}")

        results: dict[str, QuestionResult] = {}
        llm_items: list[dict[str, Any]] = []
        llm_meta: dict[str, tuple[Any, str]] = {}

        for question in exam.cloze:
            raw = answers.get(question.id)
            if raw is not None and not isinstance(raw, str):
                raise InvalidExamRequestError(f"{question.id} 的答案必须是字符串")
            answer = (raw or "").strip()
            local_result = grade_cloze_locally(question, answer)
            if local_result is not None:
                results[question.id] = local_result
                continue
            llm_items.append(
                {
                    "question_id": question.id,
                    "type": "cloze",
                    "question": question.text,
                    "reference": question.accept,
                    "rubric": "语义等同任一可接受答案给 1，否则给 0",
                    "student_answer": answer,
                }
            )
            llm_meta[question.id] = (question, answer)

        letters = "ABCD"
        for question in exam.choice:
            raw = answers.get(question.id)
            correct_answer = f"{letters[question.correct_index]}. {question.options[question.correct_index]}"
            if raw is None:
                results[question.id] = QuestionResult(
                    id=question.id,
                    type="choice",
                    points=question.points,
                    score=0,
                    verdict="unanswered",
                    my_answer=None,
                    correct_answer=correct_answer,
                    explanation=question.explanation,
                )
                continue
            if isinstance(raw, bool) or not isinstance(raw, int) or not 0 <= raw <= 3:
                raise InvalidExamRequestError(f"{question.id} 的答案必须是 0~3 的整数")
            is_correct = raw == question.correct_index
            results[question.id] = QuestionResult(
                id=question.id,
                type="choice",
                points=question.points,
                score=question.points if is_correct else 0,
                verdict="correct" if is_correct else "wrong",
                my_answer=f"{letters[raw]}. {question.options[raw]}",
                correct_answer=correct_answer,
                explanation=question.explanation,
            )

        for question in exam.essay:
            raw = answers.get(question.id)
            if raw is not None and not isinstance(raw, str):
                raise InvalidExamRequestError(f"{question.id} 的答案必须是字符串")
            answer = (raw or "").strip()
            if not answer:
                results[question.id] = QuestionResult(
                    id=question.id,
                    type="essay",
                    points=question.points,
                    score=0,
                    verdict="unanswered",
                    my_answer=None,
                    correct_answer=question.reference_answer,
                )
                continue
            llm_items.append(
                {
                    "question_id": question.id,
                    "type": "essay",
                    "question": question.question,
                    "reference": question.reference_answer,
                    "rubric": question.rubric,
                    "student_answer": answer,
                }
            )
            llm_meta[question.id] = (question, answer)

        if llm_items:
            if provider is None:
                raise ModelMismatchError("判卷模型不可用，请重新生成试卷")
            graded = self._grade_batches(
                llm_items, provider, operation_started
            )
            for item in graded:
                question, answer = llm_meta[item.question_id]
                score = ratio_to_score(item.score_ratio, question.points)
                is_cloze = question.type == "cloze"
                results[question.id] = QuestionResult(
                    id=question.id,
                    type=question.type,
                    points=question.points,
                    score=score,
                    verdict=verdict_from_score(score, question.points, answered=True),
                    my_answer=answer,
                    correct_answer=" / ".join(question.accept) if is_cloze else question.reference_answer,
                    explanation=question.explanation if is_cloze else "",
                    feedback=item.feedback,
                )

        ordered = [results[question.id] for question in exam.all_questions()]
        sections = {
            name: SectionScore(
                earned=sum(results[question.id].score for question in questions),
                max=sum(question.points for question in questions),
            )
            for name, questions in (
                ("cloze", exam.cloze),
                ("choice", exam.choice),
                ("essay", exam.essay),
            )
        }
        total_score = sum(result.score for result in ordered)
        return ExamReview(
            exam_id=exam_id,
            total_score=total_score,
            sections=sections,
            results=ordered,
            overall_comment=_build_exam_overall_comment(ordered, sections),
        )

"""小论文批改与逐句批注的门面：检查输入、拿闸门、跑图、整理结果。

三个入口，流程本身在 app/agent/graphs/ 里：

- review_paper()      答疑里的论文辅助：三维并发打分 + 条件下钻出高亮（essay.py）
- propose_topic()     答疑论文模式里的出题（essay.py）
- annotate_answer()   整卷大题的逐句批注：按需单独发一轮（annotate.py）

「渐进式披露」在这里是两层意思：
1. **输出**上——不是每句都评，而是定额挑最值得说的几处；
2. **调用**上——没被点名的段落不下钻，整卷大题不点开就一轮都不花。

第 2 层才是省钱的大头：本项目自己的压测结论是单次调用的输出 token 量与上下文
长度才是主要耗时来源（见 app/config.py），所以不发的那一轮省得最彻底。
"""

from __future__ import annotations

from app.agent.graphs.annotate import ANNOTATE_GRAPH
from app.agent.graphs.essay import ESSAY_GRAPH, write_topic
from app.agent.runtime import AgentDeps
from app.config import (
    ANNOTATE_LLM_BUDGET,
    ANNOTATE_LLM_TIMEOUT,
    ANNOTATE_MIN_ANSWER_CHARS,
    ANNOTATE_MIN_ATTEMPT_TIMEOUT,
    ESSAY_LLM_BUDGET,
    ESSAY_MAX_CHARS,
    ESSAY_MIN_CHARS,
    ESSAY_TOPIC_LLM_BUDGET,
    ESSAY_TOPIC_MAX_SUGGESTED_CHARS,
    ESSAY_TOPIC_MIN_SUGGESTED_CHARS,
)
from app.errors.exam_errors import InvalidExamRequestError
from app.prompts.essay_prompts import (
    build_essay_answer_annotation_prompt,
    dimension_order,
)
from app.schema.essay import (
    Annotation,
    AnnotationGradeContext,
    EssayTopic,
    PaperReview,
    build_dimension,
    numbered_text,
    quick_scan,
    weighted_score,
)
from app.schema.provider import ModelProvider
from app.util.text import split_sentences


# 出题时学生没给方向就用它检索：search("") 在向量库与 OpenNoteBook 两边的行为都不可控
_TOPIC_FALLBACK_QUERY = "系统建模与仿真 课程核心概念"


class EssayService:
    def __init__(self, *, knowledge_base, client_factory, llm_gate):
        self.knowledge_base = knowledge_base
        self.client_factory = client_factory
        self.llm_gate = llm_gate

    # ====================== 论文辅助 ======================
    def review_paper(
        self,
        text: str,
        topic: str | None,
        provider: ModelProvider,
        notebook_ids: list[str] | None = None,
    ) -> PaperReview:
        source = (text or "").strip()
        sentences = split_sentences(source)
        scan = quick_scan(source, sentences)

        if scan.characters < ESSAY_MIN_CHARS:
            raise InvalidExamRequestError(
                f"正文只有 {scan.characters} 字，太短了，先写到 {ESSAY_MIN_CHARS} 字以上再来批"
            )
        if scan.characters > ESSAY_MAX_CHARS:
            raise InvalidExamRequestError(
                f"正文 {scan.characters} 字，超过了单次批改上限 {ESSAY_MAX_CHARS} 字，"
                "请分段提交"
            )

        # 截止时间从进门算起，排队等闸门的时间也算在预算里
        deps = self._deps(provider, budget_seconds=ESSAY_LLM_BUDGET)
        with self.llm_gate.acquire():
            result = ESSAY_GRAPH.invoke(
                {
                    "source": source,
                    "topic": topic,
                    "notebook_ids": notebook_ids,
                    "sentences": sentences,
                },
                context=deps,
            )

        graded = result["graded"]
        dimensions = [build_dimension(name, graded[name]) for name in dimension_order()]
        return PaperReview(
            word_count=scan.characters,
            quick_scan=scan,
            dimensions=dimensions,
            annotations=result["annotations"],
            score=weighted_score(dimensions),
            overall_comment=graded["content"].comment,
        )

    # ====================== 答疑论文模式：出题 ======================
    def propose_topic(
        self,
        hint: str | None,
        provider: ModelProvider,
        notebook_ids: list[str] | None = None,
    ) -> EssayTopic:
        """按笔记本材料出一道小论文题，学生可以一键把它设为本次批改的题目。

        检索不到材料也照样出题（出课程通用题），grounded 如实告诉前端——
        这一步失败会让学生连题都拿不到，比题目泛一点更糟。
        """
        deps = self._deps(provider, budget_seconds=ESSAY_TOPIC_LLM_BUDGET)
        with self.llm_gate.acquire():
            result, context = write_topic(deps, hint, _TOPIC_FALLBACK_QUERY, notebook_ids)

        return EssayTopic(
            title=result.title,
            requirements=result.requirements,
            suggested_chars=min(
                ESSAY_TOPIC_MAX_SUGGESTED_CHARS,
                max(ESSAY_TOPIC_MIN_SUGGESTED_CHARS, result.suggested_chars),
            ),
            grounded=bool(context),
        )

    # ====================== 整卷大题的逐句批注 ======================
    def annotate_answer(
        self,
        answer: str,
        question: str,
        rubric: str,
        provider: ModelProvider,
        *,
        grading: AnnotationGradeContext | None = None,
        max_issues: int = 2,
        max_praises: int = 1,
    ) -> list[Annotation]:
        """给一道大题的作答做逐句批注。

        **不进判卷流程**，由前端在学生点开某道题时单独调。判卷本身已经要等
        一轮模型，再给每道大题各发一轮会让等待翻倍；而绝大多数学生只会细看
        自己答得差的那一两道。不点开就一轮都不花。
        """
        source = (answer or "").strip()
        sentences = split_sentences(source)
        scan = quick_scan(source, sentences)
        if scan.characters < ANNOTATE_MIN_ANSWER_CHARS:
            # 太短的答案逐句批注没有意义：整段就一两句，判分的评语已经说清了
            return []

        prompt = build_essay_answer_annotation_prompt(
            numbered_text(sentences),
            question,
            rubric,
            grading=grading,
            max_issues=max_issues,
            max_praises=max_praises,
        )
        # 长度检查在上面、拿闸门之前：短答案根本不用排队，闸门满时也不该被拒成 429
        deps = self._deps(provider, budget_seconds=ANNOTATE_LLM_BUDGET)
        with self.llm_gate.acquire():
            result = ANNOTATE_GRAPH.invoke(
                {
                    "prompt": prompt,
                    "sentences": sentences,
                    "max_issues": max_issues,
                    "max_praises": max_praises,
                    "full_credit": grading is not None and grading.score == grading.points,
                    "limit": ANNOTATE_LLM_TIMEOUT,
                    "floor": ANNOTATE_MIN_ATTEMPT_TIMEOUT,
                },
                context=deps,
            )
        return result["annotations"]

    # ====================== 共用 ======================
    def _deps(
        self,
        provider: ModelProvider,
        *,
        budget_seconds: float | None = None,
        deadline: float | None = None,
    ) -> AgentDeps:
        """一次运行的依赖。传 budget_seconds 就从现在起算，传 deadline 就沿用它。"""
        if deadline is None:
            return AgentDeps.start(
                knowledge_base=self.knowledge_base,
                client_factory=self.client_factory,
                provider=provider,
                budget_seconds=budget_seconds or 0.0,
            )
        return AgentDeps(
            knowledge_base=self.knowledge_base,
            client_factory=self.client_factory,
            provider=provider,
            deadline=deadline,
        )

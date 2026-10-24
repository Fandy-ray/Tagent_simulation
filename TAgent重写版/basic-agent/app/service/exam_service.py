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
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, NamedTuple

from app.config import (
    EXAM_PLAN_POINTS,
    EXAM_CONTEXT_SEPARATOR,
    EXAM_LLM_BUDGET,
    EXAM_LLM_TIMEOUT,
    EXAM_MIN_ATTEMPT_TIMEOUT,
    GRADE_CLOZE_BATCH,
    GRADE_ESSAY_BATCH,
    GRADE_LLM_BUDGET,
    GRADE_LLM_TIMEOUT,
    GRADE_MIN_ATTEMPT_TIMEOUT,
    FLASH_CONTEXT_CHAR_LIMIT,
    FLASH_DECK_MIN_CARDS,
    FLASH_LLM_BUDGET,
    FLASH_LLM_TIMEOUT,
    FLASH_MIN_ATTEMPT_TIMEOUT,
    FLASH_CHOICE_SHARDS,
    FLASH_CLOZE_SHARDS,
    FLASH_SHARD_CARD_RANGE,
    FLASH_SHARD_COUNT,
)
from app.errors.exam_errors import (
    InvalidExamRequestError,
    ModelMismatchError,
    UpstreamLLMError,
)
from app.infra.llm_json import call_json_llm
from app.prompts.exam_prompts import (
    build_exam_plan_prompt,
    build_choice_prompt,
    build_cloze_grade_prompt,
    build_cloze_prompt,
    build_essay_gen_prompt,
    build_essay_grade_prompt,
)
from app.repository.exam_cache import ExamCache, LLMGate, StoredExam
from app.schema.exam_quality import drop_violating
from app.schema.exam import (
    CHOICE_COUNT_RANGE,
    ExamPlan,
    split_plan,
    CLOZE_COUNT_RANGE,
    ESSAY_COUNT_RANGE,
    ChoiceExamDraft,
    ClozeExamDraft,
    EssayExamDraft,
    ExamReview,
    GeneratedExamDraft,
    LLMGradeBatch,
    LLMGradeItem,
    PrivateExam,
    PublicExam,
    QuestionResult,
    SectionScore,
    grade_cloze_locally,
    normalize_draft,
    ratio_to_score,
    to_public,
    validate_grade_batch,
    verdict_from_score,
)
from app.schema.flash import (
    DraftFlashChoice,
    FlashChoiceShardDraft,
    FlashClozeShardDraft,
    PublicFlashDeck,
    dedupe_cards,
    interleave,
    normalize_deck,
    to_public_deck,
)
from app.schema.provider import ModelProvider
from app.util.text import chunked, deal_shards


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


log = logging.getLogger(__name__)


class Stage(NamedTuple):
    """出卷的一段。用具名字段而不是裸元组：这里要按「题数下限」判断要不要
    给这一段派考点，拿位置下标取字段的话，谁重排一下就会静默取错。"""

    build_prompt: Any
    model_cls: Any
    max_tokens: int
    field: str
    minimum: int
    points: list[str] | None = None


def _plan_points(
    client_factory,
    provider: ModelProvider,
    context: str,
    topic: str | None,
    total: int,
    *,
    attempt_timeout: float,
    budget: float,
    started: float,
) -> list[str]:
    """先定考点。失败就返回空清单——规划只是锦上添花，不该让整次出卷失败。

    拿不到规划时三段各自按老样子出题，顶多回到「偶尔撞考点」，
    比直接给用户一个 502 好得多。
    """
    try:
        client = client_factory.get(
            provider, timeout_seconds=int(attempt_timeout), max_retries=0
        ).bind(max_tokens=1200)
        plan = call_json_llm(
            client,
            build_exam_plan_prompt(context, topic, total),
            ExamPlan,
            attempt_timeout=attempt_timeout,
            budget_seconds=budget,
            start_time=started,
        )
        return plan.points
    except Exception as exc:
        log.warning("考点规划失败，三段按老样子各自出题：%s", exc)
        return []


def _require_clean_enough(part: Any, field: str, minimum: int) -> None:
    """删掉违规题之后还得够数，否则让 call_json_llm 重试这一段。

    放在 post_validate 里（而不是拿到结果后在外面判）才能复用它的重试圈；
    放外面就只能要么将就用坏题、要么直接报错。
    """
    kept, _ = drop_violating(getattr(part, field, []) or [])
    if len(kept) < minimum:
        raise ValueError(
            f"{field} 段可用题目只剩 {len(kept)} 道（少于 {minimum} 道）："
            "题目大多指代了学生看不到的材料，或把答案写在了题干里"
        )


def _clean(questions: list, label: str, limit: int | None = None) -> list:
    """删掉违规题，并把删了什么记进日志——出题质量得能被看见。

    limit 是最终题数上限：分段草稿允许模型多给几道当余量（DRAFT_OVERSHOOT），
    删完还多出来的在这里裁掉，最终试卷仍然严格落在 COUNT_RANGE 内。
    """
    kept, dropped = drop_violating(questions or [])
    for question, reasons in dropped:
        log.info(
            "丢弃一道%s题（%s）：%s",
            label,
            "；".join(reasons),
            str(getattr(question, "text", None) or getattr(question, "question", ""))[:60],
        )
    if limit is not None and len(kept) > limit:
        log.info("%s题多出 %d 道（模型给的余量），裁掉", label, len(kept) - limit)
        kept = kept[:limit]
    return kept


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
        """Generate one private exam with the selected provider and return its public projection.

        按题型分三段生成，三段**并发**执行。

        分段的原因：整卷一次性输出上万 token 会顶穿单次调用超时（实测一次生成
        110s、拆两段 100s 都仍被截断，前端拿到 504）；分三段后每段只有 2~3 千
        token，都能在超时内跑完，且某段不合法时只重试那一段。

        并发的依据（各 5 轮 A/B 压测，同材料同模型；**那轮的模型与日期仓库里没记**，
        详见 app/config.py 开头的出处警示）：
            整卷中位耗时  串行 193.7s → 并行 68.4s（-65%）
            跨题型考点重复 串行 3.60  → 并行 0.75
        这里要保留的是**结论**（并发更快、且考点更不重复），不是那两个绝对秒数：
        2026-09-11 在 DeepSeek 上复测，同样走并发，整卷出卷只要 8~9s。
        并行的每一轮都快过串行最快的一轮。原本串行是为了把"前面已考的知识点"
        传给后面几段以避免重复，但数据显示带上这份清单反而重复更多（怀疑模型
        会照着清单把题抄回来），所以连同 covered 一起去掉——它既没帮上忙，
        还逼着三段必须排队。
        """
        operation_started = time.monotonic()
        deadline = operation_started + EXAM_LLM_BUDGET
        # 注意：闸门按"一次出卷"计名额，而一次出卷现在会并发发出 3 次上游调用。
        # 即上游并发峰值 = EXAM_MAX_CONCURRENT_LLM × 3（默认 5×3=15），
        # 不再等于闸门容量本身。调整闸门容量时按这个倍数换算。
        # 闪卡（generate_flash_deck）走的是同一个倍数：FLASH_SHARD_COUNT 也是 3。
        with self.llm_gate.acquire():
            context = self.knowledge_base.sample_exam_context(topic, notebook_ids=notebook_ids)
            stages_spec = (
                Stage(build_cloze_prompt, ClozeExamDraft, 5000, "cloze", CLOZE_COUNT_RANGE[0]),
                Stage(build_choice_prompt, ChoiceExamDraft, 5000, "choice", CHOICE_COUNT_RANGE[0]),
                Stage(build_essay_gen_prompt, EssayExamDraft, 5000, "essay", ESSAY_COUNT_RANGE[0]),
            )

            # 并发下三段共享同一段墙钟，各自都可以用满剩余预算（不再按段均分）。
            # 留出 > cancel_grace(5s) 的余量：call_json_llm 在
            # remaining < attempt_timeout + 5 时会直接判定预算不足并抛 504，
            # 余量不足会导致它一次都不尝试就超时返回（实测 0.9s 即 504）。
            started = time.monotonic()
            budget = max(0.0, deadline - started)
            attempt_timeout = min(
                EXAM_LLM_TIMEOUT, max(EXAM_MIN_ATTEMPT_TIMEOUT, budget - 15.0)
            )

            # 先定考点，再分头出题——但**只给填空和选择**，大题不等规划。
            #
            # 为什么要规划：三段并发时彼此看不见，同一个考点会被问两遍（实测：
            # 填空问「ρ 的计算公式」，选择又问「ρ 的表达式」），事后去重做不到。
            # 这和 config.py 里「把已考清单塞回 prompt 反而更重复」不冲突：那是**串行**
            # 传结果；这里是一次性定好、切成互不相交的几份，各段照旧并发。
            #
            # 为什么大题不等：实测一次出卷的时间线是
            #   规划 1.9s → 填空 5.8s / 选择 5.4s / 大题 8.1s，总 10.3s
            # 大题最慢、决定总耗时，而它又最不需要规划——三道大题靠「计算 / 建模 /
            # 对比各一道」本来就不重复，跨段撞考点出在填空和选择之间。
            # 让大题从 0 秒起步、和规划并行，关键路径就从「规划 + 大题」
            # 变成 max(大题, 规划 + 填空)。
            cloze_spec, choice_spec, essay_spec = stages_spec
            wants = [CLOZE_COUNT_RANGE[1], CHOICE_COUNT_RANGE[1]]

            def run_stage(stage: "Stage"):
                build_prompt, model_cls, max_tokens, field, minimum, points = stage
                client = self.client_factory.get(
                    provider,
                    timeout_seconds=int(attempt_timeout),
                    max_retries=0,
                ).bind(max_tokens=max_tokens)
                return call_json_llm(
                    client,
                    build_prompt(context, topic, [], assigned_points=points),
                    model_cls,
                    attempt_timeout=attempt_timeout,
                    budget_seconds=budget,
                    start_time=started,
                    # 守的是「违规题删掉之后还够不够数」，而不是「有没有违规题」。
                    # 后者会让一段里出一道坏题就整段重来，白等一轮模型；
                    # 实际大多数时候删掉一两道仍然够数，直接用就行。
                    post_validate=lambda value, f=field, m=minimum: _require_clean_enough(
                        value, f, m
                    ),
                )

            def assign(spec: "Stage", points):
                # 某段分到的考点少于它的题数下限时，**不给它清单**，让它自由出题。
                # 规划被要求「宁可少给也不要硬凑」，常常只返回十几个考点；硬按清单
                # 出会出到刚好下限，删掉一两道就跌破下限、重试、最后 502（实测过）。
                return spec._replace(
                    points=points if points and len(points) >= spec.minimum else None
                )

            with ThreadPoolExecutor(max_workers=len(stages_spec)) as pool:
                essay_future = pool.submit(run_stage, essay_spec)  # 不等规划
                # 开关与实测数据见 config.EXAM_PLAN_POINTS
                plan = _plan_points(
                    self.client_factory,
                    provider,
                    context,
                    topic,
                    sum(wants),
                    attempt_timeout=attempt_timeout,
                    budget=budget,
                    started=started,
                ) if EXAM_PLAN_POINTS else []
                cloze_points, choice_points = split_plan(plan, wants) if plan else (None, None)
                cloze_future = pool.submit(run_stage, assign(cloze_spec, cloze_points))
                choice_future = pool.submit(run_stage, assign(choice_spec, choice_points))
                # 任何一段抛错都在这里原样冒出来（504/502/429 的语义保持不变）
                cloze_part = cloze_future.result()
                choice_part = choice_future.result()
                essay_part = essay_future.result()
            draft = GeneratedExamDraft(
                title=cloze_part.title,
                cloze=_clean(cloze_part.cloze, "填空", CLOZE_COUNT_RANGE[1]),
                choice=_clean(choice_part.choice, "选择", CHOICE_COUNT_RANGE[1]),
                essay=_clean(essay_part.essay, "解答", ESSAY_COUNT_RANGE[1]),
            )
            exam = normalize_draft(draft, str(uuid.uuid4()))
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
        """闪卡组：填空 + 选择两类，按材料分片并发，卡组不计分。

        与 generate_exam 的分段是同一条思路再往下切一层。整卷的填空段一次要
        8~10 张、配 4500 字上下文；闪卡把"每次调用的输出量"和"上下文长度"同时
        砍到三分之一——每片 3~4 张配 ~1600 字材料，几片并发。

        分片的材料**互不相同**：sample_exam_context 返回的是若干片段用
        EXAM_CONTEXT_SEPARATOR 拼起来的，这里切回去轮流发牌。这是并发分片不撞
        考点的主要手段——整卷那边实测过"把已考知识点清单塞回 prompt"，结果是
        重复更多，所以不走那条路，改在事后 dedupe_cards 兜底。

        大题不进闪卡：写一段话没法当场判，而"当场知道对错"正是闪卡的全部意义。
        """
        operation_started = time.monotonic()
        deadline = operation_started + FLASH_LLM_BUDGET
        with self.llm_gate.acquire():
            context = self.knowledge_base.sample_exam_context(topic, notebook_ids=notebook_ids)
            shards = deal_shards(
                context,
                FLASH_SHARD_COUNT,
                separator=EXAM_CONTEXT_SEPARATOR,
                char_limit=FLASH_CONTEXT_CHAR_LIMIT,
            )
            if not shards:
                raise InvalidExamRequestError(
                    "所选知识范围里没有可出题的材料，请换一个笔记本或来源"
                )

            cloze_stage = (build_cloze_prompt, FlashClozeShardDraft)
            choice_stage = (build_choice_prompt, FlashChoiceShardDraft)
            stages = [cloze_stage] * FLASH_CLOZE_SHARDS + [choice_stage] * FLASH_CHOICE_SHARDS

            lo, hi = FLASH_SHARD_CARD_RANGE
            if len(shards) < len(stages):
                # 知识库太小、切不出这么多片。宁可少发几次，也不能让两片拿同一份
                # 材料——那等于自找重复。填空优先，还剩位置再给选择留一片。
                keep = len(shards)
                stages = [cloze_stage] if keep == 1 else [cloze_stage] * (keep - 1) + [choice_stage]
                # 每片多出几张，卡组规模才不会跟着分片数一起缩水
                scale = FLASH_SHARD_COUNT / keep
                lo = min(int(round(lo * scale)), 10)
                hi = min(int(round(hi * scale)), 12)

            started = time.monotonic()
            budget = max(0.0, deadline - started)
            # 与 generate_exam 同一套余量算法：call_json_llm 在
            # remaining < attempt_timeout + 5 时直接判预算不足抛 504，
            # 这里的 -15 就是留给它的余量，别减小。
            attempt_timeout = min(
                FLASH_LLM_TIMEOUT, max(FLASH_MIN_ATTEMPT_TIMEOUT, budget - 15.0)
            )

            def run_shard(job):
                (build_prompt, model_cls), shard_context = job
                client = self.client_factory.get(
                    provider,
                    timeout_seconds=int(attempt_timeout),
                    max_retries=0,
                ).bind(max_tokens=2500)
                return call_json_llm(
                    client,
                    build_prompt(
                        shard_context, topic, [], count_range=(lo, hi), deck_mode=True
                    ),
                    model_cls,
                    attempt_timeout=attempt_timeout,
                    budget_seconds=budget,
                    start_time=started,
                )

            jobs = list(zip(stages, shards))
            with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
                # 任何一片抛错都在这里原样冒出来（504/502/429 的语义保持不变）
                parts = list(pool.map(run_shard, jobs))

            cloze_cards = [
                card for part in parts if isinstance(part, FlashClozeShardDraft)
                for card in part.cloze
            ]
            choice_cards = [
                card for part in parts if isinstance(part, FlashChoiceShardDraft)
                for card in part.choice
            ]

            # 闪卡这边**不**像整卷那样用 post_validate 守题量：那会让任何一片出一道
            # 坏卡就整片重来，而闪卡本来就是三片并发、追求快。这里只管删，
            # 删完不够数由下面的 FLASH_DECK_MIN_CARDS 一起兜。
            cloze_cards = _clean(cloze_cards, "闪卡填空")
            choice_cards = _clean(choice_cards, "闪卡选择")

            # 先跨类型去重（同一个考点出成填空还是选择都算重复，填空先到先得），
            # 再交错，顺序才不会被去重打乱。
            kept = dedupe_cards(cloze_cards + choice_cards)
            if len(kept) < FLASH_DECK_MIN_CARDS:
                # 各片撞考点撞得太狠、或坏卡删太多，剩下的卡组不值得刷
                raise UpstreamLLMError("生成的闪卡质量不达标，请重试")

            cards = interleave(
                [card for card in kept if not isinstance(card, DraftFlashChoice)],
                [card for card in kept if isinstance(card, DraftFlashChoice)],
            )
            deck = normalize_deck(cards, parts[0].title, str(uuid.uuid4()))

        # 卡组**不进任何缓存**：答案随 to_public_deck 一起发给了前端，判定也在
        # 浏览器本地做，服务端没有任何一条路径会再读它。真要加回服务端复核，
        # 那时再开一个独立的 ExamCache 实例——绝不能借用 exam_cache，
        # review_exam 会对取出的对象调 all_questions()，卡组掉进去就是类型混淆。
        return to_public_deck(deck)

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

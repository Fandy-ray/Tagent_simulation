"""整卷出题。

    START → sample ─┬─ essay ───────────────────────────────┐
                    └─ objective（子图：plan → cloze ∥ choice）─┴→ assemble → END

按题型分段，各段**并发**。

分段的原因：整卷一次性输出上万 token 会顶穿单次调用超时（实测一次生成 110s、
拆两段 100s 都仍被截断，前端拿到 504）；分段后每段只有 2~3 千 token，都能在
超时内跑完，且某段不合法时只重试那一段。

并发的依据（各 5 轮 A/B 压测，同材料同模型；**那轮的模型与日期仓库里没记**，
详见 app/config.py 开头的出处警示）：
    整卷中位耗时  串行 193.7s → 并行 68.4s（-65%）
    跨题型考点重复 串行 3.60  → 并行 0.75
要保留的是**结论**（并发更快、且考点更不重复），不是那两个绝对秒数：
2026-09-11 在 DeepSeek 上复测，同样走并发，整卷出卷只要 8~9s。原本串行是为了
把「前面已考的知识点」传给后面几段，但数据显示带上这份清单反而重复更多
（怀疑模型会照着清单把题抄回来），所以去掉了——它既没帮上忙，还逼着各段排队。

为什么填空、选择要放进一张子图：LangGraph 按「一轮一轮」推进，同一轮里的任务
全部结束才进下一轮。如果规划和大题同在一轮，填空、选择就得等大题（最慢那段）
做完才能开始。子图在父图里只算一个任务，它内部「规划 → 填空 ∥ 选择」自己推进，
和大题互不等待：关键路径是 max(大题, 规划 + 填空)。

**大题不拆成几次并发出**，试过，是负作用。大题段最慢，拆成「计算 / 建模 /
分析或对比」三次、每次一道，单看大题段确实短了；但放进整条流水线里
（2026-10-24，DeepSeek，交替各跑 8 次）：

                 中位     P90
    一次出三道   8.61s    9.31s
    拆成三次     9.71s   11.61s

时间线显示原因：多出来的两路请求和规划挤在同一时刻，规划从 ~1.9s 拖到
3.8~6.1s，而填空、选择要等规划——关键路径反而变长。上游的并发不是免费的。
（另一个发现：让模型一次出两道「不同类型」的题，5 次里 2 次出了两道只换数字的
计算题。要类型绝对不重，得靠拆开调用；现在一次出三道靠提示词约束。）
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, NamedTuple, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.agent.nodes import json_call
from app.agent.runtime import AgentDeps
from app.config import (
    EXAM_LLM_TIMEOUT,
    EXAM_MIN_ATTEMPT_TIMEOUT,
    EXAM_PLAN_POINTS,
)
from app.prompts.exam_prompts import (
    build_choice_prompt,
    build_cloze_prompt,
    build_essay_gen_prompt,
    build_exam_plan_prompt,
)
from app.schema.exam import (
    CHOICE_COUNT_RANGE,
    CLOZE_COUNT_RANGE,
    ESSAY_COUNT_RANGE,
    ChoiceExamDraft,
    ClozeExamDraft,
    EssayExamDraft,
    ExamPlan,
    GeneratedExamDraft,
    normalize_draft,
    split_plan,
)
from app.schema.exam_quality import clean_questions, require_clean_enough

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


CLOZE_STAGE = Stage(build_cloze_prompt, ClozeExamDraft, 5000, "cloze", CLOZE_COUNT_RANGE[0])
CHOICE_STAGE = Stage(build_choice_prompt, ChoiceExamDraft, 5000, "choice", CHOICE_COUNT_RANGE[0])
ESSAY_STAGE = Stage(build_essay_gen_prompt, EssayExamDraft, 5000, "essay", ESSAY_COUNT_RANGE[0])


def _run_stage(deps: AgentDeps, stage: Stage, context: str, topic: str | None):
    return json_call(
        deps,
        stage.build_prompt(context, topic, [], assigned_points=stage.points),
        stage.model_cls,
        max_tokens=stage.max_tokens,
        limit=EXAM_LLM_TIMEOUT,
        floor=EXAM_MIN_ATTEMPT_TIMEOUT,
        # 守的是「违规题删掉之后还够不够数」，而不是「有没有违规题」。
        # 后者会让一段里出一道坏题就整段重来，白等一轮模型；
        # 实际大多数时候删掉一两道仍然够数，直接用就行。
        post_validate=lambda value: require_clean_enough(value, stage.field, stage.minimum),
    )


def _assign(stage: Stage, points: list[str] | None) -> Stage:
    # 某段分到的考点少于它的题数下限时，**不给它清单**，让它自由出题。
    # 规划被要求「宁可少给也不要硬凑」，常常只返回十几个考点；硬按清单
    # 出会出到刚好下限，删掉一两道就跌破下限、重试、最后 502（实测过）。
    return stage._replace(points=points if points and len(points) >= stage.minimum else None)


# ====================== 子图：规划 → 填空 ∥ 选择 ======================


class ObjectiveState(TypedDict, total=False):
    topic: str | None
    context: str
    plan: list[str]
    cloze_part: Any
    choice_part: Any


class ObjectiveOutput(TypedDict, total=False):
    cloze_part: Any
    choice_part: Any


# 规划只给填空和选择要考点：跨段撞考点出在这两段之间
_WANTS = [CLOZE_COUNT_RANGE[1], CHOICE_COUNT_RANGE[1]]


def _plan(state: ObjectiveState, runtime: Runtime[AgentDeps]) -> dict:
    """先定考点。失败就返回空清单——规划只是锦上添花，不该让整次出卷失败。

    为什么要规划：各段并发时彼此看不见，同一个考点会被问两遍（实测：
    填空问「ρ 的计算公式」，选择又问「ρ 的表达式」），事后去重做不到。
    这和 config.py 里「把已考清单塞回 prompt 反而更重复」不冲突：那是**串行**
    传结果；这里是一次性定好、切成互不相交的几份，各段照旧并发。

    拿不到规划时各段按老样子出题，顶多回到「偶尔撞考点」，比 502 好得多。
    开关与实测数据见 config.EXAM_PLAN_POINTS。
    """
    if not EXAM_PLAN_POINTS:
        return {"plan": []}
    try:
        plan = json_call(
            runtime.context,
            build_exam_plan_prompt(state["context"], state.get("topic"), sum(_WANTS)),
            ExamPlan,
            max_tokens=1200,
            limit=EXAM_LLM_TIMEOUT,
            floor=EXAM_MIN_ATTEMPT_TIMEOUT,
        )
        return {"plan": plan.points}
    except Exception as exc:
        log.warning("考点规划失败，各段按老样子各自出题：%s", exc)
        return {"plan": []}


def _stage_node(stage: Stage, index: int, key: str):
    def node(state: ObjectiveState, runtime: Runtime[AgentDeps]) -> dict:
        plan = state.get("plan") or []
        points = split_plan(plan, _WANTS)[index] if plan else None
        part = _run_stage(runtime.context, _assign(stage, points), state["context"], state.get("topic"))
        return {key: part}

    return node


def build_objective_graph():
    graph = StateGraph(
        ObjectiveState,
        context_schema=AgentDeps,
        input_schema=ObjectiveState,
        output_schema=ObjectiveOutput,
    )
    graph.add_node("plan", _plan)
    graph.add_node("cloze", _stage_node(CLOZE_STAGE, 0, "cloze_part"))
    graph.add_node("choice", _stage_node(CHOICE_STAGE, 1, "choice_part"))
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "cloze")
    graph.add_edge("plan", "choice")
    graph.add_edge("cloze", END)
    graph.add_edge("choice", END)
    return graph.compile()


# ====================== 整卷 ======================


class ExamState(TypedDict, total=False):
    topic: str | None
    notebook_ids: list[str] | None
    context: str
    essay_part: Any
    cloze_part: Any
    choice_part: Any
    exam: Any


def _sample(state: ExamState, runtime: Runtime[AgentDeps]) -> dict:
    return {
        "context": runtime.context.knowledge_base.sample_exam_context(
            state.get("topic"), notebook_ids=state.get("notebook_ids")
        )
    }


def _essay(state: ExamState, runtime: Runtime[AgentDeps]) -> dict:
    # 大题不等规划，从 0 秒起步：三道大题靠「计算 / 建模 / 对比各一道」本来就不重复，
    # 跨段撞考点出在填空和选择之间
    return {"essay_part": _run_stage(runtime.context, ESSAY_STAGE, state["context"], state.get("topic"))}


def _assemble(state: ExamState) -> dict:
    cloze_part, choice_part = state["cloze_part"], state["choice_part"]
    draft = GeneratedExamDraft(
        title=cloze_part.title,
        cloze=clean_questions(cloze_part.cloze, "填空", CLOZE_COUNT_RANGE[1]),
        choice=clean_questions(choice_part.choice, "选择", CHOICE_COUNT_RANGE[1]),
        essay=clean_questions(state["essay_part"].essay, "解答", ESSAY_COUNT_RANGE[1]),
    )
    return {"exam": normalize_draft(draft, str(uuid.uuid4()))}


def build_exam_graph():
    graph = StateGraph(ExamState, context_schema=AgentDeps)
    graph.add_node("sample", _sample)
    graph.add_node("essay", _essay)
    graph.add_node("objective", build_objective_graph())
    graph.add_node("assemble", _assemble)
    graph.add_edge(START, "sample")
    graph.add_edge("sample", "essay")
    graph.add_edge("sample", "objective")
    # 大题和子图在同一轮里，两边都结束才组卷，assemble 只跑一次
    graph.add_edge("essay", "assemble")
    graph.add_edge("objective", "assemble")
    graph.add_edge("assemble", END)
    return graph.compile()


EXAM_GRAPH = build_exam_graph()

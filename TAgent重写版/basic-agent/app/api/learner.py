"""「这是谁」与「记一笔」：controller 往学习记录库里写东西的唯一入口。

**谁**：平台没有登录，前端给每台设备生成一个匿名编号（X-Tagent-Client-Id），连同学生在
设置里填的昵称（X-Tagent-Client-Name，URL 编码——HTTP 头里放不了中文）一起带上来。
没带、或带得不像样，一律当匿名处理，不报错：认不出人只是少一条归属，不该让请求失败。
它只是「同一台设备」的标记，不是身份认证——别拿它做权限判断。

**不记**：前端在「临时对话」里会带 X-Tagent-No-Record: 1——界面答应过学生「消息不会被保存」，
这类请求一条都不往库里写。

**记**：尽力而为。库没开、被占用、磁盘满，都只记一行日志然后照常返回——
答疑和批改是主业，记录是副业，副业出错不能连累主业。
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from functools import wraps
from urllib.parse import unquote

from flask import current_app, g, request

from app.api.deps import get_learning_store
from app.api.response import public_value


log = logging.getLogger(__name__)

CLIENT_ID_HEADER = "X-Tagent-Client-Id"
CLIENT_NAME_HEADER = "X-Tagent-Client-Name"
NO_RECORD_HEADER = "X-Tagent-No-Record"
MAX_NAME_CHARS = 40

_CLIENT_ID = re.compile(r"[A-Za-z0-9_-]{8,64}")


@dataclass(frozen=True)
class Learner:
    id: str | None
    name: str = ""
    # False = 这次请求不留记录（临时对话）
    record: bool = True
    course_id: str = "general"


def current_learner() -> Learner:
    """从请求头里认人。必须在请求上下文里调（流式回答要在生成器开跑之前先取好）。"""
    record = request.headers.get(NO_RECORD_HEADER, "").strip() != "1"
    if current_app.config.get("AUTH_ENABLED") and (account := getattr(g, "account", None)):
        course = getattr(g, "course", None)
        return Learner(
            account["uid"], account.get("name", ""), record,
            course["uid"] if course else "general",
        )
    client_id = request.headers.get(CLIENT_ID_HEADER, "").strip()
    if not _CLIENT_ID.fullmatch(client_id):
        return Learner(None, record=record)
    try:
        name = unquote(request.headers.get(CLIENT_NAME_HEADER, ""), errors="strict")
    except UnicodeDecodeError:
        name = ""
    # 昵称只是展示用：去掉控制字符、压掉首尾空白、截到合理长度
    name = "".join(ch for ch in name if ch.isprintable()).strip()[:MAX_NAME_CHARS]
    return Learner(client_id, name, record)


def _best_effort(write):
    """把一次记录包成「绝不抛异常」：库没开就跳过，出任何错都只记日志。

    连「从结果里取字段」也算在里面——结果的形状万一变了，坏的也只是记录，不是请求。
    """

    @wraps(write)
    def wrapper(learner: Learner, *args, **kwargs) -> None:
        if not learner.record:
            return
        try:
            store = get_learning_store()
            if store is None:
                return
            if learner.id:
                store.touch_student(learner.id, learner.name)
            write(store, learner, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001 —— 记录失败不能连累请求本身
            log.warning("学习记录没存上（%s），请求照常返回：%s", write.__name__, exc)

    return wrapper


@_best_effort
def note_chat(
    store,
    learner: Learner,
    provider,
    *,
    mode: str,
    messages: list[dict[str, str]],
    answer: str,
    finish_reason: str | None,
    notebook_ids: list[str] | None,
    started_at: float,
) -> None:
    """一轮答疑。只记这一轮的提问（最后一条 user 消息）与回答，不把整段历史每轮重存一遍。"""
    question = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    store.record_chat(
        student_id=learner.id,
        course_id=learner.course_id,
        mode=mode,
        model=provider.served_model_id,
        question=question,
        answer=answer,
        finish_reason=finish_reason,
        notebook_ids=notebook_ids,
        duration_ms=int((time.monotonic() - started_at) * 1000),
    )


@_best_effort
def note_essay_review(store, learner: Learner, provider, *, topic: str | None, text: str, review) -> None:
    store.record_essay_review(
        student_id=learner.id,
        course_id=learner.course_id,
        model=provider.served_model_id,
        topic=topic,
        text=text,
        review=public_value(review),
    )


@_best_effort
def note_exam_generated(store, learner: Learner, provider, *, topic: str | None, exam) -> None:
    paper = public_value(exam)
    store.record_exam_generated(
        student_id=learner.id,
        course_id=learner.course_id,
        exam_id=paper["exam_id"],
        model=provider.served_model_id,
        title=paper.get("title", ""),
        topic=topic,
        total_points=paper.get("total_points"),
        paper=paper,
    )


@_best_effort
def note_exam_reviewed(store, learner: Learner, provider, *, exam_id: str, answers: dict, review) -> None:
    store.record_exam_reviewed(
        student_id=learner.id,
        course_id=learner.course_id,
        exam_id=exam_id,
        model=provider.served_model_id,
        answers=answers,
        review=public_value(review),
    )

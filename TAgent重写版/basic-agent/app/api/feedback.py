"""学生对回答的「有帮助 / 没有帮助」。

以前这两个按钮只改页面里的一个变量，刷新就没了，老师也看不到。现在每点一次记一条：
同一条回答改评价是覆盖，再点一次同一个按钮是撤销（删掉）。老师在管理后台「评测 · 反馈」里看，
「评测 · 排行榜」按模型统计赞踩比。

和别的记录一样认人靠 X-Tagent-Client-Id（只是设备标记，不是身份认证）；临时对话带
X-Tagent-No-Record: 1，这里一条都不写——界面答应过「消息不会被保存」。
没带设备标记的也不记：分不清是谁点的，就没法「改评价覆盖、再点撤销」（库里的唯一约束对空值不起作用，
改一次评价会多出一条，撤销会把别的匿名用户同编号的那条也删掉）。
"""

from __future__ import annotations

import re

from flask import Blueprint, jsonify

from app.api.deps import get_learning_store
from app.api.learner import current_learner
from app.api.validators import json_body
from app.errors.api_errors import AgentAPIError


blueprint = Blueprint("feedback", __name__, url_prefix="/learner")

# 前端消息编号形如 assistant-1792767943583，留点余量
_MESSAGE_KEY = re.compile(r"[A-Za-z0-9_.:-]{1,100}")
_RATINGS = {"up": 1, "down": -1, None: 0}
_MODES = ("qa", "paper", "chat")
# 只为老师能看懂是哪一问、哪一答：存头上一段就够，不必把整篇论文任务塞进库
MAX_EXCERPT_CHARS = 4000
# 和登记模型 ID 的上限一样（app/schema/provider.py 的 PROVIDER_ID_PATTERN）：再短的话，长 ID 的模型点赞会被拒
MAX_MODEL_CHARS = 128


@blueprint.post("/feedback")
def record_feedback():
    data = json_body()
    message_key = data.get("message_id")
    if not isinstance(message_key, str) or not _MESSAGE_KEY.fullmatch(message_key):
        raise AgentAPIError("message_id 不对。", 400, "validation_error")
    rating = data.get("rating")
    # 先看类型：列表、对象拿去字典里查会直接抛错，成了 500
    if not (rating is None or isinstance(rating, str)) or rating not in _RATINGS:
        raise AgentAPIError("rating 只能是 up、down 或 null（撤销）。", 400, "validation_error")
    mode = data.get("mode") or "qa"
    if mode not in _MODES:
        raise AgentAPIError(f"mode 只能是 {', '.join(_MODES)}。", 400, "invalid_mode")
    model = data.get("model")
    if not isinstance(model, str) or not model.strip() or len(model) > MAX_MODEL_CHARS:
        raise AgentAPIError("model 不对。", 400, "validation_error")
    question, answer = (_excerpt(data, field) for field in ("question", "answer"))

    learner = current_learner()
    if not learner.record or not learner.id:
        return jsonify({"recorded": False})
    store = get_learning_store()
    if store is None:
        raise AgentAPIError(
            "学习记录库没有启用（LEARNING_STORE=0，或启动时没能打开数据库文件）。",
            503,
            "learning_store_unavailable",
        )
    store.touch_student(learner.id, learner.name)
    store.record_feedback(
        student_id=learner.id,
        message_key=message_key,
        model=model.strip(),
        mode=mode,
        rating=_RATINGS[rating],
        question=question,
        answer=answer,
    )
    return jsonify({"recorded": True})


def _excerpt(data: dict, field: str) -> str:
    value = data.get(field, "")
    if not isinstance(value, str):
        raise AgentAPIError(f"{field} 必须是文字。", 400, "validation_error")
    return value.strip()[:MAX_EXCERPT_CHARS]

"""RAG 对话的 prompt 组装。"""

from __future__ import annotations

from app.errors.api_errors import AgentAPIError


_QA_SYSTEM = (
    "You are a teaching assistant. Ground the answer in the reference below. "
    "Preserve useful Markdown, formulas, tables, and image links. If the reference is insufficient, say so."
)

# 论文辅助模式。前端的任务卡已经把每一步要写什么说得很细（大纲/摘要/方法……），
# 这里只立身份和底线：可以起草章节，但不编数据、不编文献、不一次代写整篇。
_PAPER_SYSTEM = (
    "你是《系统建模与仿真》课程的论文写作助教，帮助学生一步步推进课程论文。"
    "依据下面的参考材料回答，可以按要求给出结构、方法、实验设计和修改建议，也可以起草章节草稿，"
    "但不要一次代写整篇论文。不要编造实验数据、数值结果或参考文献：学生没提供的数据标成待补。"
    "参考材料不足以支撑时直接说明，不要硬凑。保留有用的 Markdown、公式、表格和图片链接。"
)

SYSTEM_PROMPTS = {"qa": _QA_SYSTEM, "paper": _PAPER_SYSTEM}


def build_prompt_messages(messages: list[dict[str, str]], context: str, mode: str = "qa"):
    if mode == "chat":
        # Playground：不检索、不加平台的身份和底线，学生自己写的系统提示就是全部——那一页就是用来试模型本身的
        return list(messages)
    system = {
        "role": "system",
        "content": f"{SYSTEM_PROMPTS[mode]}\n\nReference:\n{context}",
    }
    return [system, *messages]
def last_user_message(messages: list[dict[str, str]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return message["content"]
    raise AgentAPIError("At least one user message is required.", 400, "invalid_messages")

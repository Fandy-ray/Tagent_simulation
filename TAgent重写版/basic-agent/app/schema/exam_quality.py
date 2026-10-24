"""出题质量的事后过滤。

prompt 里写了约束不等于模型会守。实测填「排队论」出来的卷子里大量是
「根据材料，主路常数 m 值为多少」「如图 4.9 所示」这类题——学生看不到材料、
更看不到图，这种题等于白出。闪卡那边还出现过把答案直接写在题干里的 F1。

所以生成之后再过一道闸：**违规的删掉，剩下的不够数才重试那一段**。
先删后重试而不是直接重试，是因为重试要多等一轮模型；大多数情况下一段里
只有一两道违规，删掉仍然够数。

纯逻辑、不碰网络，可离线单测。
"""

from __future__ import annotations

import re
from typing import Any, Iterable


# 指代参考材料的说法。学生手里只有题干，这些词一出现题就没法做。
#
# 「图」「表」必须跟编号或「所示/中」才算——否则「流程图」「列表」会被误伤。
_REFERS_TO_MATERIAL = re.compile(
    r"材料中|材料里|根据材料|依据材料|上文|前文|上述材料|本文中|该文中|原文中"
    r"|如图|见图|图\s*\d+(?:[.\-]\d+)*\s*(?:所示|中)"
    r"|如表|见表|表\s*\d+(?:[.\-]\d+)*\s*(?:所示|中)"
    r"|文献\s*[\[【]\s*\d+"
)

# 挖空占位符；查「答案是否出现在题干」时要先把它去掉
_BLANK = "____"

# 答案要多长才值得按「泄漏」判。太短的词在题干里正常出现太常见，一判就误伤，
# 而误删好题会让题数跌破下限、整段重试、最后 502——比漏判一道坏题贵得多。
#
# 两档门槛都是实测逼出来的：
#
# - 中文 3 字：题干「若到达率 λ **增大**，则平均等待时间会 ____」，答案也是
#   「增大」——那个「增大」在**前提从句**里，题本身完全合格却被删。
#   两字词（增大/增加/减小/变长）几乎都栽在这上面。
#
# - 符号 6 字符：题干「均值为 $1/\mu$」让答案「mu」「$\mu$」命中了。那是记号在
#   题干里正常出现，不是把答案告诉学生。而真正的公式泄漏（题干直接写出
#   $\frac{\lambda}{\mu(\mu-\lambda)}$）都远长于 6 个字符，照样抓得住。
#
# 代价是 FIFO 这种四字符缩写被写进题干时会漏判。两害相权，宁可漏判。
_MIN_LEAK_LENGTH_CJK = 3
_MIN_LEAK_LENGTH_SYMBOL = 6

_CJK = re.compile(r"[\u4e00-\u9fa5]")


def _comparable(text: str) -> str:
    return re.sub(r"\s+", "", str(text))


def _min_leak_length(answer: str) -> int:
    return _MIN_LEAK_LENGTH_CJK if _CJK.search(answer) else _MIN_LEAK_LENGTH_SYMBOL


def _visible_text(question: Any) -> str:
    """学生实际看得到的部分。参考答案、评分要点、解析都不算。"""
    parts: list[str] = []
    for field in ("cue", "text", "question"):
        value = getattr(question, field, None)
        if isinstance(value, str):
            parts.append(value)
    options = getattr(question, "options", None)
    if isinstance(options, list):
        parts.extend(str(option) for option in options)
    return "\n".join(parts)


def _leaked_answer(question: Any) -> str | None:
    """题干里是否已经写出了答案。返回泄漏的那个写法，没有则 None。"""
    stem = _visible_text(question).replace(_BLANK, "")
    normalized = _comparable(stem)

    # 填空：accept 是等价答案的穷举，任何一条出现在题干里都算泄漏
    accept = getattr(question, "accept", None)
    if isinstance(accept, list):
        for candidate in accept:
            text = _comparable(candidate)
            if len(text) >= _min_leak_length(text) and text in normalized:
                return str(candidate)

    # 选择：正确选项的文字出现在题干里（选项本身不算，它本来就要显示）
    options = getattr(question, "options", None)
    index = getattr(question, "correct_index", None)
    if isinstance(options, list) and isinstance(index, int) and 0 <= index < len(options):
        answer = _comparable(options[index])
        question_text = _comparable(getattr(question, "question", "") or "")
        if len(answer) >= _min_leak_length(answer) and answer in question_text:
            return str(options[index])

    return None


def violations(question: Any) -> list[str]:
    """这道题违反了哪些约束。空列表 = 合格。"""
    found: list[str] = []

    match = _REFERS_TO_MATERIAL.search(_visible_text(question))
    if match:
        found.append(f"指代了学生看不到的材料（「{match.group(0)}」）")

    leaked = _leaked_answer(question)
    if leaked:
        found.append(f"答案写在题干里（「{leaked}」）")

    return found


def drop_violating(questions: Iterable[Any]) -> tuple[list[Any], list[tuple[Any, list[str]]]]:
    """分成「留下的」和「删掉的（附原因）」两堆。

    调用方据此决定：剩下的够数就直接用，不够才重试这一段。
    """
    kept: list[Any] = []
    dropped: list[tuple[Any, list[str]]] = []
    for question in questions:
        reasons = violations(question)
        if reasons:
            dropped.append((question, reasons))
        else:
            kept.append(question)
    return kept, dropped

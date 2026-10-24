"""把指代型追问补成能检索的问题。

答疑子图的第一步「理解问题」。要解决的是这个实测现象：

    上一问：什么是 M/M/1 排队模型
    追  问：那它的前提呢
    检索到：供应链 / COVID-19 疫情 / NSGA-II……（「前提」撞上了「Pareto 前沿」）

生成那一步拿到了正确的历史，所以答得出来；但**检索**用的是追问原文，
而「那它的前提呢」里没有任何可检索的实词，于是材料全错。
答得对只是因为模型自己知道 M/M/1，一旦问到教材里才有的内容就会露馅。

这里**不调模型**：补一次问题要多一个来回，而这一层的目标是「除模型之外
不可感知」。把上一问拼进检索词就够了——检索本来就是模糊匹配，多几个实词
只会更准。真要做语义改写，那是另一个带成本的决定。

纯逻辑、不依赖任何层，可离线单测。
"""

from __future__ import annotations

import re


# 指代词 / 承接词。命中说明这句话离开上文就不完整。
#
# **不要**把「怎么/如何/为什么」列进来：「Little 公式怎么推导」是完全自足的问句，
# 列进来会把一大批正常提问误判成追问，白白把上一问拼进检索词。
# 单独成句的「为什么」仍然会被下面「实词太少」那条兜住。
#
# 「吗」也不列：「M/M/1 稳定吗」是自足的；「呢」才是承接味道重的那个。
_DEIXIS = re.compile(
    r"它|他|她|它们|这个|这些|那个|那些|此|该|上述|前者|后者"
    r"|还有|另外"
    r"|呢[？?]?$"
)

# 光靠「字数少」判追问会误伤：中文实词密度高，「什么是排队论」去掉虚词只剩
# 5 个字，「泊松分布」只有 4 个，它们都是完全自足的问题。误判成追问会把上一问
# 拼进检索词——先问 M/M/1 再问「什么是仿真」，就会拿 M/M/1 的材料去答仿真，
# 比不补上文还糟。
#
# 所以改成：常见的「光杆追问」直接列出来，字数只做兜底（≤2 字才算）。
# 两种误判里，误判成自足顶多是回到改动前的行为，不会倒退。
_BARE_FOLLOWUP = frozenset(
    {
        "为什么", "怎么说", "具体点", "具体些", "说详细点", "详细说说", "展开讲讲",
        "举个例子", "举例说明", "继续", "接着说", "然后呢", "再多说点", "简单点",
    }
)

# 去掉这些之后还剩多少实词，用来判断这句话自身有没有检索价值
_FILLER = re.compile(
    r"[那这](?:么)?|请|问|一下|的|了|呢|吗|啊|吧|和|与|是|有|在|？|\?|，|,|。|、|\s"
)

# 只兜底真正的碎片（一两个字），别再拿它去判整句
_MIN_STANDALONE_CHARS = 3

# 补进检索词的上文最多取这么长，免得把整段回答塞进检索
_CONTEXT_CHARS = 60


def looks_like_followup(question: str) -> bool:
    """这句话离开上文还能不能单独检索。"""
    text = (question or "").strip()
    if not text:
        return False
    if text.rstrip("？?。.！!") in _BARE_FOLLOWUP:
        return True
    if _DEIXIS.search(text):
        return True
    return len(_FILLER.sub("", text)) < _MIN_STANDALONE_CHARS


def resolve_query(messages: list[dict[str, str]], question: str) -> str:
    """给检索用的问题。不是追问就原样返回。

    追问就把**上一个用户问题**拼在前面。拼用户问题而不是助手回答：
    回答动辄上千字，拼进去会把检索词冲淡，而上一问通常正好是那个话题词。
    """
    text = (question or "").strip()
    if not text or not looks_like_followup(text):
        return text

    previous = _previous_user_question(messages, text)
    if not previous:
        return text
    return f"{previous[:_CONTEXT_CHARS]} {text}"


def _previous_user_question(messages: list[dict[str, str]], current: str) -> str:
    """倒着找上一条**不是**当前这问、且本身能独立检索的用户消息。

    连着追问好几句时（「那它的前提呢」→「那第二条呢」），要一直回溯到
    真正带话题词的那一问，否则拼上去的还是一句指代。
    """
    for message in reversed(messages or []):
        if message.get("role") != "user":
            continue
        content = (message.get("content") or "").strip()
        if not content or content == current:
            continue
        if looks_like_followup(content):
            continue
        return content
    return ""

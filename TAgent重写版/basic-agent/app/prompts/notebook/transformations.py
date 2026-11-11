"""内置变换（原版装好时自带的 6 个，现网一个都没改过），改成中文提示词、只读。

原版的「变换」页面（增删改提示词模板、试验场、默认提示词）砍掉了；来源详情里「生成洞察」
和添加来源时勾选的变换，都从这张表里选。
"""

from __future__ import annotations

_COMMON = (
    "\n\n要求：用与原文相同的语言作答（原文是中文就用中文）；只依据原文，不要编造；"
    "直接输出结果，用 Markdown 排版，不要寒暄。"
)

BUILTIN_TRANSFORMATIONS: list[dict] = [
    {
        "id": "transformation:analyze_paper",
        "name": "Analyze Paper",
        "title": "论文分析",
        "description": "分析一篇技术或学术论文",
        "apply_default": False,
        "prompt": "你是一位严谨的学术审稿人。请分析下面的论文：研究问题、方法、主要结论、创新点、局限与可改进之处，"
        "并给出三条值得追问的问题。" + _COMMON,
    },
    {
        "id": "transformation:dense_summary",
        "name": "Dense Summary",
        "title": "详细摘要",
        "description": "写一份信息密度高、覆盖全面的摘要",
        "apply_default": True,
        "prompt": "请为下面的内容写一份详细摘要：覆盖所有重要观点、论据、数据和结论，按原文结构分段，"
        "保留关键术语。" + _COMMON,
    },
    {
        "id": "transformation:key_insights",
        "name": "Key Insights",
        "title": "关键要点",
        "description": "提炼重要观点和可执行的建议",
        "apply_default": False,
        "prompt": "请从下面的内容中提炼 5~10 条最重要的要点，每条一两句话；如有可以付诸行动的建议，单独列出。" + _COMMON,
    },
    {
        "id": "transformation:reflections",
        "name": "Reflections",
        "title": "思考题",
        "description": "根据内容出几道帮助深入理解的思考题",
        "apply_default": False,
        "prompt": "请根据下面的内容出 5 道思考题，帮助读者检验理解、联系实际、发现疑点；每题后附一句提示。" + _COMMON,
    },
    {
        "id": "transformation:simple_summary",
        "name": "Simple Summary",
        "title": "简要摘要",
        "description": "用几句话概括内容",
        "apply_default": False,
        "prompt": "请用三到五句话概括下面内容的核心意思。" + _COMMON,
    },
    {
        "id": "transformation:table_of_contents",
        "name": "Table of Contents",
        "title": "内容目录",
        "description": "列出内容涉及的各个主题",
        "apply_default": False,
        "prompt": "请按原文顺序列出下面内容涉及的主题和小节，形成一份带层级的目录，每项后附一句说明。" + _COMMON,
    },
]


def transformation_messages(prompt: str, text: str) -> list[dict]:
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"# 内容\n\n{text}"},
    ]

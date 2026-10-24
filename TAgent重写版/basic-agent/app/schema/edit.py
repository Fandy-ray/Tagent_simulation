"""文件编辑的数据模型：模型给修改建议，用户逐条采纳。

这一轮只铺路（后端 + 单测），还没接上传、存储和界面，见 app/agent/graphs/edit.py。

一条修改建议 = 一条批注（落在哪一句、为什么改）+ 改成什么。直接沿用逐句批注那套：
**模型只回句子编号**，原文区间由 split_sentences 切句时存好，这里查表——
和批注一样零匹配、零猜测。改的粒度是整句：模型给出这一句改写后的完整句子。

本模块是纯逻辑，不碰网络，可离线单测。
"""

from __future__ import annotations

from typing import List, Literal, Sequence, Set

from pydantic import Field

from app.schema.essay import Annotation
from app.schema.exam import StrictModel
from app.util.text import Sentence


# issue：这句有错，必须改；suggestion：没错，但可以写得更好
EditKind = Literal["issue", "suggestion"]


# ====================== LLM 输出（不可信，严格校验） ======================
class LLMEdit(StrictModel):
    sentence_id: str = Field(min_length=1)
    kind: EditKind
    replacement: str = Field(min_length=1)  # 这一句改写后的完整句子
    comment: str = Field(min_length=1)      # 为什么这么改


class LLMEditBatch(StrictModel):
    items: List[LLMEdit] = Field(default_factory=list)


def validate_edits(
    batch: LLMEditBatch,
    sentences: Sequence[Sentence],
    *,
    max_edits: int,
) -> None:
    """编号必须是已知句子、一句只改一次、不超定额、改了等于没改的不算。

    放进 call_json_llm 的 post_validate 里用：不合格就重试一次，而不是直接报错。
    """
    original = {sentence.id: sentence.text for sentence in sentences}
    seen: Set[str] = set()
    for item in batch.items:
        if item.sentence_id not in original:
            raise ValueError(f"修改建议指向了不存在的句子：{item.sentence_id}")
        if item.sentence_id in seen:
            raise ValueError(f"同一句给了多条修改建议：{item.sentence_id}")
        seen.add(item.sentence_id)
        if item.replacement.strip() == original[item.sentence_id].strip():
            raise ValueError(f"{item.sentence_id} 的「修改」和原句一模一样")
    if len(batch.items) > max_edits:
        raise ValueError(f"修改建议 {len(batch.items)} 条，超过定额 {max_edits}")


# ====================== 对外形状（带原文区间） ======================
class EditSuggestion(Annotation):
    """一条修改建议。start/end/text 是**原句**在原文里的区间，comment 是修改理由。"""

    kind: EditKind
    replacement: str


def attach_edit_spans(batch: LLMEditBatch, sentences: Sequence[Sentence]) -> List[EditSuggestion]:
    """把模型回的编号换成带原文区间的修改建议，按原文顺序排好。"""
    index = {sentence.id: sentence for sentence in sentences}
    suggestions = [
        EditSuggestion(
            sentence_id=item.sentence_id,
            kind=item.kind,
            comment=item.comment,
            replacement=item.replacement,
            start=index[item.sentence_id].start,
            end=index[item.sentence_id].end,
            text=index[item.sentence_id].text,
        )
        for item in batch.items
        if item.sentence_id in index
    ]
    return sorted(suggestions, key=lambda s: s.start)


def apply_edits(source: str, accepted: Sequence[EditSuggestion]) -> str:
    """把用户采纳的几条建议应用回原文。

    **从后往前**替换：先改后面的，前面的下标才不会被挪位。用户采纳的顺序随意，
    这里自己排。两种情况直接拒绝，不去猜：

    - 区间对不上原文（原文在给建议之后又被改过）：照旧下标替换会改错地方；
    - 两条建议的区间重叠：先应用哪条都会让另一条落空。
    """
    ordered = sorted(accepted, key=lambda s: s.start)
    for suggestion in ordered:
        if not (0 <= suggestion.start <= suggestion.end <= len(source)):
            raise ValueError(f"{suggestion.sentence_id} 的区间超出了原文")
        if source[suggestion.start : suggestion.end] != suggestion.text:
            raise ValueError(f"{suggestion.sentence_id} 处的原文已经变了，这条建议过期了")
    for before, after in zip(ordered, ordered[1:]):
        if after.start < before.end:
            raise ValueError(f"{before.sentence_id} 和 {after.sentence_id} 的修改范围重叠")

    edited = source
    for suggestion in reversed(ordered):
        edited = edited[: suggestion.start] + suggestion.replacement + edited[suggestion.end :]
    return edited

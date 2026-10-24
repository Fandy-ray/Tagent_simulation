"""闪卡数据模型与纯逻辑：LLM 分片草稿 → 去重 → 私有卡组 → 公开卡组。

闪卡是整卷里的填空 + 选择两类单独拎出来（大题不进闪卡：写一段话没法当场判），
所以**结构完全复用 exam.py**：
`_ClozeBase` 的三条校验（text 恰好一个 ____、accept 非空、match_mode 二选一）
和两个归一化函数都是白拿的，不要在这里重写一份。

与整卷的两处关键差异：

1. **不计分。** 卡片一律 points=1，没有分值归一那一步（整卷的 normalize_draft
   要三段齐全才能算，闪卡没有这个约束，所以某一片少给一张也不用整次重来）。
2. **公开卡组带答案。** 见 to_public_deck 的注释——这是故意的，且只在这条
   路径上成立，exam.py 的 to_public() 一个字都没改。

本文件不依赖 LLM/网络，全部可离线单测。
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field, model_validator

# _ClozeBase / _normalize_* 带下划线，是 exam.py 对"模块外部"的提示；
# flash.py 是同包里刻意共享这套契约的兄弟模块，复用它们正是为了不让
# 填空的判定规则出现第二份实现。
from app.schema.exam import (
    ChoiceQuestion,
    ClozeQuestion,
    StrictModel,
    _ChoiceBase,
    _ClozeBase,
    _normalize_exact_answer,
    _normalize_text_answer,
)


FLASH_DEFAULT_TITLE = "知识点闪卡"


def normalized_accept(accept: List[str], match_mode: str) -> List[str]:
    """按 match_mode 预先归一参考答案，随卡片下发给前端。

    前端只需要用同样的规则归一**用户输入**那一侧，参考答案这一侧永远以
    服务端为准，少一半漂移的机会。
    """
    normalize = _normalize_exact_answer if match_mode == "exact" else _normalize_text_answer
    seen: set[str] = set()
    result: List[str] = []
    for item in accept:
        value = normalize(item)
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


# ====================== 草稿（LLM 分片输出） ======================
class DraftFlashCard(_ClozeBase):
    id: Optional[str] = None      # LLM 若输出 id 一律忽略，后端重新编号
    points: Optional[float] = None  # 沿用填空 prompt 时模型可能照给，收下但不用


class DraftFlashChoice(_ChoiceBase):
    id: Optional[str] = None
    points: Optional[float] = None


class FlashClozeShardDraft(StrictModel):
    """填空片的输出。**故意不校验张数**：某片少给一张不该让整次出卷失败，
    去重之后统一按 FLASH_DECK_MIN_CARDS 兜底（在 service 层判定）。"""

    title: str = FLASH_DEFAULT_TITLE
    cloze: List[DraftFlashCard] = Field(min_length=1)


class FlashChoiceShardDraft(StrictModel):
    """选择片的输出。同样不校验张数。"""

    title: str = FLASH_DEFAULT_TITLE
    choice: List[DraftFlashChoice] = Field(min_length=1)


DraftFlashItem = Union[DraftFlashCard, DraftFlashChoice]


# ====================== 私有卡组 ======================
class FlashClozeCard(ClozeQuestion):
    """填空闪卡，分值恒为 1。

    直接继承 ClozeQuestion 而不是另起一套，是为了让 grade_cloze_locally /
    cloze_matches 这些现成的判定逻辑对闪卡也直接可用。
    """

    points: int = 1


class FlashChoiceCard(ChoiceQuestion):
    """选择闪卡，分值恒为 1。点一下选项就能判，是闪卡里摩擦最小的一类。"""

    points: int = 1


FlashItem = Annotated[
    Union[FlashClozeCard, FlashChoiceCard], Field(discriminator="type")
]


class PrivateFlashDeck(StrictModel):
    deck_id: str
    title: str
    cards: List[FlashItem] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self):
        ids = [card.id for card in self.cards]
        if len(ids) != len(set(ids)):
            raise ValueError("闪卡 ID 重复")
        return self


# ====================== 公开卡组（**故意包含答案**） ======================
class PublicFlashCard(StrictModel):
    id: str
    type: Literal["cloze"] = "cloze"
    cue: str
    text: str
    accept: List[str]
    accept_normalized: List[str]
    match_mode: Literal["text", "exact"]
    explanation: str = ""


class PublicFlashChoiceCard(StrictModel):
    id: str
    type: Literal["choice"] = "choice"
    question: str
    options: List[str]
    correct_index: int
    explanation: str = ""


PublicFlashItem = Annotated[
    Union[PublicFlashCard, PublicFlashChoiceCard], Field(discriminator="type")
]


class PublicFlashDeck(StrictModel):
    deck_id: str
    title: str
    total_cards: int
    cards: List[PublicFlashItem]


def to_public_deck(deck: PrivateFlashDeck) -> PublicFlashDeck:
    """闪卡的公开投影 —— 与 exam.to_public() 相反，这里**故意下发答案**。

    翻卡这个动作本身就是"把答案给用户看"，选择卡点一下就要当场给对错，判定也都在
    浏览器里做；答案迟早要到客户端，为此多加一次往返只会让"零等待"这个卖点落空。
    闪卡是复习工具，没有分数完整性可言，所以这个取舍是划算的。

    **边界**：这条路径只服务闪卡。整卷的 to_public() 不受影响，也不要给它
    加任何带答案的投影——那边的分数是要计入判卷结果的。
    """
    cards: List[object] = []
    for card in deck.cards:
        if isinstance(card, FlashChoiceCard):
            cards.append(
                PublicFlashChoiceCard(
                    id=card.id,
                    question=card.question,
                    options=list(card.options),
                    correct_index=card.correct_index,
                    explanation=card.explanation,
                )
            )
        else:
            cards.append(
                PublicFlashCard(
                    id=card.id,
                    cue=card.cue,
                    text=card.text,
                    accept=list(card.accept),
                    accept_normalized=normalized_accept(card.accept, card.match_mode),
                    match_mode=card.match_mode,
                    explanation=card.explanation,
                )
            )

    return PublicFlashDeck(
        deck_id=deck.deck_id,
        title=deck.title,
        total_cards=len(cards),
        cards=cards,
    )


# ====================== 去重与编号 ======================
def _dedupe_key(card: DraftFlashItem) -> tuple[str, str]:
    """同一考点的判定依据。

    填空看归一后的首选答案与挖空句；选择看题干与正确选项的文本——同一个知识点
    换个问法仍然算重复，这正是三片并发最容易撞出来的东西。

    按题型基类判断，整卷的草稿题（DraftClozeQuestion / DraftChoiceQuestion）也能用：
    整卷的填空、选择也是分几路同时出的（app/agent/graphs/exam.py）。
    """
    if isinstance(card, _ChoiceBase):
        correct = ""
        if 0 <= card.correct_index < len(card.options):
            correct = _normalize_text_answer(card.options[card.correct_index])
        return correct, _normalize_text_answer(card.question)

    answer = _normalize_text_answer(card.accept[0]) if card.accept else ""
    return answer, _normalize_text_answer(card.text)


def dedupe_cards(cards: List[DraftFlashItem]) -> List[DraftFlashItem]:
    """按考点去重，保留先到的一张。

    三片并发看不到彼此，撞考点在所难免（整卷那边验证过：把"已考清单"塞回
    prompt 反而更重复，所以只能在这里事后收拾）。填空与选择放在同一个
    命名空间里比对——「λ/μ 叫什么」出成填空还是选择，都是同一个考点。
    """
    seen_answers: set[str] = set()
    seen_stems: set[str] = set()
    kept: List[DraftFlashItem] = []

    for card in cards:
        answer, stem = _dedupe_key(card)
        if (answer and answer in seen_answers) or (stem and stem in seen_stems):
            continue
        if answer:
            seen_answers.add(answer)
        if stem:
            seen_stems.add(stem)
        kept.append(card)

    return kept


def interleave(cloze: List, choice: List) -> List:
    """把选择卡均匀铺进填空卡之间，别让一组卡前半段全填空、后半段全选择。"""
    if not choice:
        return list(cloze)
    if not cloze:
        return list(choice)

    step = len(cloze) / len(choice)
    merged: List = []
    taken = 0
    since = 0.0

    for item in cloze:
        merged.append(item)
        since += 1
        if taken < len(choice) and since >= step:
            merged.append(choice[taken])
            taken += 1
            since = 0.0

    merged.extend(choice[taken:])
    return merged


def normalize_deck(cards: List[DraftFlashItem], title: str, deck_id: str) -> PrivateFlashDeck:
    """草稿 → 私有卡组：后端编号 F1..Fn，分值恒为 1（题号不信 LLM 输出）。"""
    built: List[object] = []
    for index, card in enumerate(cards):
        if isinstance(card, DraftFlashChoice):
            built.append(
                FlashChoiceCard(
                    id=f"F{index + 1}",
                    question=card.question,
                    options=card.options,
                    correct_index=card.correct_index,
                    explanation=card.explanation,
                    points=1,
                )
            )
        else:
            built.append(
                FlashClozeCard(
                    id=f"F{index + 1}",
                    cue=card.cue,
                    text=card.text,
                    accept=card.accept,
                    match_mode=card.match_mode,
                    explanation=card.explanation,
                    points=1,
                )
            )

    return PrivateFlashDeck(
        deck_id=deck_id,
        title=(title or "").strip() or FLASH_DEFAULT_TITLE,
        cards=built,
    )

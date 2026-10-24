"""闪卡出卡链路：分片、材料互不相同、去重兜底、缓存隔离、路由接线。"""

import asyncio
import json
import re
import time
import types

import pytest

from app.config import EXAM_CONTEXT_SEPARATOR, FLASH_SHARD_COUNT
from app.errors.exam_errors import InvalidExamRequestError, UpstreamLLMError
from app.factory import create_app
from app.repository.exam_cache import ExamCache, LLMGate
from app.schema.exam import (
    CHOICE_COUNT_RANGE,
    CLOZE_COUNT_RANGE,
    ESSAY_COUNT_RANGE,
    DraftChoiceQuestion,
    DraftClozeQuestion,
    DraftEssayQuestion,
    GeneratedExamDraft,
    normalize_draft,
)
from app.schema.provider import ModelProvider
from app.service.exam_service import ExamService
from tests.conftest import FakeRegistry


TEST_PROVIDER = ModelProvider(
    name="Test provider",
    served_model_id="test-provider",
    base_url="https://example.invalid/v1",
    upstream_model="test-upstream",
    auth_mode="bearer",
    api_key="test-key",
    temperature=0.1,
    created_at="2026-07-18T00:00:00Z",
    updated_at="2026-07-18T00:00:00Z",
)


def make_full_exam(exam_id="flash-sibling-exam"):
    """给 test_flash_schema 借用：证明整卷的脱敏投影没被闪卡带偏。"""
    draft = GeneratedExamDraft(
        cloze=[
            DraftClozeQuestion(cue=f"c{i}", text=f"句 {i} ____", accept=["答案"], points=3)
            for i in range(CLOZE_COUNT_RANGE[0])
        ],
        choice=[
            DraftChoiceQuestion(
                question=f"选择题 {i}", options=["甲", "乙", "丙", "丁"],
                correct_index=0, points=5,
            )
            for i in range(CHOICE_COUNT_RANGE[0])
        ],
        essay=[
            DraftEssayQuestion(
                question=f"论述题 {i}", reference_answer="参考答案",
                rubric="评分要点", points=18,
            )
            for i in range(ESSAY_COUNT_RANGE[0])
        ],
    )
    return normalize_draft(draft, exam_id)


# ====================== 替身 ======================
class ShardedKnowledgeBase:
    """返回 pieces 段材料，用生产代码同一个分隔符拼接。"""

    def __init__(self, pieces=6):
        self.pieces = [f"材料{i} " + "填充" * 40 for i in range(pieces)]
        self.calls = []

    def sample_exam_context(self, topic=None, notebook_ids=None) -> str:
        self.calls.append((topic, notebook_ids))
        return EXAM_CONTEXT_SEPARATOR.join(self.pieces)


class EmptyKnowledgeBase:
    def sample_exam_context(self, topic=None, notebook_ids=None) -> str:
        return ""


class ScriptedShardLLM:
    """按 prompt 认出这是填空片还是选择片、拿到的是哪份材料，再照着回。

    默认照 prompt 里要的张数上限给（真实模型也是这么做的），cards_per_shard
    只在需要压低卡组规模的用例里显式指定。
    """

    def __init__(self, cards_per_shard=None, duplicate_everything=False):
        self.cards_per_shard = cards_per_shard
        self.duplicate_everything = duplicate_everything
        self.prompts = []

    def bind(self, **_kwargs):
        return self

    async def ainvoke(self, prompt):
        self.prompts.append(prompt)
        shard = next(
            (i for i in range(FLASH_SHARD_COUNT) if f"材料{i} " in prompt), 0
        )
        is_choice = "**选择题**" in prompt
        pattern = r"选择题 \d+~(\d+) 道" if is_choice else r"填空题 \d+~(\d+) 道"
        wanted = self.cards_per_shard
        if wanted is None:
            wanted = int(re.search(pattern, prompt).group(1))

        items = []
        for n in range(wanted):
            key = "共同考点" if self.duplicate_everything else f"考点{shard}-{n}"
            # 题干用的编号要和答案分开：原来题干里嵌着 key、accept 也是 key，
            # 等于把答案写在题干里——exam_quality 的过滤会（正确地）把这种卡全删掉。
            tag = "共同" if self.duplicate_everything else f"{shard}-{n}"
            if is_choice:
                items.append({
                    "question": f"第 {tag} 题的正确项是哪个？",
                    "options": [key, "干扰甲", "干扰乙", "干扰丙"],
                    "correct_index": 0,
                    "explanation": f"{key} 的解析",
                })
            else:
                items.append({
                    "cue": f"提示 {tag}",
                    "text": f"第 {tag} 句的空格填 ____ 即可。",
                    "accept": [key],
                    "match_mode": "text",
                    "explanation": f"{key} 的解析",
                })

        payload = {"title": "排队论与仿真基础", ("choice" if is_choice else "cloze"): items}
        return types.SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))


class StaticFactory:
    def __init__(self, client):
        self.client = client
        self.kwargs = []

    def get(self, selected, **kwargs):
        assert selected.served_model_id == TEST_PROVIDER.served_model_id
        self.kwargs.append(kwargs)
        return self.client


def make_service(knowledge_base, client):
    return ExamService(
        knowledge_base,
        StaticFactory(client),
        exam_cache=ExamCache(),
        llm_gate=LLMGate(max_concurrent=2),
    )


# ====================== 分片 ======================
def test_generates_one_call_per_shard_with_distinct_material():
    llm = ScriptedShardLLM()
    service = make_service(ShardedKnowledgeBase(), llm)

    deck = service.generate_flash_deck("排队论", TEST_PROVIDER)

    assert len(llm.prompts) == FLASH_SHARD_COUNT
    # 每片拿到的材料互不相同 —— 这是并发分片不撞考点的主要手段
    materials = [
        {piece for piece in ("材料0 ", "材料1 ", "材料2 ", "材料3 ", "材料4 ", "材料5 ")
         if piece in prompt}
        for prompt in llm.prompts
    ]
    assert all(materials[i] & materials[j] == set()
               for i in range(len(materials)) for j in range(i + 1, len(materials)))
    assert deck.total_cards == 12


class SlowShardLLM(ScriptedShardLLM):
    """每片都慢，且第一片（材料0）最慢、最后才回来。"""

    async def ainvoke(self, prompt):
        await asyncio.sleep(0.45 if "材料0 " in prompt else 0.3)
        return await super().ainvoke(prompt)


def test_shards_run_at_the_same_time():
    # 出卡组的总耗时是最慢的那一片，不是各片相加
    started = time.perf_counter()
    make_service(ShardedKnowledgeBase(), SlowShardLLM()).generate_flash_deck(None, TEST_PROVIDER)
    assert time.perf_counter() - started < 0.8


def test_deck_keeps_the_deal_order_when_the_first_shard_finishes_last():
    # 各片完成的先后不定；卡组要按发牌顺序拼，第一张永远来自第一片
    deck = make_service(ShardedKnowledgeBase(), SlowShardLLM()).generate_flash_deck(
        None, TEST_PROVIDER
    )
    assert deck.cards[0].type == "cloze"
    assert deck.cards[0].text.startswith("第 0-0 句")


def test_uses_deck_mode_prompt():
    llm = ScriptedShardLLM()
    make_service(ShardedKnowledgeBase(), llm).generate_flash_deck(None, TEST_PROVIDER)

    for prompt in llm.prompts:
        assert "归一到 100 分" not in prompt      # 闪卡不计分
    cloze_prompts = [p for p in llm.prompts if "**填空题**" in p]
    choice_prompts = [p for p in llm.prompts if "**选择题**" in p]
    assert len(cloze_prompts) == 2 and len(choice_prompts) == 1
    assert all("填空题 3~4 道" in p and "这组闪卡" in p for p in cloze_prompts)
    assert all("选择题 3~4 道" in p for p in choice_prompts)


def test_deck_mixes_cloze_and_choice():
    deck = make_service(ShardedKnowledgeBase(), ScriptedShardLLM()).generate_flash_deck(
        None, TEST_PROVIDER
    )
    kinds = [card.type for card in deck.cards]

    assert kinds.count("cloze") == 8 and kinds.count("choice") == 4
    # 交错过，不是前八张填空后四张选择
    assert kinds.index("choice") < 8


def test_small_knowledge_base_scales_cards_per_shard():
    """切不出三片时每片多出几张，卡组规模不该跟着缩水。"""
    llm = ScriptedShardLLM()
    service = make_service(ShardedKnowledgeBase(pieces=1), llm)
    deck = service.generate_flash_deck(None, TEST_PROVIDER)

    assert len(llm.prompts) == 1
    assert "填空题 9~12 道" in llm.prompts[0]
    # 卡组规模没有跟着分片数一起缩水
    assert deck.total_cards == 12
    # 宁可这一组全是填空，也不让两片拿同一份材料——那等于自找重复
    assert {card.type for card in deck.cards} == {"cloze"}


def test_two_shards_still_keep_one_choice_shard():
    llm = ScriptedShardLLM()
    deck = make_service(ShardedKnowledgeBase(pieces=2), llm).generate_flash_deck(
        None, TEST_PROVIDER
    )

    assert len(llm.prompts) == 2
    assert {card.type for card in deck.cards} == {"cloze", "choice"}


def test_empty_material_is_a_request_error_not_a_502():
    service = make_service(EmptyKnowledgeBase(), ScriptedShardLLM())
    with pytest.raises(InvalidExamRequestError):
        service.generate_flash_deck(None, TEST_PROVIDER)


def test_notebook_ids_reach_the_knowledge_base():
    kb = ShardedKnowledgeBase()
    make_service(kb, ScriptedShardLLM()).generate_flash_deck(
        "排队论", TEST_PROVIDER, notebook_ids=["nb-1", "nb-2"]
    )
    assert kb.calls == [("排队论", ["nb-1", "nb-2"])]


# ====================== 去重兜底 ======================
def test_duplicate_shards_collapse_and_fail_loudly():
    """三片全撞同一个考点 → 去重后只剩 1 张，不该端一副没法刷的卡组出去。"""
    service = make_service(ShardedKnowledgeBase(), ScriptedShardLLM(duplicate_everything=True))
    with pytest.raises(UpstreamLLMError):
        service.generate_flash_deck(None, TEST_PROVIDER)


def test_partial_duplicates_survive_above_the_floor():
    llm = ScriptedShardLLM(cards_per_shard=3)
    deck = make_service(ShardedKnowledgeBase(), llm).generate_flash_deck(None, TEST_PROVIDER)
    assert deck.total_cards == 9
    assert [c.id for c in deck.cards] == [f"F{i}" for i in range(1, 10)]


# ====================== 缓存 ======================
def test_deck_is_not_cached_anywhere():
    """答案已经随卡组发给前端、判定也在浏览器本地做，服务端没有读者。

    这条用例盯的是"别把卡组塞进 exam_cache"——真要加服务端复核，也得另开一个
    实例，混用会让 review_exam 对卡组调 all_questions()。
    """
    service = make_service(ShardedKnowledgeBase(), ScriptedShardLLM())
    service.generate_flash_deck(None, TEST_PROVIDER)

    assert len(service.exam_cache) == 0
    assert not hasattr(service, "flash_cache")


def test_review_exam_never_sees_a_deck_id():
    """deck_id 误传给判卷接口只会拿到 410，不会栽在 all_questions() 上。"""
    from app.errors.exam_errors import ExamGoneError

    service = make_service(ShardedKnowledgeBase(), ScriptedShardLLM())
    deck = service.generate_flash_deck(None, TEST_PROVIDER)
    with pytest.raises(ExamGoneError):
        service.review_exam(deck.deck_id, {}, TEST_PROVIDER)


# ====================== 公开投影带答案（闪卡专属） ======================
def test_public_deck_is_immediately_playable_offline():
    deck = make_service(ShardedKnowledgeBase(), ScriptedShardLLM()).generate_flash_deck(
        None, TEST_PROVIDER
    )
    for card in deck.cards:
        assert card.explanation
        if card.type == "choice":
            assert len(card.options) == 4
            assert 0 <= card.correct_index <= 3
        else:
            assert card.accept and card.accept_normalized
            assert card.text.count("____") == 1


# ====================== 路由接线 ======================
class ExamOnlyServices:
    chat = None
    quiz = None
    knowledge_base = None
    client_factory = None

    def __init__(self, exam):
        self.exam = exam

    def warm_up(self):
        pass

    def invalidate_provider(self, served_model_id=None):
        pass

    def close(self):
        pass


@pytest.fixture
def flash_client():
    service = make_service(ShardedKnowledgeBase(), ScriptedShardLLM())
    application = create_app(
        {"TESTING": True},
        registry=FakeRegistry([TEST_PROVIDER]),
        services=ExamOnlyServices(service),
    )
    return application.test_client()


def test_route_returns_envelope_with_deck(flash_client):
    response = flash_client.post(
        "/quiz/flash/generate",
        json={"model": TEST_PROVIDER.served_model_id, "topic": "排队论"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["code"] == 200
    assert body["model"] == TEST_PROVIDER.served_model_id
    data = body["data"]
    assert data["total_cards"] == len(data["cards"]) == 12
    assert data["deck_id"]
    assert {card["type"] for card in data["cards"]} == {"cloze", "choice"}
    assert data["cards"][0]["accept_normalized"]


def test_route_rejects_unknown_model(flash_client):
    response = flash_client.post("/quiz/flash/generate", json={"model": "nope"})
    assert response.status_code == 404


def test_route_rejects_overlong_topic(flash_client):
    response = flash_client.post(
        "/quiz/flash/generate",
        json={"model": TEST_PROVIDER.served_model_id, "topic": "长" * 500},
    )
    assert response.status_code == 422


# ====================== 出题质量过滤的接线 ======================
class LeakyShardLLM(ScriptedShardLLM):
    """每片第一张卡都把答案写进题干——实测出现过（F1「排队系统」）。"""

    async def ainvoke(self, prompt):
        response = await super().ainvoke(prompt)
        payload = json.loads(response.content)
        if payload.get("cloze"):
            first = payload["cloze"][0]
            first["text"] = f"{first['accept'][0]} 就是答案，空格填 ____ 即可。"
        return types.SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))


class MaterialRefShardLLM(ScriptedShardLLM):
    """每张卡都指代学生看不到的材料。"""

    async def ainvoke(self, prompt):
        response = await super().ainvoke(prompt)
        payload = json.loads(response.content)
        for item in payload.get("cloze", []):
            item["text"] = "如图 4.9 所示，空格填 ____ 即可。"
        for item in payload.get("choice", []):
            item["question"] = "根据材料，下列哪个正确？"
        return types.SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))


def test_cards_that_leak_their_answer_are_dropped():
    deck = make_service(ShardedKnowledgeBase(), LeakyShardLLM()).generate_flash_deck(
        "排队论", TEST_PROVIDER
    )
    # 两片填空各被删掉第一张，选择片不受影响
    assert deck.total_cards == 10
    for card in deck.cards:
        stem = f"{getattr(card, 'cue', '')}{getattr(card, 'text', '')}"
        for accepted in getattr(card, "accept", []) or []:
            assert accepted not in stem, "泄漏答案的卡不该被端出去"


def test_a_deck_of_material_referencing_cards_fails_loudly():
    # 全删光了就不该端一副空卡组出去，要让用户看到「重试」而不是空白
    with pytest.raises(UpstreamLLMError, match="质量不达标"):
        make_service(ShardedKnowledgeBase(), MaterialRefShardLLM()).generate_flash_deck(
            "排队论", TEST_PROVIDER
        )

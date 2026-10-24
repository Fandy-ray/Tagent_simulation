"""出卷取材的来源配额。

修的是「填『排队论』，出出来的 21 题里 20 题是论文细节」这个问题：
索引里教材只有几十块，14 篇论文按 200 字窗口切出上千块，不控比例就会被淹没。
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

from app.config import EXAM_TEXTBOOK_MIN_SHARE
from app.rag.knowledge_base import balance_by_source


def docs(*spec: str) -> list[Document]:
    """'t' = 教材，'r' = 论文，'n' = 笔记本；顺序即相关度顺序。"""
    kind = {"t": "textbook", "r": "reference", "n": "opennotebook"}
    return [
        Document(page_content=f"{c}{i}", metadata={"source": kind[c]})
        for i, c in enumerate(spec)
    ]


def sources(picked: list[Document]) -> list[str]:
    return [d.metadata.get("source", "(未标记)") for d in picked]


def test_textbook_reaches_its_quota_even_when_papers_rank_higher():
    # 真实情形：论文块多、排在前面，教材被挤到后面
    pool = docs(*(["r"] * 18 + ["t"] * 10))
    picked = balance_by_source(pool, 10, min_primary_share=0.6)
    assert sources(picked).count("textbook") == 6, "教材没拿到六成配额"
    assert len(picked) == 10


def test_short_textbook_is_topped_up_by_papers():
    # 教材命中不够时宁可比例失衡，也不能少给材料——少给材料等于少出题
    pool = docs(*(["r"] * 18 + ["t"] * 2))
    picked = balance_by_source(pool, 10, min_primary_share=0.6)
    assert len(picked) == 10
    assert sources(picked).count("textbook") == 2


def test_no_papers_at_all_still_fills_up():
    pool = docs(*(["t"] * 12))
    picked = balance_by_source(pool, 10, min_primary_share=0.6)
    assert len(picked) == 10
    assert set(sources(picked)) == {"textbook"}


def test_each_source_keeps_its_own_relevance_order():
    pool = docs(*(["t"] * 5 + ["r"] * 5))
    picked = balance_by_source(pool, 10, min_primary_share=0.6)
    for kind in ("textbook", "reference"):
        same = [d.page_content for d in picked if d.metadata["source"] == kind]
        assert same == sorted(same, key=lambda c: int(c[1:])), f"{kind} 内部顺序乱了"


def test_every_prefix_roughly_respects_the_quota():
    """这条取代了早先那条「保持原始相关度顺序」。

    原来那条是错的，而且错得很隐蔽：调用方拿到结果后还要再截一刀
    （EXAM_SAMPLE_K 块、EXAM_CONTEXT_CHAR_LIMIT 字）。按原始相关度排时，
    教材排在候选池后面，配额明明挑中了，却被这一刀整段截掉——
    纯函数单测全绿，功能却是空转的。交错之后任意前缀都大致满足配额。
    """
    pool = docs(*(["r"] * 20 + ["t"] * 20))
    picked = balance_by_source(pool, 20, min_primary_share=0.6)

    for cut in (5, 10, 15, 20):
        prefix = picked[:cut]
        textbooks = sum(1 for d in prefix if d.metadata["source"] == "textbook")
        assert textbooks >= cut * 0.5, (
            f"前 {cut} 块里只有 {textbooks} 块教材，截断之后配额就没了"
        )


def test_notebook_chunks_count_as_supplementary_not_primary():
    pool = docs(*(["n"] * 10 + ["t"] * 10))
    picked = balance_by_source(pool, 10, min_primary_share=0.6)
    assert sources(picked).count("textbook") == 6


def test_asking_for_more_than_available_returns_everything():
    pool = docs("t", "r", "t")
    picked = balance_by_source(pool, 10, min_primary_share=0.6)
    assert len(picked) == 3


@pytest.mark.parametrize("k", [0, -1])
def test_non_positive_k_returns_nothing(k):
    assert balance_by_source(docs("t", "r"), k) == []


def test_empty_pool_returns_nothing():
    assert balance_by_source([], 10) == []


def test_documents_without_a_source_tag_are_supplementary():
    # 没标来源的块不该被当成教材顶掉配额
    pool = [Document(page_content=f"x{i}", metadata={}) for i in range(10)]
    pool += docs(*(["t"] * 10))
    picked = balance_by_source(pool, 10, min_primary_share=0.6)
    assert sources(picked).count("textbook") == 6


@pytest.mark.parametrize("share,expected", [(0.0, 0), (0.5, 5), (0.65, 7), (1.0, 10)])
def test_quota_rounds_up(share, expected):
    pool = docs(*(["r"] * 10 + ["t"] * 10))
    picked = balance_by_source(pool, 10, min_primary_share=share)
    assert sources(picked).count("textbook") == expected


def test_configured_share_keeps_textbook_in_the_majority():
    # 这条守的是意图本身：配额改到 0.5 以下，这个修复就白做了
    assert EXAM_TEXTBOOK_MIN_SHARE > 0.5


# ====================== 接线：候选池必须比最终挑的多 ======================
#
# 第一版接线踩过的坑：MMR 取 k=EXAM_SAMPLE_K*2，又让 balance 从这些里挑
# EXAM_SAMPLE_K*2 个——池子和要挑的一样大，配额无从挑起，整个修复空转。
# 纯函数的单测照样全绿，所以这里专门守「接线」本身。


class FakeVectorStore:
    """按调用参数记账，并返回一个论文占压倒多数的候选池。"""

    def __init__(self):
        self.calls: list[dict] = []

    def max_marginal_relevance_search(self, query, k, fetch_k, lambda_mult=0.5):
        self.calls.append({"k": k, "fetch_k": fetch_k, "lambda_mult": lambda_mult})
        pool = [
            Document(page_content=f"论文片段{i}", metadata={"source": "reference"})
            for i in range(k - 10)
        ]
        pool += [
            Document(page_content=f"教材片段{i}", metadata={"source": "textbook"})
            for i in range(10)
        ]
        return pool


def make_kb(store):
    from app.rag.knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    kb.vectorstore = store
    kb._knowledge_chunks = [Document(page_content="x", metadata={})]
    return kb


def test_candidate_pool_is_larger_than_what_gets_picked():
    from app.config import EXAM_SAMPLE_K

    store = FakeVectorStore()
    make_kb(store).sample_exam_context("排队论")

    (call,) = store.calls
    assert call["k"] > EXAM_SAMPLE_K * 2, (
        f"候选池只有 {call['k']}，而最终要挑 {EXAM_SAMPLE_K * 2} 个——配额没有可挑的余地"
    )


def test_retrieval_asks_for_relevance_over_diversity():
    store = FakeVectorStore()
    make_kb(store).sample_exam_context("排队论")
    assert store.calls[0]["lambda_mult"] > 0.5, "默认 0.5 对短主题太散，必须显式调高"


def test_textbook_actually_survives_into_the_context():
    # 端到端那一步：论文占压倒多数时，拼出来的材料里仍然要有教材
    store = FakeVectorStore()
    context = make_kb(store).sample_exam_context("排队论")
    assert "教材片段" in context, "配额没生效，拼出来的全是论文"

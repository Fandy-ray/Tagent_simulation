"""检索：中文全文检索、向量检索、范围过滤、结果形状（和原版 fn::text_search / fn::vector_search 对齐）。"""

from __future__ import annotations

from tests.notebook.conftest import new_notebook, text_source, wait_job


def _search(client, query, **extra):
    body = {"query": query, "type": "text", "limit": 10, "search_sources": True, "search_notes": True,
            "minimum_score": 0.2, **extra}
    response = client.post("/api/search", json=body)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def test_chinese_text_search_finds_words_inside_sentences(client):
    nid = new_notebook(client)
    recursion = text_source(client, nid, "递归函数的定义：函数直接或间接调用自身。", title="递归")
    text_source(client, nid, "队列是先进先出的线性表。", title="队列")
    note = client.post("/api/notes", json={"title": "函数笔记", "content": "高阶函数可以接收函数作为参数",
                                           "notebook_id": nid}).get_json()
    result = _search(client, "函数")
    assert result["search_type"] == "text" and result["total_count"] == len(result["results"])
    ids = [r["id"] for r in result["results"]]
    assert set(ids) == {recursion["id"], note["id"]}
    top = result["results"][0]
    assert set(top) == {"id", "parent_id", "title", "relevance"} and top["relevance"] == 1.0
    by_id = {r["id"]: r for r in result["results"]}
    assert by_id[recursion["id"]]["parent_id"] == recursion["id"] and by_id[recursion["id"]]["title"] == "递归"
    assert by_id[note["id"]]["parent_id"] == note["id"] and by_id[note["id"]]["title"] == "函数笔记"

    assert [r["id"] for r in _search(client, "先进先出")["results"]] != []
    assert _search(client, "栈")["results"] == []
    assert [r["id"] for r in _search(client, "函数", search_notes=False)["results"]] == [recursion["id"]]
    assert [r["id"] for r in _search(client, "函数", search_sources=False)["results"]] == [note["id"]]
    assert _search(client, "！？")["results"] == []


def test_relevance_is_share_of_query_words_matched(client):
    nid = new_notebook(client)
    full = text_source(client, nid, "快速排序和归并排序都是分治算法。", title="排序")
    half = text_source(client, nid, "冒泡排序很慢。", title="冒泡")
    results = _search(client, "快速排序")["results"]
    assert [r["id"] for r in results] == [full["id"], half["id"]]
    assert results[0]["relevance"] == 1.0 and 0 < results[1]["relevance"] < 1


def test_english_search_and_limit(client):
    nid = new_notebook(client)
    for i in range(5):
        text_source(client, nid, f"Binary search tree number {i} keeps keys ordered.")
    assert len(_search(client, "BINARY trees", limit=3)["results"]) == 3


def test_scope_filters_by_notebook(client):
    first = new_notebook(client, "一")
    second = new_notebook(client, "二")
    a = text_source(client, first, "哈希表用散列函数定位。")
    b = text_source(client, second, "哈希冲突可以用链地址法解决。")
    assert {r["id"] for r in _search(client, "哈希")["results"]} == {a["id"], b["id"]}
    assert [r["id"] for r in _search(client, "哈希", notebook_ids=[first])["results"]] == [a["id"]]
    assert [r["id"] for r in _search(client, "哈希", notebook_id=second)["results"]] == [b["id"]]
    assert client.post("/api/search", json={"query": "哈希", "notebook_ids": ["bad id"]}).status_code == 400
    assert client.post("/api/search", json={"query": "哈希", "notebook_ids": ["notebook:none"]}).status_code == 404


def test_insight_hits_point_to_source(client):
    nid = new_notebook(client)
    source = text_source(client, nid, "红黑树是一种自平衡二叉查找树。", title="红黑树")
    pending = client.post(f"/api/sources/{source['id']}/insights",
                          json={"transformation_id": "transformation:simple_summary"}).get_json()
    wait_job(client, pending["command_id"])
    hits = _search(client, "模拟回答")["results"]
    insight_hit = next(r for r in hits if r["id"].startswith("source_insight:"))
    assert insight_hit["parent_id"] == source["id"] and insight_hit["title"] == "简要摘要 - 红黑树"


def test_vector_search_shape_threshold_and_scope(client):
    first = new_notebook(client, "一")
    second = new_notebook(client, "二")
    graph = text_source(client, first, "图的深度优先搜索使用栈。", title="DFS")
    text_source(client, second, "图的广度优先搜索使用队列。", title="BFS")
    result = _search(client, "深度优先搜索", type="vector", minimum_score=0.1)
    assert result["search_type"] == "vector"
    top = result["results"][0]
    assert set(top) == {"id", "parent_id", "title", "similarity", "matches"}
    assert top["id"] == graph["id"] and top["matches"] == ["图的深度优先搜索使用栈。"]
    assert all(0.1 <= r["similarity"] <= 1.0001 for r in result["results"])
    scoped = _search(client, "搜索", type="vector", minimum_score=0.0, notebook_ids=[second])["results"]
    assert {r["title"] for r in scoped} == {"BFS"}
    assert _search(client, "完全无关的英文 words", type="vector", minimum_score=0.99)["results"] == []


def test_vector_search_sees_new_and_deleted_content(client):
    nid = new_notebook(client)
    first = text_source(client, nid, "堆排序建堆。")
    assert [r["id"] for r in _search(client, "堆排序", type="vector")["results"]] == [first["id"]]
    client.delete(f"/api/sources/{first['id']}")
    assert _search(client, "堆排序", type="vector")["results"] == []
    second = text_source(client, nid, "堆排序的复杂度。")
    assert [r["id"] for r in _search(client, "堆排序", type="vector")["results"]] == [second["id"]]


def test_vector_search_without_embedding_model_is_400(disabled_client):
    response = disabled_client.post("/api/search", json={"query": "x", "type": "vector"})
    assert response.status_code == 400 and "embedding model" in response.get_json()["detail"]
    assert disabled_client.post("/api/search", json={"query": "x", "type": "text"}).status_code == 200


def test_search_validation(client):
    assert client.post("/api/search", json={"query": "   "}).status_code == 400
    assert client.post("/api/search", json={"query": "x", "limit": 0}).status_code == 422
    assert client.post("/api/search", json={"query": "x", "minimum_score": 2}).status_code == 422
    assert client.post("/api/search", json={"query": "x", "type": "fuzzy"}).status_code == 422
    assert client.post("/api/search", json={}).status_code == 422

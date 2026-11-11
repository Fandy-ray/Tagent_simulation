"""笔记本与笔记接口：字段形状、校验、排序、归档、级联删除、最近浏览。"""

from __future__ import annotations

from tests.notebook.conftest import new_notebook, text_source, wait_job

NOTEBOOK_KEYS = {"id", "name", "description", "archived", "created", "updated", "source_count", "note_count"}
NOTE_KEYS = {"id", "title", "content", "note_type", "created", "updated", "command_id"}


def test_notebook_crud_shape_and_validation(client):
    assert client.get("/api/notebooks").get_json() == []
    created = client.post("/api/notebooks", json={"name": "  数据结构  "}).get_json()
    assert set(created) == NOTEBOOK_KEYS
    assert created["name"] == "数据结构" and created["description"] == "" and created["archived"] is False
    assert created["id"].startswith("notebook:") and "+00:00" in created["created"]

    assert client.post("/api/notebooks", json={"name": "   "}).status_code == 400
    assert client.post("/api/notebooks", json={"description": "无名"}).status_code == 422
    assert client.post("/api/notebooks", data="not json").status_code == 422

    nid = created["id"]
    updated = client.put(f"/api/notebooks/{nid}", json={"description": "新说明", "archived": True}).get_json()
    assert updated["description"] == "新说明" and updated["archived"] is True and updated["name"] == "数据结构"
    assert client.put(f"/api/notebooks/{nid}", json={"description": ""}).get_json()["description"] == ""
    assert client.put(f"/api/notebooks/{nid}", json={"name": ""}).status_code == 400
    assert client.put("/api/notebooks/notebook:nope", json={"name": "x"}).status_code == 404
    assert client.get("/api/notebooks/notebook:nope").get_json() == {"detail": "Notebook not found"}


def test_notebook_list_filters_and_ordering(client):
    a = new_notebook(client, "B 笔记本")
    b = new_notebook(client, "a 笔记本")
    client.put(f"/api/notebooks/{a}", json={"archived": True})
    names = [n["name"] for n in client.get("/api/notebooks?order_by=name asc").get_json()]
    assert names == ["a 笔记本", "B 笔记本"]
    assert [n["id"] for n in client.get("/api/notebooks?archived=false").get_json()] == [b]
    assert [n["id"] for n in client.get("/api/notebooks?archived=true").get_json()] == [a]
    assert client.get("/api/notebooks?order_by=name;drop").status_code == 400
    assert client.get("/api/notebooks?archived=maybe").status_code == 422


def test_counts_recently_viewed_and_links(client):
    nid = new_notebook(client)
    other = new_notebook(client, "另一个")
    source = text_source(client, nid, "一段内容")
    client.post("/api/notes", json={"content": "笔记内容", "notebook_id": nid})
    row = client.get(f"/api/notebooks/{nid}").get_json()
    assert (row["source_count"], row["note_count"]) == (1, 1)

    assert client.post(f"/api/notebooks/{other}/sources/{source['id']}").status_code == 200
    again = client.post(f"/api/notebooks/{other}/sources/{source['id']}").get_json()
    assert "already" in again["message"]
    assert client.get(f"/api/sources/{source['id']}").get_json()["notebooks"] == [nid, other]
    assert client.post(f"/api/notebooks/{other}/sources/source:nope").status_code == 404
    assert client.delete(f"/api/notebooks/{other}/sources/{source['id']}").status_code == 200
    assert client.get(f"/api/notebooks/{other}").get_json()["source_count"] == 0

    recent = client.get("/api/recently-viewed?limit=5").get_json()
    assert {r["type"] for r in recent} == {"notebook", "source"}
    assert set(recent[0]) == {"type", "id", "title", "last_viewed_at"}
    assert client.get("/api/recently-viewed?limit=0").status_code == 422


def test_delete_preview_and_cascade(client, app):
    nid = new_notebook(client)
    other = new_notebook(client, "共享方")
    exclusive = text_source(client, nid, "独占来源")
    shared = text_source(client, nid, "共享来源")
    client.post(f"/api/notebooks/{other}/sources/{shared['id']}")
    client.post("/api/notes", json={"content": "要被删的笔记", "notebook_id": nid})
    session = client.post("/api/chat/sessions", json={"notebook_id": nid, "title": "会话"}).get_json()

    preview = client.get(f"/api/notebooks/{nid}/delete-preview").get_json()
    assert preview == {"notebook_id": nid, "notebook_name": "测试笔记本", "note_count": 1,
                       "exclusive_source_count": 1, "shared_source_count": 1}

    result = client.delete(f"/api/notebooks/{nid}?delete_exclusive_sources=true").get_json()
    assert result["deleted_notes"] == 1 and result["deleted_sources"] == 1
    assert result["unlinked_sources"] == 1 and result["deleted_chat_sessions"] == 1
    assert client.get(f"/api/sources/{exclusive['id']}").status_code == 404
    assert client.get(f"/api/sources/{shared['id']}").get_json()["notebooks"] == [other]
    assert client.get(f"/api/chat/sessions/{session['id']}").status_code == 404
    assert client.get("/api/notes").get_json() == []
    hits = client.post("/api/search", json={"query": "独占", "type": "text"}).get_json()
    assert hits["results"] == []
    assert client.delete(f"/api/notebooks/{nid}").status_code == 404


def test_delete_without_exclusive_keeps_sources(client):
    nid = new_notebook(client)
    source = text_source(client, nid, "留下来的来源")
    result = client.delete(f"/api/notebooks/{nid}").get_json()
    assert result["deleted_sources"] == 0 and result["unlinked_sources"] == 1
    assert client.get(f"/api/sources/{source['id']}").get_json()["notebooks"] == []


def test_note_crud_and_validation(client, app):
    nid = new_notebook(client)
    note = client.post("/api/notes", json={"title": "标题", "content": "递归是函数调用自身", "notebook_id": nid}).get_json()
    assert set(note) == NOTE_KEYS and note["note_type"] == "human" and note["id"].startswith("note:")
    assert wait_job(client, note["command_id"])["status"] == "completed"

    assert client.post("/api/notes", json={"content": "   "}).status_code == 400
    assert client.post("/api/notes", json={"content": "x", "note_type": "robot"}).status_code == 400
    assert client.post("/api/notes", json={"content": "x", "notebook_id": "notebook:none"}).status_code == 404
    assert client.post("/api/notes", json={"title": "缺内容"}).status_code == 422

    listed = client.get(f"/api/notes?notebook_id={nid}").get_json()
    assert [n["id"] for n in listed] == [note["id"]] and listed[0]["content"] == "递归是函数调用自身"
    assert client.get("/api/notes?notebook_id=notebook:none").status_code == 404

    updated = client.put(f"/api/notes/{note['id']}", json={"content": "改过的内容"}).get_json()
    assert updated["content"] == "改过的内容" and updated["title"] == "标题"
    assert client.put(f"/api/notes/{note['id']}", json={"content": " "}).status_code == 400
    assert client.get(f"/api/notes/{note['id']}").get_json()["content"] == "改过的内容"
    assert client.delete(f"/api/notes/{note['id']}").status_code == 200
    assert client.get(f"/api/notes/{note['id']}").status_code == 404
    assert client.delete(f"/api/notes/{note['id']}").status_code == 404


def test_ai_note_gets_generated_title_and_falls_back(client, llm):
    ai = client.post("/api/notes", json={"content": "关于栈的总结", "note_type": "ai"}).get_json()
    assert ai["title"] == "自动生成的标题"
    llm.fail = True
    fallback = client.post("/api/notes", json={"content": "# 第一行标题\n正文", "note_type": "ai"}).get_json()
    assert fallback["title"] == "第一行标题"
    human = client.post("/api/notes", json={"content": "没有标题"}).get_json()
    assert human["title"] is None

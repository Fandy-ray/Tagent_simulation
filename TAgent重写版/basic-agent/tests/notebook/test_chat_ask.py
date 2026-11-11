"""笔记本聊天、来源聊天（SSE）、问答（SSE 三段式）。"""

from __future__ import annotations

import json

from tests.notebook.conftest import new_notebook, text_source


def _events(response) -> list[dict]:
    assert response.mimetype == "text/event-stream"
    return [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines() if line.startswith("data: ")]


def test_notebook_chat_sessions_and_execute(client, llm):
    nid = new_notebook(client)
    session = client.post("/api/chat/sessions", json={"notebook_id": nid, "title": "第一次对话"}).get_json()
    assert set(session) >= {"id", "title", "notebook_id", "created", "updated", "message_count", "model_override"}
    assert session["message_count"] == 0 and session["notebook_id"] == nid
    assert client.post("/api/chat/sessions", json={"notebook_id": "notebook:none"}).status_code == 404
    assert client.get("/api/chat/sessions").status_code == 422

    context = {"sources": [{"id": "source:x", "title": "资料", "full_text": "资料全文"}], "notes": []}
    result = client.post("/api/chat/execute", json={"session_id": session["id"], "message": "总结一下",
                                                    "context": context}).get_json()
    assert result["session_id"] == session["id"]
    assert [m["type"] for m in result["messages"]] == ["human", "ai"]
    assert result["messages"][1]["content"].startswith("模拟回答")
    system = llm.calls[-1][0]["content"]
    assert "[source:x] 资料" in system and "资料全文" in system

    client.post("/api/chat/execute", json={"session_id": session["id"], "message": "再说说", "context": {}})
    assert len(llm.calls[-1]) == 4  # system + 上一轮两条 + 新问题
    detail = client.get(f"/api/chat/sessions/{session['id']}").get_json()
    assert detail["message_count"] == 4 and len(detail["messages"]) == 4
    listed = client.get(f"/api/chat/sessions?notebook_id={nid}").get_json()
    assert listed[0]["message_count"] == 4

    llm.fail = True
    failed = client.post("/api/chat/execute", json={"session_id": session["id"], "message": "失败", "context": {}})
    assert failed.status_code == 502
    assert client.get(f"/api/chat/sessions/{session['id']}").get_json()["message_count"] == 4

    renamed = client.put(f"/api/chat/sessions/{session['id']}", json={"title": "改名", "model_override": "m"}).get_json()
    assert renamed["title"] == "改名" and renamed["model_override"] == "m"
    assert client.delete(f"/api/chat/sessions/{session['id']}").get_json()["success"] is True
    assert client.get(f"/api/chat/sessions/{session['id']}").status_code == 404
    assert client.post("/api/chat/execute", json={"session_id": session["id"], "message": "x",
                                                  "context": {}}).status_code == 404


def test_build_context_modes(client):
    nid = new_notebook(client)
    first = text_source(client, nid, "第一份正文" * 10, title="第一份")
    second = text_source(client, nid, "第二份正文", title="第二份")
    note = client.post("/api/notes", json={"title": "笔记", "content": "笔记正文" * 50, "notebook_id": nid}).get_json()

    default = client.post("/api/chat/context", json={"notebook_id": nid}).get_json()
    assert {s["id"] for s in default["context"]["sources"]} == {first["id"], second["id"]}
    assert all("full_text" not in s for s in default["context"]["sources"])
    assert len(default["context"]["notes"][0]["content"]) == 100
    assert default["char_count"] > 0 and default["token_count"] > 0

    config = {"sources": {first["id"]: "full content", second["id"]: "not in"}, "notes": {note["id"]: "full content"}}
    chosen = client.post("/api/chat/context", json={"notebook_id": nid, "context_config": config}).get_json()
    assert [s["id"] for s in chosen["context"]["sources"]] == [first["id"]]
    assert chosen["context"]["sources"][0]["full_text"].startswith("第一份正文")
    assert chosen["context"]["notes"][0]["content"] == "笔记正文" * 50
    insights_only = client.post("/api/chat/context", json={
        "notebook_id": nid, "context_config": {"sources": {first["id"]: "insights"}, "notes": {}}}).get_json()
    assert "full_text" not in insights_only["context"]["sources"][0]
    assert client.post("/api/chat/context", json={"notebook_id": "notebook:none"}).status_code == 404


def test_source_chat_stream(client, llm):
    nid = new_notebook(client)
    source = text_source(client, nid, "B 树是多路平衡查找树。", title="B 树")
    other = text_source(client, nid, "另一份", title="别的")
    session = client.post(f"/api/sources/{source['id']}/chat/sessions", json={"title": "读 B 树"}).get_json()
    assert session["source_id"] == source["id"]
    assert client.get(f"/api/sources/{source['id']}/chat/sessions").get_json()[0]["id"] == session["id"]

    events = _events(client.post(f"/api/sources/{source['id']}/chat/sessions/{session['id']}/messages",
                                 json={"message": "B 树有什么用？"}))
    assert [e["type"] for e in events] == ["user_message", "ai_message", "context_indicators", "complete"]
    assert events[1]["content"].startswith("模拟回答")
    assert events[2]["data"] == {"sources": [source["id"]], "insights": [], "notes": []}
    assert "B 树是多路平衡查找树" in llm.calls[-1][0]["content"]

    detail = client.get(f"/api/sources/{source['id']}/chat/sessions/{session['id']}").get_json()
    assert [m["type"] for m in detail["messages"]] == ["human", "ai"] and detail["context_indicators"]
    assert client.get(f"/api/sources/{other['id']}/chat/sessions/{session['id']}").status_code == 404
    assert client.post(f"/api/sources/{source['id']}/chat/sessions/{session['id']}/messages",
                       json={"message": " "}).status_code == 400

    llm.fail = True
    failed = _events(client.post(f"/api/sources/{source['id']}/chat/sessions/{session['id']}/messages",
                                 json={"message": "再问"}))
    assert [e["type"] for e in failed] == ["user_message", "error"]
    assert client.delete(f"/api/sources/{source['id']}/chat/sessions/{session['id']}").status_code == 200
    assert client.get(f"/api/sources/{source['id']}/chat/sessions").get_json() == []


def test_ask_stream_three_stages(client, llm):
    nid = new_notebook(client)
    text_source(client, nid, "递归要有终止条件，否则会栈溢出。", title="递归")
    events = _events(client.post("/api/search/ask", json={
        "question": "递归要注意什么？", "strategy_model": "m", "answer_model": "m", "final_answer_model": "m"}))
    assert [e["type"] for e in events] == ["strategy", "answer", "answer", "final_answer", "complete"]
    assert [s["term"] for s in events[0]["searches"]] == ["递归", "不存在的词汇"]
    assert events[1]["content"].startswith("模拟回答")
    assert "没有找到" in events[2]["content"]
    assert events[4]["final_answer"] == events[3]["content"]
    answer_prompt = next(call[-1]["content"] for call in llm.calls if "这次要回答" in call[-1]["content"])
    assert "递归要有终止条件" in answer_prompt

    simple = client.post("/api/search/ask/simple", json={"question": "递归要注意什么？"}).get_json()
    assert simple["question"] == "递归要注意什么？" and simple["answer"].startswith("模拟回答")
    assert client.post("/api/search/ask", json={"question": "  "}).status_code == 400
    assert client.post("/api/search/ask", json={"question": "x", "notebook_ids": ["notebook:none"]}).status_code == 404


def test_ask_with_nothing_found_and_llm_failure(client, llm):
    llm.strategy = "胡言乱语"
    events = _events(client.post("/api/search/ask", json={"question": "量子计算"}))
    assert events[0]["searches"] == [{"term": "量子计算", "instructions": "量子计算"}]
    assert "没有找到" in events[-2]["content"]
    llm.fail = True
    failed = _events(client.post("/api/search/ask", json={"question": "量子计算"}))
    assert [e["type"] for e in failed] == ["error"]

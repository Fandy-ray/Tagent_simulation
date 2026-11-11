"""口令、跨域、杂项接口、重启恢复，以及按 tagent 的调用方式走一遍（兼容性）。"""

from __future__ import annotations

from app.service.notebook.assembly import build_services
from app.repository.notebook.jobs import JobRepository
from tests.notebook.conftest import FakeEmbedder, FakeLLM, make_settings, new_notebook, text_source, wait_job


def test_password_protects_everything_but_open_paths(make_app):
    client = make_app(password="s3cret").test_client()
    for path in ("/", "/health", "/api/health", "/api/config", "/api/auth/status"):
        assert client.get(path).status_code == 200, path
    assert client.get("/api/auth/status").get_json()["auth_enabled"] is True
    denied = client.get("/api/notebooks")
    assert denied.status_code == 401 and denied.headers["WWW-Authenticate"] == "Bearer"
    assert client.get("/api/notebooks", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/notebooks", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/api/notebooks", headers={"X-Password": "s3cret"}).status_code == 200
    assert client.options("/api/notebooks").status_code == 200


def test_cors_and_errors(client, make_app):
    response = client.get("/api/notebooks", headers={"Origin": "http://example.com"})
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    preflight = client.options("/api/auth/status", headers={
        "Origin": "http://localhost:8502", "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "cache-control, authorization, content-type"})
    assert preflight.status_code == 200
    assert preflight.headers["Access-Control-Allow-Headers"] == "cache-control, authorization, content-type"
    strict = make_app(cors_origins=("http://localhost:8502",)).test_client()
    allowed = strict.get("/api/notebooks", headers={"Origin": "http://localhost:8502"})
    assert allowed.headers["Access-Control-Allow-Origin"] == "http://localhost:8502"
    assert "Access-Control-Allow-Origin" not in strict.get("/api/notebooks", headers={"Origin": "http://evil"}).headers
    assert client.get("/api/nothing-here").get_json() == {"detail": "Not Found"}
    assert client.delete("/api/config").status_code == 405


def test_meta_endpoints(client, disabled_client):
    assert client.get("/").get_json() == {"message": "Open Notebook API is running"}
    config = client.get("/api/config").get_json()
    assert config["dbStatus"] == "online" and config["hasUpdate"] is False
    assert client.get("/api/settings").get_json()["default_embedding_option"] == "ask"
    models = client.get("/api/models").get_json()
    assert {m["type"] for m in models} == {"language", "embedding"}
    assert [m["type"] for m in client.get("/api/models?type=language").get_json()] == ["language"]
    defaults = client.get("/api/models/defaults").get_json()
    assert defaults["default_chat_model"] == "model:language" and defaults["default_embedding_model"]
    assert client.get("/api/models/model:language").status_code == 200
    assert client.get("/api/models/model:nope").status_code == 404
    assert client.get("/api/transformations/transformation:dense_summary").get_json()["apply_default"] is True
    assert client.get("/api/commands/jobs/command:none").status_code == 404
    assert client.get("/api/podcasts/episodes").status_code == 404  # 砍掉的功能
    assert disabled_client.get("/api/models/defaults").get_json()["default_embedding_model"] is None


def test_unfinished_jobs_fail_after_restart(tmp_path):
    settings = make_settings(tmp_path)
    first = build_services(settings, embedder=FakeEmbedder(), llm=FakeLLM(), warm_up=False)
    job_id = JobRepository(first.db).create("process_source", {"source_id": "source:x"})
    first.close()
    second = build_services(settings, embedder=FakeEmbedder(), llm=FakeLLM(), warm_up=False)
    try:
        job = JobRepository(second.db).get(job_id)
        assert job["status"] == "failed" and "重启" in job["error"]
    finally:
        second.close()


def test_data_survives_restart(tmp_path, make_app):
    from app.factory import create_notebook_app as create_app

    settings = make_settings(tmp_path)
    services = build_services(settings, embedder=FakeEmbedder(), llm=FakeLLM(), warm_up=False)
    client = create_app(services=services).test_client()
    nid = new_notebook(client)
    text_source(client, nid, "持久化的内容")
    services.close()
    again = build_services(settings, embedder=FakeEmbedder(), llm=FakeLLM(), warm_up=False)
    try:
        client = create_app(services=again).test_client()
        assert client.get("/api/notebooks").get_json()[0]["source_count"] == 1
        assert client.post("/api/search", json={"query": "持久化", "type": "vector"}).get_json()["results"]
    finally:
        again.close()


def test_tagent_style_calls(client, disabled_client):
    """照 tagent 的 app/rag/opennotebook_kb.py 的调用顺序走一遍。"""
    headers = {"Authorization": "Bearer x", "X-Password": "x"}
    assert client.get("/health", headers=headers).status_code == 200
    nid = new_notebook(client, "课程资料")
    source = text_source(client, nid, "动态规划把问题拆成重叠子问题。", title="动态规划")
    note = client.post("/api/notes", json={"title": "我的笔记", "content": "动态规划要找状态转移方程",
                                           "notebook_id": nid, "note_type": "human"}).get_json()
    wait_job(client, note["command_id"])  # 笔记的向量是后台算的

    notebooks = client.get("/api/notebooks", headers=headers).get_json()
    assert notebooks[0]["id"] == nid and notebooks[0]["name"] == "课程资料"
    body = {"query": "动态规划", "type": "vector", "limit": 4, "search_sources": True, "search_notes": True,
            "minimum_score": 0.2}
    hits = client.post("/api/search", json=body, headers=headers).get_json()["results"]
    assert {h["id"] for h in hits} == {source["id"], note["id"]}
    # 没有嵌入模型时 tagent 先收到 400，再改用文本检索
    assert disabled_client.post("/api/search", json=body).status_code == 400
    assert disabled_client.post("/api/search", json={**body, "type": "text"}).status_code == 200

    listed_sources = client.get(f"/api/sources?notebook_id={nid}&limit=100", headers=headers).get_json()
    listed_notes = client.get(f"/api/notes?notebook_id={nid}", headers=headers).get_json()
    assert [s["id"] for s in listed_sources] == [source["id"]] and [n["id"] for n in listed_notes] == [note["id"]]
    assert client.get(f"/api/sources/{source['id']}", headers=headers).get_json()["full_text"].startswith("动态规划")
    assert client.get(f"/api/notes/{note['id']}", headers=headers).get_json()["content"] == "动态规划要找状态转移方程"
    created = client.post("/api/notebooks", json={"name": "tagent 建的", "description": ""}, headers=headers)
    assert created.status_code == 200

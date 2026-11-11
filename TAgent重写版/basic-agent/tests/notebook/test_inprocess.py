"""笔记本并进 basic-agent 之后：进程内检索，以及 /health 仍是 tagent 的。"""

from __future__ import annotations

from app.factory import create_app
from app.rag.opennotebook_kb import InProcessNotebookKnowledgeBase
from tests.conftest import FakeRegistry, FakeServices
from tests.notebook.conftest import new_notebook, text_source


def test_inprocess_search_reads_the_notebook(client, app):
    notebook_id = new_notebook(client, "课程")
    text_source(client, notebook_id, "离散事件仿真用事件表推进时钟。", title="离散事件")
    knowledge = InProcessNotebookKnowledgeBase(app.extensions["notebook_services"])
    assert knowledge.ping() is True
    found = knowledge.search("离散事件", k=3)
    assert found
    assert "事件" in found[0].page_content


def test_agent_app_keeps_health_and_serves_notebooks(make_app):
    notebook = make_app().extensions["notebook_services"]

    class Holder(FakeServices):
        def __init__(self):
            self.notebook = notebook

    agent = create_app({"TESTING": True}, registry=FakeRegistry(), services=Holder())
    client = agent.test_client()
    assert client.get("/health").get_json()["service"] == "basic-agent"
    assert client.get("/").get_json()["service"] == "basic-agent"
    assert client.get("/api/notebooks").status_code == 200
    assert client.get("/api/notebooks").get_json() == []
    # 笔记本上传把全局上限放宽了，答疑这边仍守 1 MiB。
    assert agent.config["MAX_CONTENT_LENGTH"] > 1024 * 1024
    oversized = "x" * (1024 * 1024 + 32)
    rejected = client.post(
        "/v1/chat/completions", data=oversized, content_type="application/json"
    )
    assert rejected.status_code == 413
    assert rejected.get_json()["error"]["code"] == "request_too_large"

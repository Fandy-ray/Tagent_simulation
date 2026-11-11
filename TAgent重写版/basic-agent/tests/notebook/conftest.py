"""测试夹具：每个测试一个临时数据目录；嵌入模型和大模型都换成假的（不加载 torch、不联网）。"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import time

import numpy as np
import pytest

from app.config import NotebookSettings as Settings
from app.service.notebook.assembly import build_services
from app.errors.notebook import UpstreamFailure
from app.factory import create_notebook_app as create_app
from app.infra.notebook.llm_client import LLMClient
from app.rag.notebook.embedder import DisabledEmbedder, normalize_rows
from app.rag.notebook.tokenize import index_tokens

DIM = 256


class FakeEmbedder:
    """按词袋哈希成 256 维向量：词重合越多余弦越高，够检验检索流程。"""

    name = "fake-embedder"

    def __init__(self):
        self.calls = 0

    def available(self) -> bool:
        return True

    def unavailable_reason(self) -> str:
        return ""

    def embed(self, texts: list[str]) -> np.ndarray:
        self.calls += 1
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in index_tokens(text).split():
                digest = hashlib.md5(token.encode()).digest()
                out[row, int.from_bytes(digest[:4], "little") % DIM] += 1.0
        return normalize_rows(out)


class FakeLLM(LLMClient):
    """不发网络请求：定策略回 JSON，起标题回固定标题，其余回「模拟回答」加用户最后一句。"""

    def __init__(self):
        super().__init__("http://fake-llm.invalid/v1")
        self.calls: list[list[dict]] = []
        self.fail = False
        self.strategy = None

    def complete(self, messages, *, temperature=0.3, max_tokens=None):
        self.calls.append(messages)
        if self.fail:
            raise UpstreamFailure("模型服务连不上（测试）")
        last = messages[-1]["content"]
        if "只输出一个 JSON 对象" in last:
            return self.strategy if self.strategy is not None else json.dumps(
                {"reasoning": "查两个词", "searches": [{"term": "递归", "instructions": "解释递归"},
                                                      {"term": "不存在的词汇", "instructions": "看看"}]},
                ensure_ascii=False,
            )
        if "起一个标题" in last:
            return "自动生成的标题"
        return f"模拟回答：{last[-60:]}"


def make_settings(tmp_path: pathlib.Path, **overrides) -> Settings:
    values = dict(
        data_dir=tmp_path / "data", password="", cors_origins=("*",), max_upload_mb=5,
        embedding_mode="local", allow_private_urls=False, job_workers=2,
    )
    values.update(overrides)
    return dataclasses.replace(Settings.from_env(), **values)


@pytest.fixture
def make_app(tmp_path):
    created = []

    def factory(*, embedder=None, llm=None, **overrides):
        settings = make_settings(tmp_path, **overrides)
        services = build_services(
            settings, embedder=embedder if embedder is not None else FakeEmbedder(),
            llm=llm or FakeLLM(), warm_up=False,
        )
        app = create_app(services=services)
        app.config["TESTING"] = True
        created.append(services)
        return app

    yield factory
    for services in created:
        services.close()


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def llm(app) -> FakeLLM:
    return app.extensions["notebook_services"].llm


@pytest.fixture
def disabled_client(make_app):
    return make_app(embedder=DisabledEmbedder()).test_client()


def wait_job(client, command_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/commands/jobs/{command_id}").get_json()
        if job["status"] in {"completed", "failed"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"任务 {command_id} 超时没跑完")


def new_notebook(client, name="测试笔记本") -> str:
    response = client.post("/api/notebooks", json={"name": name, "description": "说明"})
    assert response.status_code == 200, response.get_json()
    return response.get_json()["id"]


def text_source(client, notebook_id: str, content: str, title: str | None = None, **extra) -> dict:
    form = {"type": "text", "content": content, "notebook_id": notebook_id, "embed": "true", **extra}
    if title:
        form["title"] = title
    response = client.post("/api/sources", data=form)
    assert response.status_code == 200, response.get_json()
    return response.get_json()

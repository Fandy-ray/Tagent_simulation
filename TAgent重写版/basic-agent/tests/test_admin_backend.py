"""管理后台接的后端：学习记录统计、学生的赞 / 踩、知识库配置与重建索引，以及 Playground 的直接对话。

以前管理后台全是页面里写死的示例数据（排行榜的分数是用 sin 算出来的），这些接口让它显示真的东西。
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from urllib.parse import quote

import pytest
from langchain_core.embeddings import Embeddings

from app.api import knowledge_admin
from app.container import Services
from app.factory import create_app
from app.infra.background_job import BackgroundJob
from app.repository import learning_store as learning_store_module
from app.repository.learning_store import MIGRATIONS, LearningStore, now_ms
from app.repository.provider_repository import ModelProviderRegistry

DEVICE = "dev_7f3a9c21e4b8"
ME = {"X-Tagent-Client-Id": DEVICE, "X-Tagent-Client-Name": quote("小明")}
ADMIN = {"X-Agent-Admin-Token": "admin-token"}
DAY_MS = 86_400_000


@pytest.fixture
def store(tmp_path):
    instance = LearningStore(tmp_path / "tagent.sqlite3")
    yield instance
    instance.close()


def make_client(store, *, knowledge_base=None):
    registry = ModelProviderRegistry(Path(tempfile.mkdtemp()) / "providers.json")
    registry.create_provider({
        "name": "m", "served_model_id": "m", "base_url": "http://127.0.0.1:9/v1",
        "upstream_model": "u", "auth_mode": "none", "api_key": "", "enabled": True,
    })
    services = Services(chat=None, quiz=None, exam=None, essay=None,
                        knowledge_base=knowledge_base, client_factory=None, store=store)
    app = create_app({"TESTING": True, "AGENT_ADMIN_TOKEN": "admin-token"}, registry=registry, services=services)
    return app.test_client()


def vote(client, rating, *, message_id="assistant-1", headers=ME, **extra):
    return client.post("/learner/feedback", headers=headers, json={
        "message_id": message_id, "rating": rating, "model": "deepseek", "mode": "qa",
        "question": "什么是排队论？", "answer": "排队论研究随机服务系统。", **extra,
    })


# ====================== 库：升级、反馈、统计 ======================
def test_upgrading_an_old_database_keeps_its_records(tmp_path):
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    for target, script in enumerate(MIGRATIONS[:2], start=1):
        for statement in (s.strip() for s in script.split(";")):
            if statement:
                conn.execute(statement)
        conn.execute(f"PRAGMA user_version={target}")
    conn.execute("INSERT INTO chat_turns (student_id, mode, model, question, answer, created_at) "
                 "VALUES ('dev_old_student_1', 'qa', 'm', 'q', 'a', 1)")
    conn.commit()
    conn.close()

    upgraded = LearningStore(path)
    try:
        assert upgraded.schema_version == len(MIGRATIONS) == 3
        assert upgraded.db_info()["tables"]["chat_turns"] == 1
        assert upgraded.db_info()["tables"]["feedback"] == 0
    finally:
        upgraded.close()


def test_changing_a_vote_overwrites_it_and_voting_again_takes_it_back(store):
    base = dict(student_id=DEVICE, message_key="assistant-1", model="m", mode="qa", question="q", answer="a")
    store.record_feedback(rating=1, **base)
    store.record_feedback(rating=-1, **base)
    assert [row["rating"] for row in store.feedback_list()] == [-1]

    store.record_feedback(rating=0, **base)
    assert store.feedback_list() == []


def test_feedback_list_filters_by_rating_and_names_the_student(store):
    store.touch_student(DEVICE, "小明")
    store.record_feedback(student_id=DEVICE, message_key="a-1", model="m", mode="qa", rating=1, question="q", answer="a")
    store.record_feedback(student_id=DEVICE, message_key="a-2", model="m", mode="qa", rating=-1, question="q", answer="a")
    assert [row["rating"] for row in store.feedback_list(rating=-1)] == [-1]
    assert {row["student_name"] for row in store.feedback_list()} == {"小明"}


def test_analytics_fills_every_day_and_leaves_out_older_records(store, monkeypatch):
    now = now_ms()
    store.record_chat(student_id=DEVICE, mode="qa", model="m", question="q", answer="a")
    store.record_chat(student_id=DEVICE, mode="chat", model="m", question="q", answer="a")
    # 窗口外的一条：不该算进任何一天
    store._conn().execute(
        "INSERT INTO chat_turns (student_id, mode, model, question, answer, created_at) VALUES (?, 'qa', 'm', 'q', 'a', ?)",
        (DEVICE, now - 30 * DAY_MS),
    )

    result = store.analytics(days=7)

    assert len(result["daily"]) == 7
    assert [item["day"] for item in result["daily"]] == sorted(item["day"] for item in result["daily"])
    # Playground 的直接对话不算「答疑量」，但在模式分布里看得到
    assert result["daily"][-1]["chat_turns"] == 1
    assert result["totals"]["chat_turns"] == 1
    assert result["chat_modes"] == {"qa": 1, "chat": 1}
    assert result["daily"][-1]["active_students"] == 1


def test_analytics_ranks_the_most_active_students_in_the_window(store):
    other = "dev_000000000002"
    store.touch_student(DEVICE, "小明")
    store.touch_student(other, "小红")
    for _ in range(3):
        store.record_chat(student_id=other, mode="qa", model="m", question="q", answer="a")
    store.record_chat(student_id=DEVICE, mode="qa", model="m", question="q", answer="a")
    store.record_chat(student_id=DEVICE, mode="chat", model="m", question="q", answer="a")  # Playground 不算
    store._conn().execute(
        "INSERT INTO chat_turns (student_id, mode, model, question, answer, created_at) VALUES (?, 'qa', 'm', 'q', 'a', ?)",
        (DEVICE, now_ms() - 30 * DAY_MS),
    )

    result = store.analytics(days=7)
    students = result["students"]

    assert result["active_students"] == 2
    assert [(row["name"], row["chat_turns"]) for row in students] == [("小红", 3), ("小明", 1)]
    assert students[0]["essay_reviews"] == 0 and students[0]["exams_reviewed"] == 0


def test_model_activity_has_one_entry_per_day_with_votes_and_scenarios(store):
    store.record_chat(student_id=DEVICE, mode="qa", model="a", question="q", answer="x")
    store.record_chat(student_id=DEVICE, mode="paper", model="a", question="q", answer="x")
    store.record_chat(student_id=DEVICE, mode="qa", model="b", question="q", answer="x")
    store.record_feedback(student_id=DEVICE, message_key="m1", model="a", mode="qa", rating=-1, question="q", answer="x")

    activity = store.model_activity("a", days=30)

    assert len(activity["daily"]) == 30
    assert activity["daily"][-1] == {"day": activity["daily"][-1]["day"], "chat_turns": 2, "thumbs_up": 0,
                                     "thumbs_down": 1}
    assert sum(item["chat_turns"] for item in activity["daily"][:-1]) == 0
    assert activity["chat_modes"] == {"qa": 1, "paper": 1}


def test_model_stats_count_completion_and_votes_per_model(store):
    store.record_chat(student_id=DEVICE, mode="qa", model="a", question="q", answer="x", finish_reason="stop", duration_ms=1000)
    store.record_chat(student_id=DEVICE, mode="qa", model="a", question="q", answer="x", finish_reason="interrupted", duration_ms=3000)
    store.record_chat(student_id=DEVICE, mode="qa", model="b", question="q", answer="x", finish_reason="stop", duration_ms=500)
    store.record_feedback(student_id=DEVICE, message_key="m1", model="a", mode="qa", rating=1, question="q", answer="x")
    store.record_feedback(student_id=DEVICE, message_key="m2", model="a", mode="qa", rating=-1, question="q", answer="x")
    store.record_feedback(student_id=DEVICE, message_key="m3", model="a", mode="qa", rating=1, question="q", answer="x")

    by_model = {row["model"]: row for row in store.model_stats()}

    assert by_model["a"]["chat_turns"] == 2
    assert by_model["a"]["avg_duration_ms"] == 2000
    assert by_model["a"]["completion_rate"] == 0.5
    assert by_model["a"]["thumbs_up_rate"] == round(2 / 3, 3)
    assert by_model["b"]["thumbs_up_rate"] is None
    # 用得多的排前面
    assert [row["model"] for row in store.model_stats()] == ["a", "b"]


def test_db_info_lists_tables_and_backups(store):
    store.record_chat(student_id=DEVICE, mode="qa", model="m", question="q", answer="a")
    store.backup()

    info = store.db_info()

    assert info["schema_version"] == 3
    assert info["tables"]["chat_turns"] == 1
    assert info["bytes"] > 0
    assert len(info["backups"]) == 1 and info["backups"][0]["file"].startswith("tagent-")


# ====================== 学生端：赞 / 踩 ======================
def test_a_vote_is_recorded_for_the_student(store):
    client = make_client(store)

    assert vote(client, "up").get_json() == {"recorded": True}
    rows = store.feedback_list()
    assert [(row["rating"], row["student_name"], row["model"]) for row in rows] == [(1, "小明", "deepseek")]

    vote(client, None)
    assert store.feedback_list() == []


def test_temporary_chats_are_not_recorded(store):
    client = make_client(store)
    response = vote(client, "up", headers={**ME, "X-Tagent-No-Record": "1"})
    assert response.get_json() == {"recorded": False}
    assert store.feedback_list() == []


def test_votes_without_a_device_id_are_not_recorded(store):
    """分不清是谁点的就不记：否则改评价会多一条，撤销还会删到别人的。"""
    client = make_client(store)
    assert vote(client, "up", headers={}).get_json() == {"recorded": False}
    assert store.feedback_list() == []


@pytest.mark.parametrize("override", [
    {"message_id": "has spaces"},
    {"rating": "meh"},
    {"rating": []},
    {"rating": {}},
    {"mode": "exam"},
    {"mode": ["qa"]},
    {"model": ""},
    {"question": 3},
])
def test_malformed_votes_are_rejected(store, override):
    client = make_client(store)
    body = {"message_id": "assistant-1", "rating": "up", "model": "deepseek", "mode": "qa", "question": "q",
            "answer": "a", **override}
    assert client.post("/learner/feedback", headers=ME, json=body).status_code == 400
    assert store.feedback_list() == []


def test_a_vote_for_the_longest_allowed_model_id_is_recorded(store):
    """登记模型 ID 最长 128 个字符，这样的模型也要能点赞"""
    client = make_client(store)
    assert vote(client, "up", model="m" * 128).get_json() == {"recorded": True}
    assert vote(client, "up", message_id="assistant-2", model="m" * 129).status_code == 400


def test_votes_are_refused_when_the_learning_store_is_off():
    client = make_client(None)
    response = vote(client, "up")
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "learning_store_unavailable"


def test_long_answers_are_stored_as_an_excerpt(store):
    client = make_client(store)
    vote(client, "down", answer="长" * 10_000)
    assert len(store.feedback_list()[0]["answer"]) == 4000


# ====================== 老师端：统计接口 ======================
@pytest.mark.parametrize("path", [
    "/admin/learning/analytics", "/admin/learning/models", "/admin/learning/feedback", "/admin/learning/db",
    "/admin/knowledge",
])
def test_admin_endpoints_need_the_admin_token(store, path):
    client = make_client(store, knowledge_base=FakeKnowledgeBase())
    assert client.get(path).status_code == 403
    assert client.get(path, headers={"X-Agent-Admin-Token": "wrong"}).status_code == 403
    assert client.get(path, headers=ADMIN).status_code == 200


def test_statistics_endpoints_return_real_records(store):
    client = make_client(store)
    store.record_chat(student_id=DEVICE, mode="qa", model="deepseek", question="q", answer="a", finish_reason="stop")
    vote(client, "down")

    analytics = client.get("/admin/learning/analytics?days=3", headers=ADMIN).get_json()
    assert len(analytics["daily"]) == 3 and analytics["totals"]["chat_turns"] == 1

    models = client.get("/admin/learning/models", headers=ADMIN).get_json()["models"]
    assert models[0]["model"] == "deepseek" and models[0]["thumbs_down"] == 1

    assert client.get("/admin/learning/feedback?rating=up", headers=ADMIN).get_json() == {"feedback": []}
    assert len(client.get("/admin/learning/feedback?rating=down", headers=ADMIN).get_json()["feedback"]) == 1

    assert client.get("/admin/learning/db", headers=ADMIN).get_json()["tables"]["feedback"] == 1


def test_a_teacher_can_delete_a_feedback_entry(store):
    client = make_client(store)
    vote(client, "up")
    feedback_id = store.feedback_list()[0]["id"]

    assert client.delete(f"/admin/learning/feedback/{feedback_id}").status_code == 403
    assert client.delete(f"/admin/learning/feedback/{feedback_id}", headers=ADMIN).get_json() == {"status": True}
    assert store.feedback_list() == []
    assert client.delete(f"/admin/learning/feedback/{feedback_id}", headers=ADMIN).status_code == 404


def test_model_activity_endpoint(store):
    client = make_client(store)
    store.record_chat(student_id=DEVICE, mode="qa", model="deepseek:v3", question="q", answer="a")
    body = client.get("/admin/learning/models/deepseek:v3/activity?days=7", headers=ADMIN).get_json()
    assert body["model"] == "deepseek:v3" and len(body["daily"]) == 7 and body["daily"][-1]["chat_turns"] == 1
    assert client.get("/admin/learning/models/x/activity?days=999", headers=ADMIN).status_code == 400


@pytest.mark.parametrize("query", ["days=0", "days=366", "days=abc", "rating=meh"])
def test_statistics_endpoints_reject_bad_parameters(store, query):
    client = make_client(store)
    path = "/admin/learning/feedback" if query.startswith("rating") else "/admin/learning/analytics"
    assert client.get(f"{path}?{query}", headers=ADMIN).status_code == 400


# ====================== 老师端：知识库 ======================
class FakeKnowledgeBase:
    def __init__(self):
        self.reloads = 0
        self.cleared = 0

    def describe(self):
        return {"kind": "local"}

    def admin_snapshot(self):
        return {"kind": "local", "retrieval": {"qa_top_k": 4}}

    def clear_retrieval_cache(self):
        self.cleared += 1
        return 7

    def reload(self):
        self.reloads += 1
        return {"chunks": 42, "papers": 14}


@pytest.fixture
def sync_jobs(monkeypatch):
    """后台任务就地跑完，测试里直接看结果。"""
    jobs = {name: BackgroundJob(name, spawn=lambda task: task()) for name in ("reload", "references")}
    monkeypatch.setattr(knowledge_admin, "_jobs", jobs)
    return jobs


def test_knowledge_page_shows_what_the_backend_really_uses(store, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_SOURCE", "local")
    client = make_client(store, knowledge_base=FakeKnowledgeBase())
    body = client.get("/admin/knowledge", headers=ADMIN).get_json()
    assert body["source"] == "local"
    assert body["knowledge_base"]["retrieval"]["qa_top_k"] == 4
    assert body["jobs"]["reload"]["status"] == "idle"


def test_clearing_the_retrieval_cache(store):
    knowledge = FakeKnowledgeBase()
    client = make_client(store, knowledge_base=knowledge)
    assert client.post("/admin/knowledge/cache/clear", headers=ADMIN).get_json() == {"cleared": 7}
    assert knowledge.cleared == 1


def test_reloading_runs_in_the_background_and_reports_back(store, sync_jobs):
    knowledge = FakeKnowledgeBase()
    client = make_client(store, knowledge_base=knowledge)

    response = client.post("/admin/knowledge/reload", headers=ADMIN)

    assert response.status_code == 202
    assert knowledge.reloads == 1
    status = client.get("/admin/knowledge", headers=ADMIN).get_json()["jobs"]["reload"]
    assert status["status"] == "succeeded" and "42 块" in status["message"] and "14 篇" in status["message"]


def test_a_running_job_is_not_started_twice(store):
    job = BackgroundJob("reload", spawn=lambda task: None)  # 起了但一直没跑完
    assert job.start(lambda: "done") is True
    assert job.start(lambda: "done") is False
    assert job.status()["status"] == "running"


def test_a_job_whose_thread_cannot_start_is_not_left_running():
    def no_threads(task):
        raise RuntimeError("can't start new thread")

    job = BackgroundJob("reload", spawn=no_threads)
    assert job.start(lambda: "done") is False
    assert job.status()["status"] == "failed" and "can't start new thread" in job.status()["message"]
    job._spawn = lambda task: task()  # 缓过来之后能再点
    assert job.start(lambda: "done") is True and job.status()["status"] == "succeeded"


def test_a_failing_job_is_reported_as_failed():
    job = BackgroundJob("reload", spawn=lambda task: task())

    def boom():
        raise RuntimeError("期刊官网连不上")

    job.start(boom)
    assert job.status()["status"] == "failed" and job.status()["message"] == "期刊官网连不上"


def test_refreshing_references_is_refused_when_they_are_off(store, monkeypatch, sync_jobs):
    monkeypatch.setenv("TAGENT_REFERENCES", "0")
    client = make_client(store, knowledge_base=FakeKnowledgeBase())
    assert client.post("/admin/knowledge/references/refresh", headers=ADMIN).status_code == 400


def test_refreshing_references_runs_the_script_then_reloads(store, monkeypatch, sync_jobs):
    monkeypatch.setenv("TAGENT_REFERENCES", "1")
    knowledge = FakeKnowledgeBase()
    calls = []

    class Done:
        returncode = 0
        stdout = "参考文献 14 篇就绪\n"
        stderr = ""

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return Done()

    monkeypatch.setattr(knowledge_admin.subprocess, "run", fake_run)
    client = make_client(store, knowledge_base=knowledge)

    assert client.post("/admin/knowledge/references/refresh", headers=ADMIN).status_code == 202
    args, kwargs = calls[0]
    assert args[1:] == ["-X", "utf8", "-m", "tools.fetch_references"]
    # 子进程按 UTF-8 写、这边按 UTF-8 读，不跟着系统默认编码走（中文 Windows 是 GBK）
    assert kwargs["encoding"] == "utf-8" and kwargs["errors"] == "replace"
    assert knowledge.reloads == 1
    message = client.get("/admin/knowledge", headers=ADMIN).get_json()["jobs"]["references"]["message"]
    assert "参考文献 14 篇就绪" in message and "索引已重建" in message


# ====================== 知识库：在线重建 ======================
class HashEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [self._vector(t) for t in texts]

    def embed_query(self, text):
        return self._vector(text)

    @staticmethod
    def _vector(text):
        return [float((sum(map(ord, text)) * (i + 3)) % 97) / 97.0 for i in range(8)]


def test_reload_picks_up_an_edited_textbook_and_drops_cached_results(tmp_path):
    from app.rag.knowledge_base import KnowledgeBase

    book = tmp_path / "book.md"
    book.write_text("# 排队论\n\n到达率与服务率。\n", encoding="utf-8")
    kb = KnowledgeBase(knowledge_file=book, embeddings=HashEmbeddings(), index_cache_dir=tmp_path / "cache",
                       embedding_revision="test-embedding-v1")
    kb.warm_up()
    kb.retrieve("到达率")
    assert kb.admin_snapshot()["retrieval"]["cache"]["entries"] == 1

    book.write_text("# 排队论\n\n到达率与服务率。\n\n## 蒙特卡洛\n\n随机抽样估计积分。\n", encoding="utf-8")
    result = kb.reload()

    assert result["chunks"] == 2
    assert kb.admin_snapshot()["retrieval"]["cache"]["entries"] == 0
    assert any("随机抽样" in doc.page_content for doc in kb.retrieve("蒙特卡洛 随机抽样")[1])


def test_snapshot_reports_real_constants_without_building_anything(tmp_path):
    from app.rag import knowledge_base as module

    kb = module.KnowledgeBase(knowledge_file=tmp_path / "missing.md")
    snapshot = kb.admin_snapshot()
    assert snapshot["chunking"]["chunk_size"] == module.TEXTBOOK_CHUNK_SIZE
    assert snapshot["retrieval"]["qa_top_k"] == module.QA_RETRIEVE_K
    assert snapshot["index"]["ready"] is False and snapshot["embedding"]["loaded"] is False


# ====================== Playground：不检索，直接和模型聊 ======================
def test_chat_mode_skips_retrieval_and_keeps_only_the_students_messages():
    from app.agent.graphs.answer import ANSWER_GRAPH, prompt_messages

    class NoRetrieval:
        def retrieve(self, query, notebook_ids=None):
            raise AssertionError("Playground 不该检索")

    class Deps:
        knowledge_base = NoRetrieval()

    messages = [{"role": "system", "content": "你是助手"}, {"role": "user", "content": "你好"}]
    state = ANSWER_GRAPH.invoke(
        {"messages": messages, "query": "你好", "mode": "chat", "stream": True, "step_log": []}, context=Deps()
    )
    assert prompt_messages(state) == messages


def test_chat_mode_is_accepted_by_the_validator():
    from app.api.validators import chat_mode

    assert chat_mode({"mode": "chat"}) == "chat"


def test_time_window_starts_at_local_midnight():
    window = learning_store_module._DayWindow(3)
    assert window.since <= now_ms() - 2 * DAY_MS + DAY_MS
    assert len(window.labels) == 3 and window.labels == sorted(window.labels)
    assert window.label(2) == window.labels[-1] and window.label(3) is None and window.label(-1) is None


SPREAD = 36


def _record_spread(store):
    """最近一年里每隔 9 天 13 小时一条（36 条都在 365 天窗口里），盖住一天里的各个钟点、跨过夏令时切换。"""
    for n in range(SPREAD):
        at = now_ms() - n * (9 * DAY_MS + 13 * 3_600_000)
        store._conn().execute(
            "INSERT INTO chat_turns (student_id, mode, model, question, answer, created_at) VALUES (?, 'qa', 'm', 'q', 'a', ?)",
            (DEVICE, at),
        )
        store._conn().execute(
            "INSERT INTO feedback (student_id, message_key, model, mode, rating, question, answer, created_at, updated_at)"
            " VALUES (?, ?, 'm', 'qa', 1, 'q', 'a', ?, ?)", (DEVICE, f"m{n}", at, at),
        )


def _expected_days():
    from datetime import datetime

    counts = {}
    for n in range(SPREAD):
        at = now_ms() - n * (9 * DAY_MS + 13 * 3_600_000)
        day = datetime.fromtimestamp(at / 1000).astimezone().date().isoformat()
        counts[day] = counts.get(day, 0) + 1
    return counts


def test_daily_counts_land_on_the_right_local_day(store):
    _record_spread(store)
    daily = {item["day"]: item["chat_turns"] for item in store.analytics(days=365)["daily"] if item["chat_turns"]}
    assert daily == _expected_days() and sum(daily.values()) == SPREAD
    votes = {item["day"]: item["thumbs_up"] for item in store.model_activity("m", days=365)["daily"] if item["thumbs_up"]}
    assert votes == daily


def test_a_window_across_a_daylight_saving_change_falls_back_to_per_row_conversion(tmp_path, monkeypatch):
    """夏令时地区一年里总有一天是 23 或 25 小时，不能按 24 小时整除分天。"""
    import time

    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    try:
        assert learning_store_module._DayWindow(365).uniform is False
        dst_store = LearningStore(tmp_path / "dst.sqlite3")
        try:
            _record_spread(dst_store)
            daily = {item["day"]: item["chat_turns"] for item in dst_store.analytics(days=365)["daily"]
                     if item["chat_turns"]}
            assert daily == _expected_days()
        finally:
            dst_store.close()
    finally:
        monkeypatch.undo()
        time.tzset()


# ====================== 统计结果的记忆 ======================
def test_statistics_are_reused_until_a_record_is_written(store, monkeypatch):
    queries = []
    real = store._active_students

    def counting(*args, **kwargs):
        queries.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(store, "_active_students", counting)
    first = store.analytics(days=7)
    assert store.analytics(days=7) is first and len(queries) == 1

    for write in (
        lambda: store.record_chat(student_id=DEVICE, mode="qa", model="m", question="q", answer="a"),
        lambda: store.record_feedback(student_id=DEVICE, message_key="k", model="m", mode="qa", rating=1,
                                      question="q", answer="a"),
        lambda: store.touch_student(DEVICE, "小明"),
    ):
        before = len(queries)
        write()
        store.analytics(days=7)
        assert len(queries) == before + 1, "写过记录之后必须重算"
    assert store.analytics(days=7)["totals"]["chat_turns"] == 1


def test_concurrent_identical_statistics_are_computed_once():
    import threading

    memo = learning_store_module._StatsMemo()
    computed = []
    gate = threading.Event()

    def compute():
        computed.append(1)
        gate.wait(2)
        return {"n": len(computed)}

    results = []
    threads = [threading.Thread(target=lambda: results.append(memo.get(("k",), compute))) for _ in range(10)]
    for thread in threads:
        thread.start()
    gate.set()
    for thread in threads:
        thread.join(5)
    assert computed == [1] and all(result == {"n": 1} for result in results) and len(results) == 10


def test_statistics_written_by_another_process_show_up_within_the_age_limit():
    now = [0.0]
    memo = learning_store_module._StatsMemo(max_age_s=30, clock=lambda: now[0])
    values = iter([1, 2])
    assert memo.get(("k",), lambda: next(values)) == 1
    now[0] = 29
    assert memo.get(("k",), lambda: next(values)) == 1
    now[0] = 31
    assert memo.get(("k",), lambda: next(values)) == 2


def test_a_write_during_a_computation_is_not_hidden_by_it():
    memo = learning_store_module._StatsMemo()

    def compute_while_someone_writes():
        memo.bump()
        return "算到一半有人写了"

    memo.get(("k",), compute_while_someone_writes)
    assert memo.get(("k",), lambda: "重算的") == "重算的"


def test_remembered_statistics_are_capped():
    """键里带日期和学生编号，不设上限的话后端连着跑一学期会越攒越多"""
    memo = learning_store_module._StatsMemo(max_entries=2)
    computed = []

    def compute(name):
        computed.append(name)
        return name

    for name in ("a", "b", "a", "c", "a", "b"):
        memo.get((name,), lambda name=name: compute(name))
    # a 一直在用所以留着；c 进来时挤掉了最久没用的 b，b 再来要重算
    assert computed == ["a", "b", "c", "b"]
    assert len(memo._entries) == 2 and len(memo._key_locks) <= 3


def test_db_info_skips_a_backup_rotated_away_while_listing(store):
    store.backup()
    (store.backup_dir / "tagent-19700101-000000.sqlite3").symlink_to(store.backup_dir / "已经删掉了.sqlite3")
    info = store.db_info()
    assert len(info["backups"]) == 1 and info["backups"][0]["modified_at"] is not None

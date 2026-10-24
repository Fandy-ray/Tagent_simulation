"""接口层的学习记录：谁的、记了什么、只记一次、记不上也不影响请求；老师接口要口令。"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import quote

import pytest

from app.api import exam as exam_api
from app.container import Services
from app.factory import create_app
from app.repository.learning_store import LearningStore
from app.repository.provider_repository import ModelProviderRegistry
from app.util.singleflight import SingleFlight

PAPER = "排队论研究随机服务系统。" * 12
EXAM_ID = "12345678-1234-5678-1234-567812345678"
DEVICE = "dev_7f3a9c21e4b8"
ME = {"X-Tagent-Client-Id": DEVICE, "X-Tagent-Client-Name": quote("小明")}


class FakeChat:
    def __init__(self, tokens=("排队论", "研究", "排队。"), fail_after=None):
        self.tokens, self.fail_after = tokens, fail_after

    def answer(
        self, messages, provider, notebook_ids=None, *, mode="qa",
        retrieval_query=None, tuning=None,
    ):
        return {"content": "".join(self.tokens)}

    def stream_answer(
        self, messages, provider, notebook_ids=None, *, mode="qa", retrieval_query=None, tuning=None, on_citations=None
    ):
        for index, token in enumerate(self.tokens):
            if self.fail_after is not None and index == self.fail_after:
                raise RuntimeError("upstream reset")
            yield token, None
        yield "", "stop"


class FakeEssay:
    def __init__(self, seconds=0.0):
        self.seconds, self.calls = seconds, 0

    def review_paper(self, text, topic, provider, notebook_ids=None):
        self.calls += 1
        time.sleep(self.seconds)
        return {"score": 78, "dimensions": [], "annotations": [], "overall_comment": "结构清楚"}


class FakeExam:
    def __init__(self, seconds=0.0):
        self.seconds, self.generated = seconds, 0
        self.lock = threading.Lock()

    def generate_exam(self, topic, provider, notebook_ids=None):
        time.sleep(self.seconds)
        with self.lock:
            self.generated += 1
            exam_id = EXAM_ID if self.generated == 1 else f"12345678-1234-5678-1234-{self.generated:012d}"
        return {"exam_id": exam_id, "title": "排队论测评", "total_points": 100, "cloze": [], "choice": [], "essay": []}

    def review_exam(self, exam_id, answers, provider):
        return {"exam_id": exam_id, "total_score": 64, "total_points": 100, "results": []}


class BrokenStore:
    def __getattr__(self, name):
        def fail(*_args, **_kwargs):
            raise OSError("disk I/O error")

        return fail


@pytest.fixture(autouse=True)
def fresh_flights():
    exam_api._flights = SingleFlight()


@pytest.fixture
def store(tmp_path):
    instance = LearningStore(tmp_path / "tagent.sqlite3")
    yield instance
    instance.close()


def make_client(store, *, chat=None, essay=None, exam=None, admin_token="admin-token"):
    registry = ModelProviderRegistry(Path(tempfile.mkdtemp()) / "providers.json")
    registry.create_provider({
        "name": "m", "served_model_id": "m", "base_url": "http://127.0.0.1:9/v1",
        "upstream_model": "u", "auth_mode": "none", "api_key": "", "enabled": True,
    })
    services = Services(chat=chat or FakeChat(), quiz=None, exam=exam or FakeExam(), essay=essay or FakeEssay(),
                        knowledge_base=None, client_factory=None, store=store)
    app = create_app({"TESTING": True, "AGENT_ADMIN_TOKEN": admin_token}, registry=registry, services=services)
    return app.test_client()


def rows(store, sql, *args):
    return [dict(r) for r in store._conn().execute(sql, args).fetchall()]


def ask(client, *, stream, headers=ME, mode="qa"):
    return client.post("/v1/chat/completions", headers=headers, json={
        "model": "m", "stream": stream, "mode": mode, "messages": [{"role": "user", "content": "什么是排队论？"}],
    })


# ====================== 记什么、记给谁 ======================
def test_essay_review_is_recorded_once_for_clicks_and_resubmits(store):
    essay = FakeEssay(seconds=0.2)
    client = make_client(store, essay=essay)
    body = {"model": "m", "text": PAPER, "topic": "排队论"}
    threads = [threading.Thread(target=client.post, args=("/essay/review",), kwargs={"json": body, "headers": ME})
               for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    client.post("/essay/review", json=body, headers=ME)  # 刷新后重交：走重放

    assert essay.calls == 1
    assert rows(store, "SELECT student_id, topic, text, score FROM essay_reviews") == [
        {"student_id": DEVICE, "topic": "排队论", "text": PAPER, "score": 78}
    ]
    assert rows(store, "SELECT id, name FROM students") == [{"id": DEVICE, "name": "小明"}]


@pytest.mark.parametrize("headers", [
    {},
    {"X-Tagent-Client-Id": "short"},
    {"X-Tagent-Client-Id": "has spaces in it"},
    {"X-Tagent-Client-Id": "x" * 65},
])
def test_missing_or_malformed_ids_are_recorded_anonymously(store, headers):
    response = ask(make_client(store), stream=False, headers=headers)

    assert response.status_code == 200
    assert rows(store, "SELECT student_id FROM chat_turns") == [{"student_id": None}]
    assert rows(store, "SELECT COUNT(*) AS n FROM students") == [{"n": 0}]


def test_a_garbled_name_is_dropped_but_the_device_is_kept(store):
    headers = {"X-Tagent-Client-Id": DEVICE, "X-Tagent-Client-Name": "%E5%B0"}  # 半个汉字
    ask(make_client(store), stream=False, headers=headers)
    assert rows(store, "SELECT id, name FROM students") == [{"id": DEVICE, "name": ""}]


def test_streamed_answer_is_recorded_when_it_finishes(store):
    response = ask(make_client(store), stream=True, mode="paper")
    assert b"[DONE]" in response.get_data()

    [turn] = rows(store, "SELECT student_id, mode, question, answer, finish_reason, duration_ms FROM chat_turns")
    assert turn["student_id"] == DEVICE and turn["mode"] == "paper"
    assert (turn["question"], turn["answer"], turn["finish_reason"]) == ("什么是排队论？", "排队论研究排队。", "stop")
    assert turn["duration_ms"] >= 0


def test_stopping_a_stream_midway_records_what_was_said_as_interrupted(store):
    response = ask(make_client(store), stream=True)
    chunks = response.iter_encoded()
    next(chunks)  # 角色块
    next(chunks)  # 第一个字
    response.close()  # 学生点了「停止」/ 刷新

    assert rows(store, "SELECT answer, finish_reason FROM chat_turns") == [
        {"answer": "排队论", "finish_reason": "interrupted"}
    ]


def test_upstream_failure_midway_is_recorded_as_error(store):
    response = ask(make_client(store, chat=FakeChat(fail_after=2)), stream=True)
    response.get_data()
    assert rows(store, "SELECT answer, finish_reason FROM chat_turns") == [
        {"answer": "排队论研究", "finish_reason": "error"}
    ]


def test_exam_generation_and_review_share_one_row(store):
    client = make_client(store)
    client.post("/quiz/exam/generate", json={"model": "m", "topic": "排队论"}, headers=ME)
    client.post("/quiz/exam/review", json={"model": "m", "exam_id": EXAM_ID, "answers": {"q1": "A"}}, headers=ME)

    [row] = rows(store, "SELECT student_id, title, topic, score, total_points, answers FROM exam_attempts")
    assert row == {"student_id": DEVICE, "title": "排队论测评", "topic": "排队论", "score": 64,
                   "total_points": 100, "answers": '{"q1": "A"}'}


OTHER = {"X-Tagent-Client-Id": "dev_other_student_02", "X-Tagent-Client-Name": quote("小红")}


def post_together(client, path, bodies_and_headers):
    responses = [None] * len(bodies_and_headers)

    def run(index, body, headers):
        responses[index] = client.post(path, json=body, headers=headers)

    threads = [threading.Thread(target=run, args=(i, b, h)) for i, (b, h) in enumerate(bodies_and_headers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    return responses


def test_two_students_generating_at_once_get_their_own_exams(store):
    exam = FakeExam(seconds=0.2)
    client = make_client(store, exam=exam)
    body = {"model": "m"}
    responses = post_together(client, "/quiz/exam/generate", [(body, ME), (body, OTHER)])

    ids = {r.get_json()["data"]["exam_id"] for r in responses}
    assert exam.generated == 2 and len(ids) == 2
    assert sorted(r["student_id"] for r in rows(store, "SELECT student_id FROM exam_attempts")) == sorted(
        [DEVICE, "dev_other_student_02"]
    )


def test_one_student_double_clicking_generate_still_gets_one_exam(store):
    exam = FakeExam(seconds=0.2)
    client = make_client(store, exam=exam)
    responses = post_together(client, "/quiz/exam/generate", [({"model": "m"}, ME)] * 3)

    assert exam.generated == 1
    assert len({r.get_json()["data"]["exam_id"] for r in responses}) == 1
    assert len(rows(store, "SELECT exam_id FROM exam_attempts")) == 1


def test_two_students_submitting_the_same_sample_are_both_recorded(store):
    essay = FakeEssay()
    client = make_client(store, essay=essay)
    body = {"model": "m", "text": PAPER}
    client.post("/essay/review", json=body, headers=ME)
    client.post("/essay/review", json=body, headers=OTHER)  # 90 秒内，同一篇范例

    assert essay.calls == 2
    assert sorted(r["student_id"] for r in rows(store, "SELECT student_id FROM essay_reviews")) == sorted(
        [DEVICE, "dev_other_student_02"]
    )


# ====================== 临时对话不留记录 ======================
PRIVATE = {**ME, "X-Tagent-No-Record": "1"}


def test_temporary_chats_leave_no_trace(store):
    client = make_client(store)
    ask(client, stream=True, headers=PRIVATE).get_data()
    ask(client, stream=False, headers=PRIVATE)
    client.post("/essay/review", json={"model": "m", "text": PAPER}, headers=PRIVATE)

    for table in ("chat_turns", "essay_reviews", "students"):
        assert rows(store, f"SELECT COUNT(*) AS n FROM {table}") == [{"n": 0}]


def test_cut_off_upstream_is_recorded_as_interrupted_but_sent_as_stop(store):
    from app.service.chat_service import FINISH_INTERRUPTED

    class CutOff(FakeChat):
        def stream_answer(
            self, messages, provider, notebook_ids=None, *, mode="qa", retrieval_query=None, tuning=None, on_citations=None
        ):
            yield "排队论", None
            yield "", FINISH_INTERRUPTED

    body = ask(make_client(store, chat=CutOff()), stream=True).get_data(as_text=True)

    assert '"finish_reason": "stop"' in body and FINISH_INTERRUPTED not in body
    assert rows(store, "SELECT finish_reason FROM chat_turns") == [{"finish_reason": FINISH_INTERRUPTED}]


# ====================== 记不上也不能坏事 ======================
def test_a_broken_store_never_breaks_the_request():
    client = make_client(BrokenStore())
    assert client.post("/essay/review", json={"model": "m", "text": PAPER}, headers=ME).status_code == 200
    assert ask(client, stream=False).status_code == 200
    assert b"[DONE]" in ask(client, stream=True).get_data()


def test_no_store_means_nothing_is_recorded_and_health_says_so():
    client = make_client(None)
    assert ask(client, stream=False).status_code == 200
    assert client.get("/health").get_json()["learning_store"] == "off"


# ====================== 老师接口 ======================
def admin(token="admin-token"):
    return {"X-Agent-Admin-Token": token}


def test_teacher_endpoints_need_the_admin_token(store):
    assert make_client(store, admin_token="").get("/admin/learning/summary").status_code == 503
    client = make_client(store)
    assert client.get("/admin/learning/summary").status_code == 403
    assert client.get("/admin/learning/summary", headers=admin("wrong")).status_code == 403
    assert client.post("/admin/learning/backup", headers=admin("wrong")).status_code == 403


def test_teacher_can_read_the_class_and_one_student(store):
    client = make_client(store)
    client.post("/essay/review", json={"model": "m", "text": PAPER}, headers=ME)
    ask(client, stream=False)

    summary = client.get("/admin/learning/summary", headers=admin()).get_json()
    assert summary["totals"]["essay_reviews"] == 1 and summary["totals"]["chat_turns"] == 1
    assert summary["students"][0]["name"] == "小明"

    timeline = client.get(f"/admin/learning/students/{DEVICE}?limit=5", headers=admin()).get_json()
    assert timeline["essay_reviews"][0]["review"]["overall_comment"] == "结构清楚"
    assert client.get("/admin/learning/students/nobody", headers=admin()).status_code == 404
    assert client.get("/admin/learning/summary?limit=0", headers=admin()).status_code == 400


def test_teacher_can_back_up_on_demand(store):
    response = make_client(store).post("/admin/learning/backup", headers=admin())
    assert response.status_code == 200
    assert (store.backup_dir / response.get_json()["file"]).exists()


def test_teacher_endpoints_report_a_disabled_store():
    assert make_client(None).get("/admin/learning/summary", headers=admin()).status_code == 503


def test_browser_may_send_the_identity_headers(store):
    response = make_client(store).options("/essay/review", headers={"Origin": "http://localhost:5173"})
    allowed = response.headers["Access-Control-Allow-Headers"]
    assert "X-Tagent-Client-Id" in allowed and "X-Tagent-Client-Name" in allowed
    assert "X-Tagent-No-Record" in allowed

"""私有卷落盘：basic-agent 重启（内存清空）之后，学生照样能交卷、能点开大题批注。"""

from __future__ import annotations

import time

import pytest

from app.errors.exam_errors import ExamGoneError
from app.repository import learning_store as learning_store_module
from app.repository.exam_cache import ExamCache, StoredExam
from app.repository.exam_persistence import ExamPersistence
from app.repository.learning_store import MIGRATIONS, LearningStore
from tests.test_review_exam_wiring import TEST_PROVIDER, make_exam


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "tagent.sqlite3"


def restart(db_path, **kwargs):
    """模拟重启：新开一个库连接、新建一个空的内存缓存。"""
    return ExamCache(persistence=ExamPersistence(LearningStore(db_path)), **kwargs)


def test_an_exam_survives_a_restart(db_path):
    exam = make_exam("exam-before-restart")
    restart(db_path).put(exam.exam_id, StoredExam(exam=exam, served_model_id="test-provider"))

    found = restart(db_path).get_copy(exam.exam_id)

    assert isinstance(found, StoredExam) and found.served_model_id == "test-provider"
    assert found.exam.model_dump() == exam.model_dump()


def test_grading_side_reads_the_restored_exam(db_path):
    from app.service.exam_service import ExamService

    exam = make_exam("exam-annotate")
    restart(db_path).put(exam.exam_id, StoredExam(exam=exam, served_model_id=TEST_PROVIDER.served_model_id))

    service = ExamService(knowledge_base=None, client_factory=None, exam_cache=restart(db_path))
    question, rubric = service.essay_question_for_annotation(exam.exam_id, exam.essay[0].id, TEST_PROVIDER)
    assert question == exam.essay[0].question and rubric == exam.essay[0].rubric


def test_an_expired_exam_is_still_gone_after_a_restart(db_path):
    exam = make_exam("exam-expired")
    restart(db_path, ttl_seconds=0.05).put(exam.exam_id, StoredExam(exam=exam, served_model_id="m"))
    time.sleep(0.1)
    with pytest.raises(ExamGoneError):
        restart(db_path).get_copy(exam.exam_id)


def test_a_broken_store_falls_back_to_memory_only():
    class Broken:
        def save_cached_exam(self, *args):
            raise OSError("disk full")

        def load_cached_exam(self, *args):
            raise OSError("disk I/O error")

    cache = ExamCache(persistence=ExamPersistence(Broken()))
    exam = make_exam("exam-broken-store")
    cache.put(exam.exam_id, StoredExam(exam=exam, served_model_id="m"))  # 不抛
    assert cache.get_copy(exam.exam_id).exam.exam_id == exam.exam_id  # 内存里的照样能用
    with pytest.raises(ExamGoneError):
        ExamCache(persistence=ExamPersistence(Broken())).get_copy(exam.exam_id)


def test_an_old_database_is_upgraded_and_keeps_its_records(db_path, monkeypatch):
    monkeypatch.setattr(learning_store_module, "MIGRATIONS", MIGRATIONS[:1])
    old = LearningStore(db_path)
    old.record_chat(student_id=None, mode="qa", model="m", question="升级前的提问", answer="a")
    old.close()
    monkeypatch.setattr(learning_store_module, "MIGRATIONS", MIGRATIONS)

    upgraded = LearningStore(db_path)
    assert upgraded.schema_version == len(MIGRATIONS)
    assert upgraded._conn().execute("SELECT question FROM chat_turns").fetchone()[0] == "升级前的提问"
    exam = make_exam("exam-after-upgrade")
    ExamCache(persistence=ExamPersistence(upgraded)).put(exam.exam_id, StoredExam(exam=exam, served_model_id="m"))
    assert upgraded.load_cached_exam(exam.exam_id) is not None

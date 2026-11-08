"""学习记录库（SQLite）：存得进、读得出、重启还在、崩溃不丢、并发不乱、备份可用。"""

from __future__ import annotations

import os
import signal
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from app.repository.learning_store import MIGRATIONS, LearningStore

REVIEW = {"score": 82, "dimensions": [{"key": "content", "score": 33}], "annotations": []}


@pytest.fixture
def store(tmp_path):
    instance = LearningStore(tmp_path / "data" / "tagent.sqlite3")
    yield instance
    instance.close()


def rows(store, sql, *args):
    return [dict(r) for r in store._conn().execute(sql, args).fetchall()]


# ====================== 建库 ======================
def test_creates_the_file_its_folder_and_the_current_schema(store):
    assert store.path.exists()
    assert store.schema_version == len(MIGRATIONS)
    assert store._conn().execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    tables = {r["name"] for r in rows(store, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"students", "chat_turns", "essay_reviews", "exam_attempts"} <= tables


def test_reopening_keeps_the_data_and_does_not_rerun_migrations(tmp_path):
    path = tmp_path / "tagent.sqlite3"
    first = LearningStore(path)
    first.record_chat(student_id=None, mode="qa", model="m", question="什么是排队论？", answer="研究排队的理论。")
    first.close()

    second = LearningStore(path)
    assert second.schema_version == len(MIGRATIONS)
    assert rows(second, "SELECT question FROM chat_turns") == [{"question": "什么是排队论？"}]
    second.close()


def test_a_failed_migration_rolls_back_completely(tmp_path, monkeypatch):
    from app.repository import learning_store

    path = tmp_path / "tagent.sqlite3"
    LearningStore(path).close()
    broken = [*MIGRATIONS, "CREATE TABLE half_done (id INTEGER); CREATE TABLE students (id TEXT)"]
    monkeypatch.setattr(learning_store, "MIGRATIONS", broken)

    with pytest.raises(sqlite3.OperationalError):
        LearningStore(path)

    raw = sqlite3.connect(path)
    assert raw.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    assert raw.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'half_done'").fetchone()[0] == 0
    raw.close()


# ====================== 写与读 ======================
def test_student_name_is_kept_when_a_later_request_has_none(store):
    store.touch_student("device-0001", "小明")
    store.touch_student("device-0001", "")
    assert rows(store, "SELECT id, name FROM students") == [{"id": "device-0001", "name": "小明"}]

    store.touch_student("device-0001", "李明")
    assert rows(store, "SELECT name FROM students") == [{"name": "李明"}]


def test_exam_is_one_row_from_generation_to_review(store):
    exam_id = "7b1d6d0a-1111-4222-8333-444455556666"
    store.record_exam_generated(student_id="device-0001", exam_id=exam_id, model="m", title="排队论测评",
                                topic="排队论", total_points=100, paper={"exam_id": exam_id, "questions": []})
    store.record_exam_generated(student_id="device-0001", exam_id=exam_id, model="m", title="重复的出卷记录",
                                topic=None, total_points=100)
    store.record_exam_reviewed(student_id="device-0001", exam_id=exam_id, model="m",
                               answers={"q1": "A"}, review={"total_score": 64, "total_points": 100})

    [row] = rows(store, "SELECT * FROM exam_attempts")
    assert (row["title"], row["topic"], row["score"], row["total_points"]) == ("排队论测评", "排队论", 64, 100)
    assert row["reviewed_at"] is not None and row["paper"] is not None


def test_review_without_a_generation_record_still_lands(store):
    store.record_exam_reviewed(student_id="device-0001", exam_id="e-1", model="m",
                               answers={}, review={"total_score": 10, "total_points": 100})
    assert rows(store, "SELECT score, student_id FROM exam_attempts") == [{"score": 10, "student_id": "device-0001"}]


def test_summary_and_timeline(store):
    store.touch_student("device-0001", "小明")
    store.touch_student("device-0002", "小红")
    store.record_chat(student_id="device-0001", mode="paper", model="m", question="帮我列个大纲", answer="一、引言…",
                      finish_reason="stop", notebook_ids=["nb1"], duration_ms=1200)
    store.record_essay_review(student_id="device-0001", model="m", topic="排队论", text="正文" * 60, review=REVIEW)
    store.record_essay_review(student_id="device-0001", model="m", topic=None, text="正文" * 60,
                              review={**REVIEW, "score": 70})
    store.record_exam_reviewed(student_id="device-0002", exam_id="e-1", model="m",
                               answers={"q1": "B"}, review={"total_score": 45, "total_points": 50})

    summary = store.summary()
    assert summary["totals"] == {"students": 2, "chat_turns": 1, "essay_reviews": 2, "exams_reviewed": 1}
    by_id = {s["id"]: s for s in summary["students"]}
    assert by_id["device-0001"]["essay_avg"] == 76.0
    assert by_id["device-0001"]["chat_turns"] == 1
    assert by_id["device-0002"]["exam_avg_percent"] == 90.0

    timeline = store.student_timeline("device-0001")
    assert timeline["student"]["name"] == "小明"
    assert timeline["chat_turns"][0]["mode"] == "paper"
    assert [e["score"] for e in timeline["essay_reviews"]] == [70, 82]  # 新的在前
    assert timeline["essay_reviews"][0]["review"]["dimensions"][0]["key"] == "content"  # JSON 已还原
    assert store.student_timeline("nobody")["student"] is None


def test_chinese_emoji_and_quotes_round_trip(store):
    text = "他说：“λ/μ < 1 才稳定”；DROP TABLE students; -- 😀\n第二段"
    store.record_essay_review(student_id=None, model="m", topic="'; --", text=text, review=REVIEW)
    assert rows(store, "SELECT text, topic FROM essay_reviews") == [{"text": text, "topic": "'; --"}]


# ====================== 并发 ======================
def test_many_threads_writing_at_once_lose_nothing(store):
    threads_count, per_thread = 16, 150
    errors: list[Exception] = []

    def work(worker):
        try:
            for i in range(per_thread):
                store.touch_student(f"device-{worker:04d}", f"学生{worker}")
                store.record_chat(student_id=f"device-{worker:04d}", mode="qa", model="m",
                                  question=f"q{i}", answer="a")
                if i % 10 == 0:
                    store.summary()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(threads_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)

    assert errors == []
    assert store.summary()["totals"]["chat_turns"] == threads_count * per_thread
    assert store._conn().execute("PRAGMA integrity_check").fetchone()[0] == "ok"


# ====================== 崩溃 ======================
WRITER = textwrap.dedent(
    """
    import os, sys
    from app.repository.learning_store import LearningStore

    store = LearningStore(sys.argv[1])
    ack = os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    n = 0
    while True:
        store.record_chat(student_id=None, mode="qa", model="m", question=str(n), answer="a")
        os.write(ack, f"{n}\\n".encode())   # 写库成功之后才登记
        n += 1
    """
)


@pytest.mark.skipif(os.name == "nt", reason="用 SIGKILL 模拟进程被强杀")
def test_kill_minus_nine_loses_no_acknowledged_write(tmp_path):
    path, ack = tmp_path / "tagent.sqlite3", tmp_path / "ack.txt"
    root = Path(__file__).resolve().parent.parent
    proc = subprocess.Popen([sys.executable, "-c", WRITER, str(path), str(ack)], cwd=root,
                            env={**os.environ, "PYTHONPATH": str(root)})
    deadline = time.time() + 20
    while time.time() < deadline and not (ack.exists() and ack.stat().st_size > 2000):
        time.sleep(0.05)
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait()

    acked = {line for line in ack.read_text().split()}
    assert len(acked) > 100, "写入进程没跑起来"

    survivor = LearningStore(path)
    stored = {r["question"] for r in rows(survivor, "SELECT question FROM chat_turns")}
    assert acked - stored == set()
    assert survivor._conn().execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    survivor.close()


# ====================== 备份 ======================
def test_backup_is_a_complete_usable_database(store):
    for i in range(50):
        store.record_chat(student_id=None, mode="qa", model="m", question=f"q{i}", answer="a")
    target = store.backup()

    assert target.parent == store.backup_dir
    copy = sqlite3.connect(target)
    assert copy.execute("SELECT COUNT(*) FROM chat_turns").fetchone()[0] == 50
    assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    copy.close()
    assert list(store.backup_dir.glob("*.partial")) == []


def test_only_the_newest_backups_are_kept(tmp_path):
    store = LearningStore(tmp_path / "tagent.sqlite3", backup_keep=3)
    store.backup_dir.mkdir()
    for day in range(1, 6):
        (store.backup_dir / f"tagent-2026090{day}-030000.sqlite3").write_bytes(b"old")
    newest = store.backup()

    kept = sorted(p.name for p in store.backup_dir.glob("tagent-*.sqlite3"))
    assert kept == ["tagent-20260904-030000.sqlite3", "tagent-20260905-030000.sqlite3", newest.name]
    store.close()


def test_daily_backup_runs_once_when_there_is_none_and_not_again_while_fresh(tmp_path):
    store = LearningStore(tmp_path / "tagent.sqlite3")
    store.start_daily_backup(every_s=3600, check_s=0.05)
    deadline = time.time() + 5
    while time.time() < deadline and store.latest_backup_age_s() is None:
        time.sleep(0.02)
    time.sleep(0.3)  # 再让它多转几圈：还新鲜着，不该再备

    assert len(list(store.backup_dir.glob("tagent-*.sqlite3"))) == 1
    store.close()


# ====================== 配置与装配 ======================
def test_env_picks_the_path_and_can_switch_it_off(monkeypatch, tmp_path):
    from app.config import LEARNING_DB_FILENAME, AgentConfig, default_data_dir

    monkeypatch.setenv("LEARNING_STORE", "1")
    monkeypatch.delenv("TAGENT_DB_PATH", raising=False)
    settings = AgentConfig.from_env()
    assert settings.learning_store_enabled
    assert settings.resolved_learning_db_path() == default_data_dir() / LEARNING_DB_FILENAME

    monkeypatch.setenv("TAGENT_DB_PATH", str(tmp_path / "x.sqlite3"))
    assert AgentConfig.from_env().resolved_learning_db_path() == tmp_path / "x.sqlite3"

    monkeypatch.setenv("LEARNING_STORE", "0")
    assert not AgentConfig.from_env().learning_store_enabled


def test_default_location_is_outside_the_project_folder():
    from app.config import BASE_DIR, default_data_dir

    assert BASE_DIR not in default_data_dir().parents


def test_a_store_that_cannot_open_does_not_stop_the_service(tmp_path, caplog):
    from app.config import AgentConfig
    from app.container import build_learning_store

    blocker = tmp_path / "not-a-folder"
    blocker.write_text("")
    settings = AgentConfig(learning_db_path=blocker / "tagent.sqlite3")

    assert build_learning_store(settings) is None
    assert "学习记录库打不开" in caplog.text
    assert build_learning_store(AgentConfig(learning_store_enabled=False)) is None


def test_a_corrupt_file_does_not_stop_the_service(tmp_path):
    from app.config import AgentConfig
    from app.container import build_learning_store

    path = tmp_path / "tagent.sqlite3"
    path.write_bytes(b"this is not a database" * 100)
    assert build_learning_store(AgentConfig(learning_db_path=path)) is None


# ====================== 并发打开 / 并发备份 ======================
def test_two_processes_opening_a_fresh_db_do_not_both_create_tables(tmp_path):
    """先到的建表期间，后到的读到的是旧版本号；它拿到写锁后必须复查，而不是再建一遍表。"""
    path = tmp_path / "tagent.sqlite3"
    first = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    first.execute("PRAGMA journal_mode=WAL")
    first.execute("BEGIN IMMEDIATE")
    for migration in MIGRATIONS:
        for statement in (s.strip() for s in migration.split(";")):
            if statement:
                first.execute(statement)
    first.execute(f"PRAGMA user_version={len(MIGRATIONS)}")

    def finish_later():
        time.sleep(0.3)
        first.execute("COMMIT")

    threading.Thread(target=finish_later).start()
    second = LearningStore(path)  # 读到 0 → 等写锁 → 复查发现已是最新

    assert second.schema_version == len(MIGRATIONS)
    second.record_chat(student_id=None, mode="qa", model="m", question="q", answer="a")
    second.close()
    first.close()


def test_concurrent_backups_queue_up_and_all_produce_valid_files(store):
    for i in range(30):
        store.record_chat(student_id=None, mode="qa", model="m", question=f"q{i}", answer="a")
    results, errors = [], []

    def run():
        try:
            results.append(store.backup())
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)

    assert errors == [] and len(results) == 4
    for target in set(results):
        copy = sqlite3.connect(target)
        assert copy.execute("SELECT COUNT(*) FROM chat_turns").fetchone()[0] == 30
        copy.close()
    assert list(store.backup_dir.glob("*.partial")) == []


def test_a_failed_backup_leaves_no_temporary_file(store, monkeypatch):
    class Broken:
        def backup(self, _dest):
            raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(store, "_conn", lambda: Broken())
    with pytest.raises(sqlite3.OperationalError):
        store.backup()
    assert list(store.backup_dir.iterdir()) == []

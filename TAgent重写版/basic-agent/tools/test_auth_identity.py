"""真实 SurrealDB 内存引擎验证账号与密文，不依赖现网服务。"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.fernet import Fernet

from app.auth.mail import MemoryMailer
from app.auth.personal import PersonalService
from app.auth.service import AuthService
from app.auth.store import IdentityStore
from app.errors.api_errors import AgentAPIError
from tools.init_auth_db import SCHEMA


@pytest.fixture
def identity():
    store = IdentityStore("mem://", "tagent_test", "app", "", "")
    for statement in SCHEMA:
        store.query(statement)
    mailer = MemoryMailer()
    service = AuthService(store, mailer, "http://localhost:5173")
    personal = PersonalService(store, Fernet.generate_key().decode())
    yield store, mailer, service, personal
    store.close()


def token_from(message: dict) -> str:
    url = message["body"].splitlines()[1]
    return parse_qs(urlsplit(url).query)["token"][0]


def test_registration_verification_session_and_reset(identity):
    store, mailer, service, _ = identity
    service.register(" STUDENT@EXAMPLE.ORG ", "a long test password!", "小明", "127.0.0.1")
    assert len(mailer.outbox) == 1
    with pytest.raises(AgentAPIError) as not_verified:
        service.login("student@example.org", "a long test password!", "127.0.0.1")
    assert not_verified.value.code == "email_not_verified"
    token = token_from(mailer.outbox[0])
    service.verify_email(token)
    with pytest.raises(AgentAPIError):
        service.verify_email(token)
    raw, session = service.login("student@example.org", "a long test password!", "127.0.0.1")
    assert service.session(raw).account["uid"] == session.account["uid"]
    assert raw not in str(store.query("SELECT * FROM auth_sessions"))
    service.request_reset("student@example.org")
    service.reset_password(token_from(mailer.outbox[-1]), "another long password!")
    assert service.session(raw) is None
    with pytest.raises(AgentAPIError):
        service.login("student@example.org", "a long test password!", "127.0.0.1")
    assert service.login("student@example.org", "another long password!", "127.0.0.1")


def test_password_change_invalidates_session_when_cleanup_fails(identity, monkeypatch):
    _, mailer, service, _ = identity
    service.register("student@example.org", "a long test password!", "Student", "127.0.0.1")
    service.verify_email(token_from(mailer.outbox[-1]))
    old_token, session = service.login("student@example.org", "a long test password!", "127.0.0.1")
    with monkeypatch.context() as patch:
        def fail_cleanup(_uid):
            raise OSError("cleanup failed")
        patch.setattr(service, "revoke_all", fail_cleanup)
        with pytest.raises(OSError):
            service.change_password(session.account, "a long test password!", "another long password!")
    assert service.session(old_token) is None
    with pytest.raises(AgentAPIError):
        service.login("student@example.org", "a long test password!", "127.0.0.1")
    assert service.login("student@example.org", "another long password!", "127.0.0.1")


def test_personal_data_is_encrypted_versioned_and_scoped(identity):
    store, _, service, personal = identity
    service.register("one@example.org", "a long test password!", "One", "1.1.1.1")
    account = service._account_for_email("one@example.org")
    original = {"directConnections": [{"url": "https://api.example.org", "key": "private-key"}]}
    assert personal.put(account["uid"], "settings", original, 0) == {"version": 1}
    assert personal.get(account["uid"], "settings") == {"version": 1, "data": original}
    assert "private-key" not in str(store.query("SELECT * FROM auth_personal"))
    assert "private-key" not in str(personal.export(account["uid"]))
    with pytest.raises(AgentAPIError) as conflict:
        personal.put(account["uid"], "settings", {}, 0)
    assert conflict.value.code == "version_conflict"
    personal.put(account["uid"], "qa_chats", {"chats": ["course A"]}, 0, "course-a")
    assert personal.get(account["uid"], "qa_chats", "course-b")["data"] is None


def test_registration_toggle_and_membership(identity):
    store, _, service, _ = identity
    service.set_registration_open(False)
    with pytest.raises(AgentAPIError):
        service.register("two@example.org", "a long test password!", "Two", "2.2.2.2")
    service.set_registration_open(True)
    service.register("two@example.org", "a long test password!", "Two", "2.2.2.2")
    account = service._account_for_email("two@example.org")
    store.query("CREATE auth_courses CONTENT $value", {"value": {
        "uid": "course-a", "name": "A", "active": True, "model_ids": ["m"],
        "notebook_ids": ["n"],
    }})
    assert not service.is_member(account["uid"], "course-a")
    store.query("CREATE auth_memberships CONTENT $value", {"value": {
        "account_id": account["uid"], "course_id": "course-a",
    }})
    assert service.is_member(account["uid"], "course-a")
    assert service.courses_for(account)[0]["name"] == "A"


def test_deletion_failure_can_be_retried_without_reactivating(identity):
    _, _, service, personal = identity
    service.register("delete@example.org", "a long test password!", "Delete", "3.3.3.3")
    account = service._account_for_email("delete@example.org")
    personal.put(account["uid"], "qa_chats", {"chats": []}, 0)

    class FailingLearningStore:
        def delete_student(self, _uid):
            raise OSError("temporary SQLite failure")

    with pytest.raises(OSError):
        service.delete_account(account, "a long test password!", personal, FailingLearningStore())
    pending = service.account(account["uid"])
    assert pending["active"] is False and pending["deletion_pending"] is True
    assert personal.get(account["uid"], "qa_chats")["data"] is None

    deleted = []

    class WorkingLearningStore:
        def delete_student(self, uid):
            deleted.append(uid)

    service.complete_deletion(account["uid"], personal, WorkingLearningStore())
    assert deleted == [account["uid"]]
    assert service.account(account["uid"]) is None

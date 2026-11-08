"""真实 Flask 路由和 SurrealDB 内存引擎的账号边界测试。"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.fernet import Fernet

from app.auth.mail import DisabledMailer, MemoryMailer
from app.auth.personal import PersonalService
from app.auth.service import AuthService, now_ms
from app.auth.store import IdentityStore
from app.factory import create_app
from tools.init_auth_db import SCHEMA
from tools.reset_student_password import reset_student


@pytest.fixture
def system():
    store = IdentityStore("mem://", "tagent_test", "http", "", "")
    for statement in SCHEMA:
        store.query(statement)
    mailer = MemoryMailer()
    service = AuthService(store, mailer, "http://localhost:5173")
    personal = PersonalService(store, Fernet.generate_key().decode())
    app = create_app({
        "TESTING": True, "AUTH_ENABLED": True,
        "AUTH_PUBLIC_ORIGIN": "http://localhost:5173",
        "AUTH_COOKIE_SECURE": False,
        "AUTH_STORE": store, "AUTH_SERVICE": service,
        "PERSONAL_SERVICE": personal,
    })
    yield app.test_client(), store, mailer, service
    store.close()


def register_verified(client, mailer, email="student@example.org"):
    assert client.post("/auth/register", json={
        "email": email, "password": "a sufficiently long password", "name": "Student"
    }).status_code == 202
    token = parse_qs(urlsplit(mailer.outbox[-1]["body"].splitlines()[1]).query)["token"][0]
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 200
    response = client.post("/auth/login", json={
        "email": email, "password": "a sufficiently long password"
    })
    assert response.status_code == 200
    return response.json["user"], response.json["csrf"]


def test_public_and_protected_boundary(system):
    client, _, mailer, _ = system
    assert client.get("/health").status_code == 200
    assert client.get("/auth/status").json["enabled"] is True
    assert client.get("/v1/models").status_code == 401
    account, csrf = register_verified(client, mailer)
    assert account["role"] == "student"
    assert client.get("/auth/me").json["user"]["id"] == account["id"]
    assert client.get("/v1/models").status_code == 200
    assert client.put("/me/data/qa_chats", json={"data": [], "version": 0}).status_code == 403
    assert client.put("/me/data/qa_chats", json={"data": [], "version": 0}, headers={
        "X-Tagent-CSRF": csrf, "Origin": "https://attacker.example"
    }).status_code == 403
    assert client.put("/me/data/qa_chats", json={"data": [], "version": 0}, headers={
        "X-Tagent-CSRF": csrf, "Origin": "http://localhost:5173"
    }).status_code == 200
    assert client.get("/me/data/qa_chats").json == {"data": [], "version": 1}
    assert client.post("/auth/logout", headers={"X-Tagent-CSRF": csrf}).status_code == 200
    assert client.get("/v1/models").status_code == 401


def test_course_membership_and_personal_isolation(system):
    client, store, mailer, _ = system
    account, csrf = register_verified(client, mailer)
    store.query("CREATE auth_courses CONTENT $value", {"value": {
        "uid": "course-a", "name": "Course A", "active": True,
        "model_ids": [], "notebook_ids": ["notebook-a"],
    }})
    headers = {"X-Tagent-Course-Id": "course-a", "X-Tagent-CSRF": csrf}
    assert client.get("/me/data/qa_chats", headers=headers).status_code == 403
    store.query("CREATE auth_memberships CONTENT $value", {"value": {
        "account_id": account["id"], "course_id": "course-a"
    }})
    assert client.get("/me/courses").json["courses"][0]["id"] == "course-a"
    assert client.put("/me/data/qa_chats", json={"data": {"chats": ["A"]}, "version": 0},
                      headers=headers).status_code == 200
    assert client.get("/me/data/qa_chats", headers=headers).json["data"] == {"chats": ["A"]}
    assert client.get("/me/data/qa_chats").json["data"] is None
    assert client.get("/v1/models", headers=headers).json["data"] == []


def test_admin_course_membership_and_account_revocation(system):
    student_client, store, mailer, service = system
    student, student_csrf = register_verified(student_client, mailer)
    store.query("CREATE auth_accounts CONTENT $value", {"value": {
        "uid": "admin-one", "email": "admin@example.org", "name": "Admin",
        "password_hash": service._hash("a sufficiently long admin password"),
        "role": "admin", "active": True, "verified_at": now_ms(), "created_at": now_ms(),
    }})
    admin_client = student_client.application.test_client()
    response = admin_client.post("/auth/login", json={
        "email": "admin@example.org", "password": "a sufficiently long admin password"
    })
    assert response.status_code == 200
    admin_csrf = response.json["csrf"]
    assert student_client.post("/admin/courses", json={"name": "Course A"},
                               headers={"X-Tagent-CSRF": student_csrf}).status_code == 403
    response = admin_client.post("/admin/courses", json={
        "name": "Course A", "model_ids": [], "notebook_ids": ["notebook-a"]
    }, headers={"X-Tagent-CSRF": admin_csrf})
    assert response.status_code == 201
    course_id = response.json["course"]["id"]
    assert student_client.get("/me/courses").json["courses"] == []
    assert admin_client.post(f"/admin/courses/{course_id}/members", json={
        "email": student["email"]
    }, headers={"X-Tagent-CSRF": admin_csrf}).status_code == 200
    assert student_client.get("/me/courses").json["courses"][0]["id"] == course_id
    assert student_client.put("/me/data/settings", json={
        "data": {"apiKey": "test-secret", "theme": "dark"}, "version": 0
    }, headers={"X-Tagent-CSRF": student_csrf}).status_code == 200
    exported = student_client.get("/me/export").json["personal_data"]
    assert exported[0]["data"]["apiKey"] == "[已隐藏]"
    assert admin_client.patch(f"/admin/accounts/{student['id']}", json={"active": False},
                              headers={"X-Tagent-CSRF": admin_csrf}).status_code == 200
    assert student_client.get("/me/courses").status_code == 401


def test_two_devices_and_shared_browser_account_boundary(system, monkeypatch):
    browser, _, mailer, service = system
    first, first_csrf = register_verified(browser, mailer, "first@example.org")
    other_device = browser.application.test_client()
    second_session = other_device.post("/auth/login", json={
        "email": first["email"], "password": "a sufficiently long password"
    })
    assert second_session.status_code == 200
    assert browser.put("/me/data/qa_chats", json={
        "data": {"chats": [{"id": "first-chat"}]}, "version": 0
    }, headers={"X-Tagent-CSRF": first_csrf}).status_code == 200
    assert other_device.get("/me/data/qa_chats").json["data"]["chats"][0]["id"] == "first-chat"
    assert other_device.put("/me/data/qa_chats", json={
        "data": {"chats": []}, "version": 0
    }, headers={"X-Tagent-CSRF": second_session.json["csrf"]}).status_code == 409

    assert browser.post("/auth/logout", headers={"X-Tagent-CSRF": first_csrf}).status_code == 200
    assert browser.get("/me/data/qa_chats").status_code == 401
    assert other_device.get("/me/data/qa_chats").status_code == 200
    second, _ = register_verified(browser, mailer, "second@example.org")
    assert second["id"] != first["id"]
    assert browser.get("/me/data/qa_chats").json["data"] is None
    assert other_device.get("/me/data/qa_chats").json["data"]["chats"][0]["id"] == "first-chat"

    with monkeypatch.context() as patch:
        def fail_session(_token):
            raise OSError("identity database unavailable")
        patch.setattr(service, "session", fail_session)
        assert other_device.get("/me/data/qa_chats").status_code == 503
    assert other_device.get("/me/data/qa_chats").status_code == 200


def test_username_self_registration_without_smtp_and_cross_device_sync():
    store = IdentityStore("mem://", "tagent_test", "no_mail", "", "")
    try:
        for statement in SCHEMA:
            store.query(statement)
        service = AuthService(store, DisabledMailer(), "http://localhost:5173")
        personal = PersonalService(store, Fernet.generate_key().decode())
        app = create_app({
            "TESTING": True, "AUTH_ENABLED": True,
            "AUTH_PUBLIC_ORIGIN": "http://localhost:5173", "AUTH_COOKIE_SECURE": False,
            "AUTH_STORE": store, "AUTH_SERVICE": service, "PERSONAL_SERVICE": personal,
        })
        first_device = app.test_client()
        second_device = app.test_client()
        status = first_device.get("/auth/status").json
        assert status["registration_open"] is True
        assert status["registration_method"] == "username"
        assert status["password_reset_available"] is False
        service.set_registration_open(False)
        assert first_device.post("/auth/register", json={
            "username": "closed.user", "password": "a sufficiently long password"
        }).status_code == 403
        service.set_registration_open(True)
        assert first_device.post("/auth/register", json={
            "username": "  Student.One  ", "password": "a sufficiently long password", "name": "One"
        }).status_code == 201
        assert first_device.post("/auth/register", json={
            "username": "student.one", "password": "another long password", "name": "Copy"
        }).status_code == 409
        assert first_device.post("/auth/register", json={
            "username": "bad@name", "password": "a sufficiently long password"
        }).status_code == 400
        assert first_device.post("/auth/password/forgot", json={
            "email": "nobody@example.org"
        }).status_code == 503
        assert first_device.post("/auth/verify-email", json={"token": "ignored"}).status_code == 503
        assert first_device.post("/auth/password/reset", json={
            "token": "ignored", "password": "a sufficiently long password"
        }).status_code == 503
        first_login = first_device.post("/auth/login", json={
            "identifier": "student.one", "password": "a sufficiently long password"
        })
        assert first_login.status_code == 200
        assert first_login.json["user"]["username"] == "student.one"
        assert first_login.json["user"]["email"] is None
        second_login = second_device.post("/auth/login", json={
            "identifier": "student.one", "password": "a sufficiently long password"
        })
        assert second_login.status_code == 200
        assert first_device.put("/me/data/qa_chats", json={
            "data": {"chats": [{"id": "saved-on-first-device"}]}, "version": 0
        }, headers={"X-Tagent-CSRF": first_login.json["csrf"]}).status_code == 200
        assert second_device.get("/me/data/qa_chats").json["data"]["chats"][0]["id"] == "saved-on-first-device"
        assert first_device.post("/auth/logout", headers={
            "X-Tagent-CSRF": first_login.json["csrf"]
        }).status_code == 200
        assert first_device.post("/auth/register", json={
            "username": "other.student", "password": "a sufficiently long password", "name": "Other"
        }).status_code == 201
        assert first_device.post("/auth/login", json={
            "identifier": "other.student", "password": "a sufficiently long password"
        }).status_code == 200
        assert first_device.get("/me/data/qa_chats").json["data"] is None
        store.query("CREATE auth_accounts CONTENT $value", {"value": {
            "uid": "admin-no-mail", "email": "admin@example.org", "name": "Admin",
            "password_hash": service._hash("a sufficiently long admin password"),
            "role": "admin", "active": True, "verified_at": now_ms(), "created_at": now_ms(),
        }})
        admin_device = app.test_client()
        admin_login = admin_device.post("/auth/login", json={
            "identifier": "admin@example.org", "password": "a sufficiently long admin password"
        })
        assert admin_login.status_code == 200
        admin_csrf = admin_login.json["csrf"]
        created = admin_device.post("/admin/courses", json={"name": "Course A"},
                                    headers={"X-Tagent-CSRF": admin_csrf})
        assert created.status_code == 201
        course_id = created.json["course"]["id"]
        assert admin_device.post(f"/admin/courses/{course_id}/members", json={
            "identifier": "student.one"
        }, headers={"X-Tagent-CSRF": admin_csrf}).status_code == 200
        assert second_device.get("/me/courses").json["courses"][0]["id"] == course_id
        reset_student(store, "student.one", "a new sufficiently long password")
        assert second_device.get("/me/data/qa_chats").status_code == 401
        assert second_device.post("/auth/login", json={
            "identifier": "student.one", "password": "a sufficiently long password"
        }).status_code == 401
        assert second_device.post("/auth/login", json={
            "identifier": "student.one", "password": "a new sufficiently long password"
        }).status_code == 200
        assert second_device.get("/me/data/qa_chats").json["data"]["chats"][0]["id"] == "saved-on-first-device"
    finally:
        store.close()

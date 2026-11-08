"""账号规则。数据库只保存口令哈希、一次性令牌哈希和会话哈希。"""

from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from argon2 import PasswordHasher, exceptions as argon_errors

from app.errors.api_errors import AgentAPIError


_EMAIL = re.compile(r"^[^\s@]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,63}$")
_USERNAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")
_PASSWORD = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
_GENERIC_LOGIN = "账号或密码不正确，或账号暂不可用。"
_DUMMY_HASH = _PASSWORD.hash("this account is intentionally unavailable")
_PASSWORD_SLOTS = threading.BoundedSemaphore(4)


@contextmanager
def password_slot():
    # Argon2 每次约 19 MiB；200 人同时登录时不能让 200 次校验一起分配内存。
    if not _PASSWORD_SLOTS.acquire(timeout=10):
        raise AgentAPIError("登录请求较多，请稍后重试。", 429, "auth_busy")
    try:
        yield
    finally:
        _PASSWORD_SLOTS.release()


def now_ms() -> int:
    return int(time.time() * 1000)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def public_account(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["uid"],
        "email": row.get("email"),
        "username": row.get("username"),
        "name": row.get("name", ""),
        "role": row["role"],
        "verified": bool(row.get("verified_at")),
        "active": bool(row.get("active", True)),
        "deletion_pending": bool(row.get("deletion_pending")),
    }


@dataclass(frozen=True)
class Session:
    account: dict[str, Any]
    csrf: str
    digest: str
    expires_at: int


class AuthService:
    def __init__(self, store, mailer, public_origin: str, *, registration_open: bool = True):
        self.store = store
        self.mailer = mailer
        self.public_origin = public_origin.rstrip("/")
        self.registration_open = registration_open
        self._event_count = 0
        self._event_lock = threading.Lock()

    def _account_for_email(self, email: str):
        return self.store.first(
            "SELECT * FROM auth_accounts WHERE email = $email LIMIT 1", {"email": email}
        )

    def _account_for_username(self, username: str):
        return self.store.first(
            "SELECT * FROM auth_accounts WHERE username = $username LIMIT 1", {"username": username}
        )

    def _account_for_identifier(self, identifier: str):
        return (self._account_for_email(identifier) if "@" in identifier
                else self._account_for_username(identifier))

    def account(self, uid: str):
        return self.store.first("SELECT * FROM auth_accounts WHERE uid = $uid LIMIT 1", {"uid": uid})

    def _event(self, kind: str, subject: str) -> None:
        self.store.query(
            "CREATE auth_events CONTENT $value RETURN NONE",
            {"value": {"kind": kind, "subject": digest(subject), "at": now_ms()}},
        )
        with self._event_lock:
            self._event_count += 1
            prune = self._event_count % 1000 == 0
        if prune:
            try:
                self.store.query("DELETE auth_events WHERE at < $cutoff RETURN NONE",
                                 {"cutoff": now_ms() - 2 * 24 * 60 * 60_000})
            except Exception:
                # 清理失败不改变当前注册或登录请求的结果，下次仍会重试。
                pass

    def _limit(self, kind: str, subject: str, count: int, window_ms: int) -> None:
        rows = self.store.first(
            "SELECT count() AS attempts FROM auth_events WHERE kind = $kind "
            "AND subject = $subject AND at > $since GROUP ALL",
            {"kind": kind, "subject": digest(subject), "since": now_ms() - window_ms},
        )
        if rows and int(rows.get("attempts", 0)) >= count:
            raise AgentAPIError("请稍后再试。", 429, "rate_limited")

    @staticmethod
    def email(value: str) -> str:
        email = value.strip().lower() if isinstance(value, str) else ""
        if len(email) > 254 or not _EMAIL.fullmatch(email):
            raise AgentAPIError("请输入有效邮箱。", 400, "invalid_email")
        return email

    @staticmethod
    def username(value: str) -> str:
        username = value.strip().lower() if isinstance(value, str) else ""
        if not _USERNAME.fullmatch(username):
            raise AgentAPIError("用户名需为 3～32 位英文字母、数字、下划线、点或连字符，且以字母或数字开头。", 400, "invalid_username")
        return username

    @staticmethod
    def password(value: str) -> str:
        if not isinstance(value, str) or not 12 <= len(value) <= 256:
            raise AgentAPIError("密码长度应为 12～256 个字符。", 400, "invalid_password")
        return value

    @staticmethod
    def _hash(password: str) -> str:
        with password_slot():
            return _PASSWORD.hash(password)

    def register(self, identifier: str, password: str, name: str, ip: str) -> None:
        if not self.registration_is_open():
            raise AgentAPIError("注册暂未开放。", 403, "registration_closed")
        if not self.mailer.can_send:
            username = self.username(identifier)
            password = self.password(password)
            name = name.strip()[:40] if isinstance(name, str) else ""
            self._limit("register_ip", ip, 20, 60 * 60_000)
            self._event("register_ip", ip)
            if self._account_for_username(username):
                raise AgentAPIError("该用户名已被使用。", 409, "username_taken")
            try:
                self.store.query("CREATE auth_accounts CONTENT $value", {"value": {
                    "uid": str(uuid.uuid4()), "username": username, "name": name,
                    "password_hash": self._hash(password), "role": "student",
                    "active": True, "verified_at": now_ms(), "created_at": now_ms(),
                }})
            except Exception as exc:
                if self._account_for_username(username):
                    raise AgentAPIError("该用户名已被使用。", 409, "username_taken") from exc
                raise
            return
        email = self.email(identifier)
        password = self.password(password)
        name = name.strip()[:40] if isinstance(name, str) else ""
        self._limit("register_ip", ip, 300, 60 * 60_000)
        self._limit("register_email", email, 3, 60 * 60_000)
        self._event("register_ip", ip)
        self._event("register_email", email)
        row = self._account_for_email(email)
        if row is None:
            uid = str(uuid.uuid4())
            try:
                self.store.query(
                    "CREATE auth_accounts CONTENT $value",
                    {"value": {
                        "uid": uid, "email": email, "name": name,
                        "password_hash": self._hash(password), "role": "student",
                        "active": True, "verified_at": None, "created_at": now_ms(),
                    }},
                )
            except Exception:
                # 并发注册同邮箱由数据库 UNIQUE 约束裁决；对外仍给相同答复。
                if self._account_for_email(email) is None:
                    raise
            row = self._account_for_email(email)
        if row and not row.get("verified_at") and row.get("active", True):
            self._send_token(row, "verify", 24 * 60 * 60_000)

    def registration_is_open(self) -> bool:
        row = self.store.first("SELECT * FROM auth_config WHERE key = 'registration' LIMIT 1")
        return bool(row["open"]) if row else self.registration_open

    def set_registration_open(self, enabled: bool) -> None:
        row = self.store.first("SELECT * FROM auth_config WHERE key = 'registration' LIMIT 1")
        if row:
            self.store.query(
                "UPDATE auth_config SET open = $enabled WHERE key = 'registration'",
                {"enabled": enabled},
            )
        else:
            self.store.query(
                "CREATE auth_config CONTENT $value",
                {"value": {"key": "registration", "open": enabled}},
            )

    def _send_token(self, account: dict, kind: str, lifetime_ms: int) -> None:
        token = secrets.token_urlsafe(32)
        self.store.query(
            "CREATE auth_tokens CONTENT $value",
            {"value": {
                "digest": digest(token), "account_id": account["uid"], "kind": kind,
                "expires_at": now_ms() + lifetime_ms,
            }},
        )
        endpoint = "verify-email" if kind == "verify" else "reset-password"
        link = f"{self.public_origin}/{endpoint}?token={token}"
        subject = "TAgent 验证邮箱" if kind == "verify" else "TAgent 重置密码"
        self.mailer.send(account["email"], subject, f"请打开以下链接完成操作：\n{link}\n")

    def request_reset(self, email: str) -> None:
        if not self.mailer.can_send:
            raise AgentAPIError("暂未启用邮件找回，请联系管理员。", 503, "mail_unavailable")
        email = self.email(email)
        self._limit("reset", email, 3, 60 * 60_000)
        self._event("reset", email)
        row = self._account_for_email(email)
        if row and row.get("verified_at") and row.get("active", True):
            self._send_token(row, "reset", 30 * 60_000)

    def _consume(self, token: str, kind: str) -> dict:
        if not isinstance(token, str) or len(token) > 256:
            raise AgentAPIError("链接无效或已过期。", 400, "invalid_token")
        row = self.store.first(
            "DELETE auth_tokens WHERE digest = $digest AND kind = $kind "
            "AND expires_at > $now RETURN BEFORE",
            {"digest": digest(token), "kind": kind, "now": now_ms()},
        )
        if not row:
            raise AgentAPIError("链接无效或已过期。", 400, "invalid_token")
        account = self.account(row["account_id"])
        if not account or not account.get("active", True):
            raise AgentAPIError("账号不可用。", 403, "account_disabled")
        return account

    def verify_email(self, token: str) -> None:
        if not self.mailer.can_send:
            raise AgentAPIError("当前未启用邮箱验证。", 503, "mail_unavailable")
        account = self._consume(token, "verify")
        self.store.query(
            "UPDATE auth_accounts SET verified_at = $at WHERE uid = $uid",
            {"at": now_ms(), "uid": account["uid"]},
        )

    def reset_password(self, token: str, password: str) -> None:
        if not self.mailer.can_send:
            raise AgentAPIError("当前未启用邮件找回。", 503, "mail_unavailable")
        password = self.password(password)
        account = self._consume(token, "reset")
        self.store.query(
            "UPDATE auth_accounts SET password_hash = $hash WHERE uid = $uid",
            {"hash": self._hash(password), "uid": account["uid"]},
        )
        self.revoke_all(account["uid"])

    def login(self, identifier: str, password: str, ip: str) -> tuple[str, Session]:
        identifier = self.email(identifier) if isinstance(identifier, str) and "@" in identifier else self.username(identifier)
        self._limit("login_identifier", identifier, 5, 15 * 60_000)
        self._limit("login_ip", ip, 1000, 15 * 60_000)
        account = self._account_for_identifier(identifier)
        valid = False
        if isinstance(password, str):
            try:
                with password_slot():
                    valid = _PASSWORD.verify(account["password_hash"] if account else _DUMMY_HASH, password)
            except (argon_errors.VerifyMismatchError, argon_errors.VerificationError):
                pass
        if not valid or not account or not account.get("active", True):
            self._event("login_identifier", identifier)
            self._event("login_ip", ip)
            raise AgentAPIError(_GENERIC_LOGIN, 401, "invalid_credentials")
        if not account.get("verified_at"):
            raise AgentAPIError("请先验证邮箱。", 403, "email_not_verified")
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        now = now_ms()
        expires = now + (24 * 60 * 60_000 if account["role"] == "admin" else 7 * 24 * 60 * 60_000)
        self.store.query(
            "CREATE auth_sessions CONTENT $value",
            {"value": {
                "digest": digest(token), "account_id": account["uid"], "csrf": csrf,
                "created_at": now, "last_seen_at": now, "expires_at": expires,
            }},
        )
        return token, Session(account, csrf, digest(token), expires)

    def session(self, token: str) -> Session | None:
        if not token or len(token) > 256:
            return None
        row = self.store.first(
            "SELECT * FROM auth_sessions WHERE digest = $digest AND expires_at > $now LIMIT 1",
            {"digest": digest(token), "now": now_ms()},
        )
        if not row:
            return None
        account = self.account(row["account_id"])
        if not account or not account.get("active", True) or not account.get("verified_at"):
            return None
        idle = 30 * 60_000 if account["role"] == "admin" else 12 * 60 * 60_000
        if int(row["last_seen_at"]) + idle < now_ms():
            self.revoke_digest(row["digest"])
            return None
        if int(row["last_seen_at"]) + 60_000 < now_ms():
            self.store.query(
                "UPDATE auth_sessions SET last_seen_at = $at WHERE digest = $digest",
                {"at": now_ms(), "digest": row["digest"]},
            )
        return Session(account, row["csrf"], row["digest"], int(row["expires_at"]))

    def revoke_digest(self, token_digest: str) -> None:
        self.store.query("DELETE auth_sessions WHERE digest = $digest", {"digest": token_digest})

    def revoke_all(self, account_id: str) -> None:
        self.store.query("DELETE auth_sessions WHERE account_id = $uid", {"uid": account_id})

    def courses_for(self, account: dict) -> list[dict]:
        if account["role"] == "admin":
            return self.store.query("SELECT * FROM auth_courses WHERE active = true ORDER BY name") or []
        memberships = self.store.query(
            "SELECT course_id FROM auth_memberships WHERE account_id = $uid",
            {"uid": account["uid"]},
        ) or []
        return [course for item in memberships
                if (course := self.course(item["course_id"])) is not None]

    def course(self, uid: str) -> dict | None:
        return self.store.first(
            "SELECT * FROM auth_courses WHERE uid = $uid AND active = true LIMIT 1", {"uid": uid}
        )

    def is_member(self, account_id: str, course_id: str) -> bool:
        return bool(self.store.first(
            "SELECT * FROM auth_memberships WHERE account_id = $account AND course_id = $course LIMIT 1",
            {"account": account_id, "course": course_id},
        ))

    def delete_account(self, account: dict, password: str, personal, learning_store=None) -> None:
        if account["role"] == "admin":
            raise AgentAPIError("管理员账号不能自行注销。", 403, "admin_protected")
        if learning_store is None:
            raise AgentAPIError("学习记录库不可用，暂不能注销。", 503, "learning_store_unavailable")
        try:
            with password_slot():
                valid = _PASSWORD.verify(account["password_hash"], password)
        except (argon_errors.VerifyMismatchError, argon_errors.VerificationError, TypeError):
            valid = False
        if not valid:
            raise AgentAPIError("密码不正确。", 403, "invalid_credentials")
        uid = account["uid"]
        # 先停用和撤销会话。之后任一步失败，账号仍不能被登录，管理员可重试清理。
        self.store.query(
            "UPDATE auth_accounts SET active = false, deletion_pending = true WHERE uid = $uid",
            {"uid": uid},
        )
        self.revoke_all(uid)
        self.complete_deletion(uid, personal, learning_store)

    def complete_deletion(self, uid: str, personal, learning_store=None) -> None:
        """仅重试已停用的待注销账号；不会误删仍在使用的账号。"""
        account = self.account(uid)
        if not account or account.get("active", True) or not account.get("deletion_pending"):
            raise AgentAPIError("账号不在待注销状态。", 409, "not_pending_deletion")
        if learning_store is None:
            raise AgentAPIError("学习记录库不可用，暂不能完成注销。", 503, "learning_store_unavailable")
        personal.delete(uid)
        self.store.query("DELETE auth_memberships WHERE account_id = $uid", {"uid": uid})
        self.store.query("DELETE auth_tokens WHERE account_id = $uid", {"uid": uid})
        learning_store.delete_student(uid)
        self.store.query("DELETE auth_accounts WHERE uid = $uid", {"uid": uid})

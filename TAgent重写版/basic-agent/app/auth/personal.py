"""账号个人内容。服务端是唯一持久副本，密文在 TAgent 数据库中保存。"""

from __future__ import annotations

import json
import re
from typing import Any

from cryptography.fernet import Fernet, MultiFernet

from app.errors.api_errors import AgentAPIError


KINDS = {"settings", "qa_chats", "qa_folders", "workspace", "controls"}
GLOBAL_KINDS = {"settings", "controls"}
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
SECRET_FIELDS = {"key", "apikey", "token", "accesstoken", "refreshtoken", "secret", "clientsecret", "password", "authorization"}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: ("[已隐藏]" if re.sub(r"[^a-z0-9]", "", key.lower()) in SECRET_FIELDS else redact(item))
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class PersonalService:
    def __init__(self, store, keys: str):
        parsed = [item.strip().encode("ascii") for item in keys.split(",") if item.strip()]
        if not parsed:
            raise ValueError("TAGENT_DATA_KEYS is required for personal data encryption")
        self.store = store
        self.crypto = MultiFernet([Fernet(key) for key in parsed])

    @staticmethod
    def context(kind: str, course_id: str | None) -> str:
        if kind not in KINDS:
            raise AgentAPIError("未知的个人数据类型。", 404, "unknown_data_kind")
        return "global" if kind in GLOBAL_KINDS else (course_id or "general")

    def _find(self, account_id: str, context_id: str, kind: str):
        return self.store.first(
            "SELECT * FROM auth_personal WHERE account_id = $account "
            "AND context_id = $context AND kind = $kind LIMIT 1",
            {"account": account_id, "context": context_id, "kind": kind},
        )

    def get(self, account_id: str, kind: str, course_id: str | None = None) -> dict:
        context_id = self.context(kind, course_id)
        row = self._find(account_id, context_id, kind)
        if not row:
            return {"version": 0, "data": None}
        try:
            data = json.loads(self.crypto.decrypt(row["ciphertext"].encode("ascii")))
        except Exception as exc:
            raise AgentAPIError("个人数据无法解密，请联系管理员。", 503, "data_key_unavailable") from exc
        return {"version": int(row["version"]), "data": data}

    def put(self, account_id: str, kind: str, data: Any, version: int,
            course_id: str | None = None) -> dict:
        context_id = self.context(kind, course_id)
        if not isinstance(version, int) or isinstance(version, bool) or version < 0:
            raise AgentAPIError("数据版本无效。", 400, "invalid_version")
        try:
            encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise AgentAPIError("个人数据格式无效。", 400, "invalid_data") from exc
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise AgentAPIError("这份个人数据太大。", 413, "data_too_large")
        ciphertext = self.crypto.encrypt(encoded).decode("ascii")
        params = {
            "account": account_id, "context": context_id, "kind": kind,
            "ciphertext": ciphertext, "version": version,
        }
        if version == 0:
            if self._find(account_id, context_id, kind):
                raise AgentAPIError("另一台设备已更新，请刷新后重试。", 409, "version_conflict")
            try:
                self.store.query(
                    "CREATE auth_personal CONTENT $value",
                    {"value": {
                        "account_id": account_id, "context_id": context_id, "kind": kind,
                        "version": 1, "ciphertext": ciphertext,
                    }},
                )
            except Exception as exc:
                if self._find(account_id, context_id, kind):
                    raise AgentAPIError("另一台设备已更新，请刷新后重试。", 409, "version_conflict") from exc
                raise
            return {"version": 1}
        rows = self.store.query(
            "UPDATE auth_personal SET ciphertext = $ciphertext, version = version + 1 "
            "WHERE account_id = $account AND context_id = $context AND kind = $kind "
            "AND version = $version RETURN AFTER",
            params,
        )
        if not rows:
            raise AgentAPIError("另一台设备已更新，请刷新后重试。", 409, "version_conflict")
        return {"version": version + 1}

    def export(self, account_id: str) -> dict:
        rows = self.store.query(
            "SELECT context_id, kind, version, ciphertext FROM auth_personal WHERE account_id = $account",
            {"account": account_id},
        ) or []
        content = []
        for row in rows:
            data = json.loads(self.crypto.decrypt(row["ciphertext"].encode("ascii")))
            content.append({
                "context": row["context_id"], "kind": row["kind"],
                "version": row["version"], "data": redact(data),
            })
        return {"personal_data": content}

    def delete(self, account_id: str) -> None:
        self.store.query("DELETE auth_personal WHERE account_id = $account", {"account": account_id})

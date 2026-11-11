"""记录编号：保持原版 SurrealDB 的「表名:20 位小写字母数字」，前端和 tagent 都按这个格式认。"""

from __future__ import annotations

import re
import secrets
import string

_ALPHABET = string.ascii_lowercase + string.digits
_KEY = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def new_id(table: str) -> str:
    return f"{table}:{''.join(secrets.choice(_ALPHABET) for _ in range(20))}"


def normalize(table: str, raw: str | None) -> str | None:
    """`xxx` 或 `table:xxx` → `table:xxx`；别的表的编号或格式不对就回 None。"""
    value = (raw or "").strip()
    if not value:
        return None
    if ":" in value:
        prefix, _, key = value.partition(":")
        if prefix != table:
            return None
    else:
        key = value
    if not _KEY.match(key):
        return None
    return f"{table}:{key}"

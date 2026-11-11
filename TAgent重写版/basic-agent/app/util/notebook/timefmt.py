"""时间：库里存毫秒整数（照 tagent 的 learning_store），对外输出原版的字符串格式。

原版直接 str(datetime)，形如 `2026-11-11 08:00:00.123000+00:00`，前端拿它 new Date()。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone


def now_ms() -> int:
    return int(time.time() * 1000)


def fmt(ms: int | None) -> str | None:
    if ms is None:
        return None
    return str(datetime.fromtimestamp(ms / 1000, tz=timezone.utc))

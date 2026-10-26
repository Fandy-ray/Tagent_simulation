"""一次运行的依赖与预算。

依赖不进图的状态：模型客户端、知识库这些对象既不能序列化，也不该每一步都
被复制一遍。它们放在 AgentDeps 里，随一次运行传给各个节点。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.schema.provider import ModelProvider


# 留给 call_json_llm 的余量。它在「剩余预算 < 单次超时 + 取消宽限(5s)」时
# 会直接判预算不足、一次都不尝试就抛 504（实测过 0.9 秒即 504），
# 所以单次超时必须比剩余预算再少一截。这条原来在 7 处各抄了一份。
ATTEMPT_MARGIN_SECONDS = 15.0

# 分路并发的图（整卷 7 路、闪卡各片、判卷各批、小论文三维）同时最多跑几路。各路几乎都在等上游回答，
# 不占 CPU；不写的话 LangGraph 用 Python 线程池的默认大小「CPU 核数 + 4」，2 核的云服务器上只有 6 个，
# 整卷的第 7 路要等前面写完才发出去，出一张卷的时间翻倍（2026-10-26 部署到 2 核服务器时测出）
FANOUT_MAX_CONCURRENCY = 16


def attempt_timeout(limit: float, floor: float, budget: float) -> float:
    """单次调用的超时：不超过 limit，不低于 floor，并给预算留出余量。"""
    return min(limit, max(floor, budget - ATTEMPT_MARGIN_SECONDS))


@dataclass(frozen=True)
class AgentDeps:
    knowledge_base: Any
    client_factory: Any
    provider: ModelProvider
    deadline: float
    tuning: dict | None = field(default=None)

    @classmethod
    def start(
        cls,
        *,
        knowledge_base: Any,
        client_factory: Any,
        provider: ModelProvider,
        budget_seconds: float,
        tuning: dict | None = None,
    ) -> "AgentDeps":
        """从现在起算截止时间。整次运行共用这一个截止时间。"""
        return cls(
            knowledge_base=knowledge_base,
            client_factory=client_factory,
            provider=provider,
            deadline=time.monotonic() + budget_seconds,
            tuning=tuning,
        )

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

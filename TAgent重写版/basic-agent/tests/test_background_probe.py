"""后台探活：读永不阻塞。

守的是「/knowledge 在 OpenNotebook 断连时一次请求要等 15~20 秒」这个问题。
这接口不调模型，前端每次打开答疑页都会调，不该有任何可感知延迟。
"""

from __future__ import annotations

import threading
import time

import pytest

from app.infra.background_probe import BackgroundProbe


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Deferred:
    """把后台任务攒起来，由用例决定什么时候跑——免得单测依赖线程时序。"""

    def __init__(self):
        self.pending: list = []

    def __call__(self, work) -> None:
        self.pending.append(work)

    def run_all(self) -> int:
        count = len(self.pending)
        for work in self.pending:
            work()
        self.pending.clear()
        return count


def make(probe, ttl=30.0):
    clock, spawn = Clock(), Deferred()
    return BackgroundProbe(probe, ttl_seconds=ttl, clock=clock, spawn=spawn), clock, spawn


def test_first_read_is_unknown_and_does_not_block():
    # 第一次没有缓存就返回「未知」，而不是把请求卡在探测上
    slow_calls = []
    probe, _clock, spawn = make(lambda: slow_calls.append(1) or True)

    assert probe.value() is None
    assert slow_calls == [], "读的时候不该已经探过了"
    assert len(spawn.pending) == 1, "该丢了一个后台任务"


def test_value_is_available_after_the_background_run():
    probe, _clock, spawn = make(lambda: True)
    probe.value()
    spawn.run_all()
    assert probe.value() is True


def test_fresh_value_does_not_trigger_another_probe():
    calls = []
    probe, clock, spawn = make(lambda: calls.append(1) or True, ttl=30.0)
    probe.value()
    spawn.run_all()

    clock.advance(10)
    assert probe.value() is True
    assert spawn.run_all() == 0, "还没过期就不该再探"
    assert len(calls) == 1


def test_stale_value_triggers_a_refresh_but_still_returns_immediately():
    results = [True, False]
    probe, clock, spawn = make(lambda: results.pop(0), ttl=30.0)
    probe.value()
    spawn.run_all()

    clock.advance(31)
    # 过期这一次仍然立刻返回**旧值**，不等探测
    assert probe.value() is True
    spawn.run_all()
    assert probe.value() is False


def test_a_failing_probe_counts_as_unreachable_and_never_raises():
    def boom():
        raise RuntimeError("连不上")

    probe, _clock, spawn = make(boom)
    assert probe.value() is None
    spawn.run_all()
    assert probe.value() is False


def test_only_one_probe_runs_at_a_time():
    # 断连时每次探测都要耗很久，不限流会把线程堆满
    calls = []
    probe, clock, spawn = make(lambda: calls.append(1) or True, ttl=0.0)
    for _ in range(5):
        probe.value()
    assert len(spawn.pending) == 1, "同一时刻只该有一个探测在排队"
    spawn.run_all()
    assert len(calls) == 1


def test_a_slow_probe_does_not_slow_down_the_read():
    """真线程版：探测睡 1 秒，读必须立刻回。"""

    def slow():
        time.sleep(1.0)
        return True

    probe = BackgroundProbe(slow, ttl_seconds=30.0)
    started = time.monotonic()
    value = probe.value()
    elapsed = time.monotonic() - started

    assert value is None
    assert elapsed < 0.1, f"读阻塞了 {elapsed:.2f}s，后台探活就白做了"


def test_refresh_now_is_synchronous_for_warm_up():
    probe = BackgroundProbe(lambda: True, ttl_seconds=30.0)
    assert probe.refresh_now() is True
    assert probe.value() is True


def test_concurrent_reads_are_safe():
    probe = BackgroundProbe(lambda: True, ttl_seconds=0.0)
    errors: list[Exception] = []

    def hammer():
        try:
            for _ in range(50):
                probe.value()
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []


def test_a_failed_spawn_does_not_wedge_the_probe_forever():
    """起不来线程时必须把「有人在刷」的标记放回去。

    不放的话这个探活就永久卡死：之后每次调用都认为有后台任务在跑，
    接口一直返回旧值，再也不会重试——而这正是连不上笔记本时最需要刷新的时候。
    """
    attempts = []

    def refuses_once(work):
        attempts.append(work)
        if len(attempts) == 1:
            raise RuntimeError("can't start new thread")
        work()

    probe = BackgroundProbe(lambda: True, ttl_seconds=0.0, clock=Clock(), spawn=refuses_once)

    assert probe.value() is None
    assert probe.value() is True, "第一次起线程失败后该还能再试，而不是永久卡住"

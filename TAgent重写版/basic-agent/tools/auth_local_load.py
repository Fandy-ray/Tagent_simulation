"""仅对本机夹具做 100/200 用户登录与轻量 GET 突发测试，输出逐请求和逐秒记录。"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import psutil


def percentile(values: list[float], percent: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 1)


async def run_tier(base: str, users: int, backend_pid: int) -> tuple[list[dict], list[dict], dict]:
    backend = psutil.Process(backend_pid)
    client_process = psutil.Process()
    backend.cpu_percent(None)
    client_process.cpu_percent(None)
    stopped = asyncio.Event()
    finished = asyncio.Event()
    request_rows: list[dict] = []
    resource_rows: list[dict] = []
    in_flight = 0
    peak_in_flight = 0

    async def monitor():
        low_since: float | None = None
        while not finished.is_set():
            now = time.time()
            memory = psutil.virtual_memory()
            alive = backend.is_running() and backend.status() != psutil.STATUS_ZOMBIE
            row = {
                "at": now, "backend_alive": alive,
                "backend_rss_mib": round(backend.memory_info().rss / 1024**2, 1) if alive else None,
                "backend_cpu_percent": backend.cpu_percent(None) if alive else None,
                "client_rss_mib": round(client_process.memory_info().rss / 1024**2, 1),
                "client_cpu_percent": client_process.cpu_percent(None),
                "available_memory_percent": round(memory.available * 100 / memory.total, 2),
                "in_flight": in_flight,
            }
            resource_rows.append(row)
            if not alive:
                stopped.set()
            if memory.available < memory.total * 0.2:
                low_since = low_since or time.monotonic()
                if time.monotonic() - low_since >= 30:
                    stopped.set()
            else:
                low_since = None
            try:
                await asyncio.wait_for(finished.wait(), timeout=1)
            except TimeoutError:
                pass

    async def one_request(client: httpx.AsyncClient, request_id: str, method: str, path: str,
                          gate: asyncio.Event, payload: dict | None = None):
        nonlocal in_flight, peak_in_flight
        planned_at = time.time()
        await gate.wait()
        if stopped.is_set():
            request_rows.append({"id": request_id, "path": path, "planned_at": planned_at,
                                 "status": "interrupted"})
            return
        issued_at = time.time()
        in_flight += 1
        peak_in_flight = max(peak_in_flight, in_flight)
        status = "failed"
        http_status = None
        try:
            response = await client.request(method, path, json=payload)
            http_status = response.status_code
            status = "completed" if response.status_code == 200 else "failed"
        except asyncio.CancelledError:
            status = "interrupted"
            raise
        except Exception:
            status = "failed"
        finally:
            completed_at = time.time()
            in_flight -= 1
            request_rows.append({
                "id": request_id, "path": path, "planned_at": planned_at,
                "issued_at": issued_at, "completed_at": completed_at,
                "duration_ms": round((completed_at - issued_at) * 1000, 1),
                "http_status": http_status, "status": status,
            })

    monitor_task = asyncio.create_task(monitor())
    clients = [httpx.AsyncClient(base_url=base, timeout=45, follow_redirects=False)
               for _ in range(users)]
    started = time.monotonic()
    try:
        for wave in ("login", "light"):
            gate = asyncio.Event()
            tasks = []
            for index, client in enumerate(clients, 1):
                if wave == "login":
                    path, method, payload = "/agent-api/auth/login", "POST", {
                        "email": f"load{index:03d}@example.test", "password": "fixture-password-123"
                    }
                else:
                    path = ("/welcome", "/agent-api/health", "/agent-api/v1/models",
                            "/agent-api/v1/models")[(index - 1) % 4]
                    method, payload = "GET", None
                tasks.append(asyncio.create_task(one_request(
                    client, f"{users}-{wave}-{index:03d}", method, path, gate, payload
                )))
            await asyncio.sleep(0)
            gate.set()
            group = asyncio.gather(*tasks, return_exceptions=True)
            guard = asyncio.create_task(stopped.wait())
            done, _ = await asyncio.wait({group, guard}, timeout=90,
                                         return_when=asyncio.FIRST_COMPLETED)
            if group not in done or guard in done:
                stopped.set()
                for task in tasks:
                    task.cancel()
            await group
            guard.cancel()
            await asyncio.gather(guard, return_exceptions=True)
            if stopped.is_set():
                break
        # 压力结束后的资源回落观察。
        for _ in range(5):
            if stopped.is_set():
                break
            await asyncio.sleep(1)
    finally:
        finished.set()
        await monitor_task
        await asyncio.gather(*(client.aclose() for client in clients), return_exceptions=True)

    issued = [row for row in request_rows if row.get("issued_at")]
    durations = [row["duration_ms"] for row in issued if row["status"] == "completed"]
    summary = {
        "users": users, "planned": users * 2, "issued": len(issued),
        "completed": sum(row["status"] == "completed" for row in request_rows),
        "failed": sum(row["status"] == "failed" for row in request_rows),
        "interrupted": sum(row["status"] == "interrupted" for row in request_rows),
        "peak_in_flight": peak_in_flight, "p95_ms": percentile(durations, 0.95),
        "median_ms": round(statistics.median(durations), 1) if durations else None,
        "backend_rss_peak_mib": max((row["backend_rss_mib"] for row in resource_rows
                                     if row["backend_rss_mib"] is not None), default=None),
        "available_memory_min_percent": min(row["available_memory_percent"]
                                              for row in resource_rows),
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "stopped_by_guard": stopped.is_set(),
        "http_statuses": {str(code): sum(row["http_status"] == code for row in issued)
                          for code in sorted({row["http_status"] for row in issued
                                              if row["http_status"] is not None})},
    }
    return request_rows, resource_rows, summary


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:4173")
    parser.add_argument("--backend-pid", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if urlsplit(args.base).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("此夹具只能请求本机回环入口")
    args.out.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(base_url=args.base, timeout=10) as client:
        if (await client.get("/agent-api/health")).status_code != 200:
            raise RuntimeError("health preflight failed")
        if (await client.get("/agent-api/v1/models")).status_code != 401:
            raise RuntimeError("anonymous models preflight failed")
    all_summaries = []
    for users in (100, 200):
        requests, resources, summary = await run_tier(args.base, users, args.backend_pid)
        for name, rows in (("requests", requests), ("resources", resources)):
            path = args.out / f"{users}-{name}.jsonl"
            path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                            encoding="utf-8")
        all_summaries.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        if summary["stopped_by_guard"] or summary["failed"] or summary["interrupted"]:
            break
    (args.out / "summary.json").write_text(
        json.dumps(all_summaries, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())

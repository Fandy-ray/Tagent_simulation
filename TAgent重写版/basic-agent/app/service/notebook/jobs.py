"""后台任务：进程内线程池 + jobs 表，取代原版的 surreal-commands worker。

- submit：先写一条 queued 记录再丢进线程池，回任务编号（前端轮询用）；
- run_sync：同步接口用，提交后等它跑完（超时 300 秒，同原版 execute_command_sync）；
- 任务函数抛 NotebookError（抽取不出文字、文件类型不支持……）算永久失败，消息原样给用户看；
  别的异常也记失败，但只给一句通用文案，细节进日志。
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Callable

from app.errors.notebook import NotebookError
from app.repository.notebook.jobs import JobRepository

log = logging.getLogger(__name__)

SYNC_TIMEOUT = 300.0
RESTART_REASON = "服务重启，处理被中断，请点「重试」"


class JobRunner:
    def __init__(self, jobs: JobRepository, *, workers: int):
        self.jobs = jobs
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="notebook-job")
        self._futures: dict[str, Future] = {}
        self._lock = threading.Lock()
        self._closed = False

    def recover(self) -> int:
        count = self.jobs.fail_unfinished(RESTART_REASON)
        if count:
            log.warning("上次有 %s 个任务没跑完，已标成失败", count)
        return count

    def submit(self, name: str, args: dict, fn: Callable[[str], dict]) -> str:
        job_id = self.jobs.create(name, args)
        self.start(job_id, fn)
        return job_id

    def start(self, job_id: str, fn: Callable[[str], dict]) -> None:
        with self._lock:
            if self._closed:
                self.jobs.mark_failed(job_id, "服务正在关闭")
                return
            future = self._pool.submit(self._run, job_id, fn)
            self._futures[job_id] = future
        future.add_done_callback(lambda _f, jid=job_id: self._forget(jid))

    def _forget(self, job_id: str) -> None:
        with self._lock:
            self._futures.pop(job_id, None)

    def _run(self, job_id: str, fn: Callable[[str], dict]) -> None:
        self.jobs.mark_running(job_id)
        try:
            result = fn(job_id) or {}
        except NotebookError as exc:
            log.info("任务 %s 失败：%s", job_id, exc.detail)
            self.jobs.mark_failed(job_id, exc.detail)
            return
        except Exception:  # noqa: BLE001 - 后台线程里的异常不能丢，要记到任务上
            log.exception("任务 %s 出错", job_id)
            self.jobs.mark_failed(job_id, "处理时出错，请稍后重试")
            return
        self.jobs.mark_completed(job_id, result)

    def wait(self, job_id: str, timeout: float = SYNC_TIMEOUT) -> dict | None:
        with self._lock:
            future = self._futures.get(job_id)
        if future is not None:
            try:
                future.result(timeout=timeout)
            except TimeoutError:
                pass
        return self.jobs.get(job_id)

    def is_active(self, job_id: str | None) -> bool:
        if not job_id:
            return False
        with self._lock:
            if job_id in self._futures:
                return True
        job = self.jobs.get(job_id)
        return bool(job and job["status"] in {"queued", "running"})

    def close(self, timeout: float = 10.0) -> None:
        """排队的任务取消（库里还是 queued，下次启动会标成失败可重试），正在跑的最多等 timeout 秒。"""
        with self._lock:
            self._closed = True
            running = list(self._futures.values())
        self._pool.shutdown(wait=False, cancel_futures=True)
        if running:
            wait(running, timeout=timeout)

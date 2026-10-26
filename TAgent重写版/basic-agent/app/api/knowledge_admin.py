"""管理后台「设置 · 文档」：知识库实际在用的配置和状态，外加三个动作。

- 看：嵌入模型与实际版本、切块参数、教材 / 论文 / 笔记本各来源的状态与条数、索引、答疑取几块、出题取材配比、检索缓存；
  全是后端此刻真正在用的值，只读——这些参数改了要重建索引、重测出题质量，不适合在网页上随手改。
- 清检索缓存：同一个问题 60 秒内会复用检索结果，改了教材想立刻看到效果时用。
- 重建索引：重新读教材和参考文献，建好后整体换上，不用重启后端（几秒，块向量有缓存）。
- 补参考文献：跑一遍 tools/fetch_references.py（缺的论文去期刊官网下），跑完自动重建索引。

后两个要跑几秒到几分钟，在后台做，接口立刻返回，页面轮询本接口看进度。都要管理员口令。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from flask import Blueprint, jsonify

from app.api.deps import get_services
from app.api.notebook_status import notebook_reachable
from app.api.security import require_admin_token
from app.config import AgentConfig
from app.errors.api_errors import AgentAPIError
from app.infra.background_job import BackgroundJob


blueprint = Blueprint("knowledge_admin", __name__, url_prefix="/admin/knowledge")

BASIC_AGENT_DIR = Path(__file__).resolve().parents[2]
# 14 篇论文全缺、期刊官网又慢时，一篇要几十秒
REFERENCES_TIMEOUT_SECONDS = 900
_jobs = {"reload": BackgroundJob("reload"), "references": BackgroundJob("references")}


@blueprint.get("")
def knowledge_config():
    require_admin_token()
    settings = AgentConfig.from_env()
    knowledge_base = get_services().knowledge_base
    snapshot = (
        knowledge_base.admin_snapshot()
        if hasattr(knowledge_base, "admin_snapshot")
        else {"kind": type(knowledge_base).__name__}
    )
    return jsonify(
        {
            "source": settings.knowledge_source,
            "notebook_url": settings.notebook_url,
            "notebook_reachable": notebook_reachable(settings, knowledge_base),
            "knowledge_base": snapshot,
            "jobs": {name: job.status() for name, job in _jobs.items()},
        }
    )


@blueprint.post("/cache/clear")
def clear_cache():
    require_admin_token()
    knowledge_base = get_services().knowledge_base
    cleared = knowledge_base.clear_retrieval_cache() if hasattr(knowledge_base, "clear_retrieval_cache") else 0
    return jsonify({"cleared": cleared})


@blueprint.post("/reload")
def reload_index():
    require_admin_token()
    knowledge_base = get_services().knowledge_base
    if not hasattr(knowledge_base, "reload"):
        raise AgentAPIError("当前的知识来源不需要重建索引（只用笔记本时检索在笔记本服务里做）。", 400, "not_supported")

    def task() -> str:
        result = knowledge_base.reload()
        return _reload_message(result)

    return _start("reload", task)


@blueprint.post("/references/refresh")
def refresh_references():
    require_admin_token()
    settings = AgentConfig.from_env()
    knowledge_base = get_services().knowledge_base
    if settings.references_dir is None or not hasattr(knowledge_base, "reload"):
        raise AgentAPIError("参考文献没有启用（TAGENT_REFERENCES=0，或只用笔记本）。", 400, "not_supported")

    def task() -> str:
        # 子进程跑：下载、抽文字都在那边做，出什么错都不会带累服务进程；输出原样拿来给页面看。
        # 两边都定死 UTF-8：中文 Windows 默认是 GBK，子进程和这边只要有一边不是（比如全局设了
        # PYTHONIOENCODING），读输出就乱码甚至报错，明明论文下好了却显示失败、也不重建索引
        done = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "tools.fetch_references"],
            cwd=BASIC_AGENT_DIR,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=REFERENCES_TIMEOUT_SECONDS,
        )
        lines = [line.strip() for line in (done.stdout + done.stderr).splitlines() if line.strip()]
        summary = "；".join(lines[-4:])
        if done.returncode != 0:
            raise RuntimeError(summary or f"参考文献脚本退出码 {done.returncode}")
        return f"{summary}；{_reload_message(knowledge_base.reload())}" if summary else _reload_message(knowledge_base.reload())

    return _start("references", task)


def _start(name: str, task):
    job = _jobs[name]
    started = job.start(task)
    return jsonify({"started": started, "job": job.status()}), 202


def _reload_message(result: dict) -> str:
    if "sources" in result:
        result = next((item for item in result["sources"] if item), {})
    return f"索引已重建：{result.get('chunks', 0)} 块，参考文献 {result.get('papers') or 0} 篇"

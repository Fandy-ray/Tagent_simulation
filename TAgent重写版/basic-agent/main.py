"""启动入口。

必须留在 basic-agent/ 根目录：scripts/start.ps1 与 deploy/systemd 都按
`python main.py`（工作目录 basic-agent/）拉起本服务。
"""

import logging
import threading
from pathlib import Path

from dotenv import load_dotenv

_here = Path(__file__).resolve().parent
load_dotenv(_here / ".env")
load_dotenv(_here.parent / ".env.runtime")

from app.config import AgentConfig  # noqa: E402  — 必须在 load_dotenv 之后再读环境
from app.factory import create_app  # noqa: E402


app = create_app()


def _serve_notebook_api() -> None:
    """笔记本页面和 tagent 前端仍然访问 5055。和 5001 是同一个应用、另一组线程。"""
    notebook = app.extensions.get("notebook_services")
    if notebook is None:
        return
    settings = AgentConfig.from_env()
    port = notebook.settings.port
    if port == settings.port:
        return
    log = logging.getLogger("notebook")

    def run() -> None:
        try:
            from waitress import serve

            log.info("笔记本接口 http://127.0.0.1:%s", port)
            serve(app, host="127.0.0.1", port=port, threads=notebook.settings.threads)
        except Exception:
            log.exception("笔记本接口 %s 没能监听（多半是旧的 Docker 还占着这个端口）", port)

    threading.Thread(target=run, name="notebook-api", daemon=True).start()


def _close_services() -> None:
    services = app.extensions.get("services")
    closer = getattr(services, "close", None)
    if closer is not None:
        closer()


def main() -> None:
    settings = AgentConfig.from_env()
    _serve_notebook_api()
    try:
        if settings.use_waitress:
            try:
                from waitress import serve

                serve(
                    app,
                    host=settings.host,
                    port=settings.port,
                    threads=settings.waitress_threads,
                    connection_limit=settings.waitress_connection_limit,
                )
                return
            except ImportError:
                pass
        app.run(
            host=settings.host,
            port=settings.port,
            debug=False,
            threaded=True,
            use_reloader=False,
        )
    finally:
        _close_services()


if __name__ == "__main__":
    main()

"""启动入口。

必须留在 basic-agent/ 根目录：scripts/start.ps1 与 deploy/systemd 都按
`python main.py`（工作目录 basic-agent/）拉起本服务。
"""

from pathlib import Path

from dotenv import load_dotenv

_here = Path(__file__).resolve().parent
load_dotenv(_here / ".env")
load_dotenv(_here.parent / ".env.runtime")

from app.config import AgentConfig  # noqa: E402  — 必须在 load_dotenv 之后再读环境
from app.factory import create_app  # noqa: E402


app = create_app()


def main() -> None:
    settings = AgentConfig.from_env()
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


if __name__ == "__main__":
    main()

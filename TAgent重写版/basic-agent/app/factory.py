"""启动类：装配配置、依赖、路由与异常处理，别的什么都不做。"""

from __future__ import annotations

from flask import Flask, request

from app.api import register_blueprints
from app.api.error_handler import register_error_handlers
from app.config import AgentConfig, running_under_pytest
from app.container import build_registry, build_services


def create_app(config: dict | None = None, *, registry=None, services=None) -> Flask:
    settings = AgentConfig.from_env()

    app = Flask(__name__)
    app.config.from_mapping(
        AGENT_ADMIN_TOKEN=settings.admin_token,
        AGENT_INTERNAL_TOKEN=settings.internal_token,
        MAX_CONTENT_LENGTH=settings.max_content_length,
    )
    if config:
        app.config.update(config)
    app.json.ensure_ascii = False

    app.extensions["settings"] = settings
    app.extensions["model_provider_registry"] = registry or build_registry(settings)
    # TESTING 时跳过预热：加载嵌入模型并建 FAISS 索引要几十秒。
    # 也不建学习记录库：单测不该往真实的数据目录里写东西（要测它就自己注入一个）。
    testing = app.config.get("TESTING", False)
    # 单测里 PYTEST_CURRENT_TEST 一定在。TESTING=False 的那条预热测试也会进来，
    # 不能因此去打开用户本机的笔记本库。真正启动（python main.py）没有这个变量。
    app.extensions["services"] = services or build_services(
        settings,
        warm_up=not testing,
        learning_store=not testing,
        include_notebook=not testing and not running_under_pytest(),
        registry=app.extensions["model_provider_registry"],
    )

    register_blueprints(app)
    register_error_handlers(app)
    notebook = getattr(app.extensions["services"], "notebook", None)
    if notebook is not None:
        mount_notebook(
            app, notebook, respect_limit=bool(config and "MAX_CONTENT_LENGTH" in config)
        )

    @app.after_request
    def allow_tagentnote(response):
        origin = request.headers.get("Origin", "")
        if origin in {"http://127.0.0.1:5173", "http://localhost:5173"}:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, X-Tagent-Client-Id, X-Tagent-Client-Name, X-Tagent-No-Record"
            )
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    return app


def mount_notebook(app: Flask, notebook, *, respect_limit: bool = False) -> None:
    """把笔记本的接口挂到已经建好的 tagent 应用上。/ 和 /health 仍是 tagent 的。"""
    from app.api.notebook import register_blueprints as register_notebook_blueprints
    from app.api.notebook.security import install_security

    app.extensions["notebook_services"] = notebook
    install_security(
        app,
        password=notebook.settings.password,
        cors_origins=notebook.settings.cors_origins,
        api_only=True,
    )
    register_notebook_blueprints(app, include_root=False)
    # 笔记本客户端会带或不带结尾斜杠，和单独跑的时候一样都认。
    app.url_map.strict_slashes = False
    if not respect_limit:
        upload = notebook.settings.max_upload_mb * 1024 * 1024
        agent_limit = app.config.get("MAX_CONTENT_LENGTH") or 0
        if agent_limit < upload:
            # 上传要能到笔记本的上限，但答疑、出卷仍守原来的 1 MiB，不能跟着放宽。
            app.config["TAGENT_BODY_LIMIT"] = agent_limit
            app.config["MAX_CONTENT_LENGTH"] = upload

            @app.before_request
            def limit_non_notebook_body():
                if request.path.startswith("/api/"):
                    return None
                limit = app.config.get("TAGENT_BODY_LIMIT") or 0
                length = request.content_length
                if not limit or length is None or length <= limit:
                    return None
                from app.api.error_handler import error_response
                from app.errors.api_errors import AgentAPIError

                mib = max(1, limit // (1024 * 1024))
                return error_response(
                    AgentAPIError(
                        f"Request body exceeds the {mib} MiB limit.",
                        413,
                        "request_too_large",
                    )
                )


def create_notebook_app(settings=None, *, services=None, warm_up: bool = True) -> Flask:
    """只含笔记本的应用。笔记本自己的测试用这个，不拉 tagent 的模型和图。"""
    from app.api.notebook import register_blueprints as register_notebook_blueprints
    from app.api.notebook.error_handler import register_error_handlers as register_notebook_errors
    from app.api.notebook.security import install_security
    from app.config import NotebookSettings
    from app.service.notebook.assembly import build_services as build_notebook_services

    settings = settings or (services.settings if services else NotebookSettings.from_env())
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=settings.max_upload_mb * 1024 * 1024)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    app.url_map.strict_slashes = False
    notebook = services or build_notebook_services(settings, warm_up=warm_up)
    app.extensions["notebook_services"] = notebook
    install_security(app, password=settings.password, cors_origins=settings.cors_origins)
    register_notebook_blueprints(app, include_root=True)
    register_notebook_errors(app)
    return app

"""启动类：装配配置、依赖、路由与异常处理，别的什么都不做。"""

from __future__ import annotations

from urllib.parse import urlsplit

from flask import Flask, g, request

from app.api import register_blueprints
from app.api.error_handler import register_error_handlers
from app.config import AgentConfig, AuthConfig, running_under_pytest
from app.container import build_registry, build_services


def create_app(config: dict | None = None, *, registry=None, services=None) -> Flask:
    settings = AgentConfig.from_env()
    auth_settings = AuthConfig.from_env()

    app = Flask(__name__)
    app.config.from_mapping(
        AGENT_ADMIN_TOKEN=settings.admin_token,
        AGENT_INTERNAL_TOKEN=settings.internal_token,
        MAX_CONTENT_LENGTH=settings.max_content_length,
        AUTH_ENABLED=auth_settings.enabled,
        AUTH_PUBLIC_ORIGIN=auth_settings.public_origin,
        AUTH_NOTEBOOK_ORIGIN=auth_settings.notebook_origin,
        AUTH_COOKIE_SECURE=auth_settings.cookie_secure,
    )
    if config:
        app.config.update(config)
    if app.config["AUTH_ENABLED"]:
        # 个人文档允许 5 MiB 明文；加密和 JSON 请求包装需要额外余量。
        app.config["MAX_CONTENT_LENGTH"] = max(app.config["MAX_CONTENT_LENGTH"], 8 * 1024 * 1024)
    app.config["AUTH_COOKIE_NAME"] = (
        "__Host-tagent_session" if app.config["AUTH_COOKIE_SECURE"] else "tagent_session_dev"
    )
    app.json.ensure_ascii = False

    if app.config["AUTH_ENABLED"]:
        from app.api.auth_gate import enforce_identity
        from app.auth.mail import DisabledMailer, MemoryMailer, SMTPMailer
        from app.auth.notebook_lifecycle import NotebookLifecycle
        from app.auth.personal import PersonalService
        from app.auth.service import AuthService
        from app.auth.store import IdentityStore

        origin = app.config["AUTH_PUBLIC_ORIGIN"]
        if not origin or (not app.config.get("TESTING") and not origin.startswith("https://")):
            raise ValueError("TAgent login requires a configured HTTPS public origin")
        notebook_origin = app.config["AUTH_NOTEBOOK_ORIGIN"]
        if not notebook_origin and not app.config.get("TESTING"):
            raise ValueError("TAgent login requires the full OpenNotebook public origin")
        if notebook_origin:
            notebook_url = urlsplit(notebook_origin)
            main_url = urlsplit(origin)
            if (
                notebook_url.scheme != "https"
                or not notebook_url.hostname
                or notebook_url.hostname != main_url.hostname
                or notebook_url.username is not None
                or notebook_url.password is not None
                or notebook_url.path
                or notebook_url.query
                or notebook_url.fragment
            ):
                raise ValueError(
                    "OpenNotebook origin must be HTTPS on the TAgent hostname"
                )
        if not app.config["AUTH_COOKIE_SECURE"] and not app.config.get("TESTING"):
            raise ValueError("TAgent login requires Secure session cookies")
        mail_mode = auth_settings.mail_mode
        if app.config.get("TESTING") and mail_mode == "memory":
            mailer = MemoryMailer()
        elif mail_mode == "disabled":
            mailer = DisabledMailer()
        elif mail_mode == "smtp":
            mailer = SMTPMailer(
                auth_settings.smtp_host, auth_settings.smtp_port,
                auth_settings.smtp_user, auth_settings.smtp_password,
                auth_settings.smtp_from,
            )
        else:
            raise ValueError("Choose disabled mail or configure SMTP mail delivery")
        store = app.config.get("AUTH_STORE")
        if store is None and (app.config.get("AUTH_SERVICE") is None or app.config.get("PERSONAL_SERVICE") is None):
            store = IdentityStore(
                auth_settings.db_url, auth_settings.db_namespace,
                auth_settings.db_database, auth_settings.db_user,
                auth_settings.db_password,
            )
        app.extensions["auth_service"] = app.config.get("AUTH_SERVICE") or AuthService(
            store, mailer, origin, registration_open=auth_settings.registration_open
        )
        app.extensions["personal_service"] = app.config.get("PERSONAL_SERVICE") or PersonalService(
            store, auth_settings.data_keys
        )
        lifecycle = app.config.get("NOTEBOOK_LIFECYCLE")
        if lifecycle is None and auth_settings.notebook_lifecycle_url and auth_settings.notebook_lifecycle_key:
            lifecycle = NotebookLifecycle(
                auth_settings.notebook_lifecycle_url,
                auth_settings.notebook_lifecycle_key,
            )
        if lifecycle is None and not app.config.get("TESTING"):
            raise ValueError("TAgent login requires the full OpenNotebook lifecycle service")
        app.extensions["notebook_lifecycle"] = lifecycle
        app.before_request(enforce_identity)

        from app.infra.notebook_identity import reset_notebook_identity

        @app.after_request
        def keep_streaming_request_active(response):
            activity_uid = getattr(g, "auth_activity_uid", None)
            if activity_uid is not None and response.is_streamed:
                g.auth_activity_uid = None
                response.call_on_close(
                    lambda uid=activity_uid: app.extensions["auth_service"].end_request(uid)
                )
            return response

        @app.teardown_request
        def clear_notebook_identity(_error):
            try:
                token = getattr(g, "notebook_identity_token", None)
                if token is not None:
                    reset_notebook_identity(token)
            finally:
                activity_uid = getattr(g, "auth_activity_uid", None)
                if activity_uid is not None:
                    g.auth_activity_uid = None
                    app.extensions["auth_service"].end_request(activity_uid)

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
        # 精简笔记本使用共享存储。账号模式只能接入已完成隔离的完整版服务。
        include_notebook=not testing and not running_under_pytest() and not app.config["AUTH_ENABLED"],
        account_mode=app.config["AUTH_ENABLED"],
        registry=app.extensions["model_provider_registry"],
    )
    if app.config["AUTH_ENABLED"] and not testing and app.extensions["services"].store is None:
        raise ValueError("TAgent login requires a working learning records database")

    register_blueprints(app)
    register_error_handlers(app)
    notebook = getattr(app.extensions["services"], "notebook", None)
    if notebook is not None:
        mount_notebook(
            app, notebook, respect_limit=bool(config and "MAX_CONTENT_LENGTH" in config)
        )

    @app.after_request
    def allow_tagentnote(response):
        if app.config["AUTH_ENABLED"]:
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Content-Type-Options"] = "nosniff"
        origin = request.headers.get("Origin", "")
        if origin in {"http://127.0.0.1:5173", "http://localhost:5173"}:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, X-Tagent-Client-Id, X-Tagent-Client-Name, X-Tagent-No-Record, "
                "X-Tagent-CSRF, X-Tagent-Course-Id, X-Tagent-Account-Id"
            )
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
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
    if AuthConfig.from_env().enabled:
        raise ValueError("Shared Lite notebook cannot run in TAgent account mode")
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

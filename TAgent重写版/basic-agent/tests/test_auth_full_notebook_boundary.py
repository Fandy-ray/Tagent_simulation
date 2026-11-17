"""Account mode must not expose the newer shared Lite notebook storage."""

from types import SimpleNamespace

import pytest
from flask import Flask

from app import factory
from app.api.auth_gate import enforce_identity


def test_account_mode_does_not_mount_shared_lite_notebook(monkeypatch):
    captured = {}

    def build_services(_settings, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(store=object(), notebook=None)

    monkeypatch.setattr(factory, "build_services", build_services)
    monkeypatch.setattr(factory, "running_under_pytest", lambda: False)
    app = factory.create_app(
        config={
            "AUTH_ENABLED": True,
            "AUTH_PUBLIC_ORIGIN": "https://example.org",
            "AUTH_COOKIE_SECURE": True,
            "AUTH_SERVICE": object(),
            "PERSONAL_SERVICE": object(),
        },
        registry=object(),
    )

    assert captured["include_notebook"] is False
    assert captured["account_mode"] is True
    assert "notebook_services" not in app.extensions


def test_standalone_shared_lite_notebook_refuses_account_mode(monkeypatch):
    monkeypatch.setenv("TAGENT_AUTH_ENABLED", "1")
    with pytest.raises(ValueError, match="Shared Lite notebook"):
        factory.create_notebook_app()


def test_notebook_origin_is_accepted_only_on_same_https_host():
    app = Flask(__name__)
    app.config.update(
        AUTH_ENABLED=True,
        AUTH_PUBLIC_ORIGIN="https://tagent.example.org:5173",
        AUTH_NOTEBOOK_ORIGIN="https://tagent.example.org:8502",
    )
    for origin in (
        "https://tagent.example.org:5173",
        "https://tagent.example.org:8502",
    ):
        with app.test_request_context(
            "/auth/login", method="POST", headers={"Origin": origin}
        ):
            enforce_identity()
    with app.test_request_context(
        "/api/anything",
        method="POST",
        headers={"Origin": "https://tagent.example.org:8502"},
    ):
        from app.errors.api_errors import AgentAPIError

        with pytest.raises(AgentAPIError):
            enforce_identity()


@pytest.mark.parametrize(
    "origin",
    ["http://tagent.example.org:8502", "https://other.example.org:8502"],
)
def test_notebook_origin_rejects_untrusted_browser(origin):
    from app.errors.api_errors import AgentAPIError

    app = Flask(__name__)
    app.config.update(
        AUTH_ENABLED=True,
        AUTH_PUBLIC_ORIGIN="https://tagent.example.org:5173",
        AUTH_NOTEBOOK_ORIGIN="https://tagent.example.org:8502",
    )
    with app.test_request_context(
        "/auth/login", method="POST", headers={"Origin": origin}
    ):
        with pytest.raises(AgentAPIError):
            enforce_identity()


def test_factory_rejects_cross_host_notebook_origin():
    with pytest.raises(ValueError, match="TAgent hostname"):
        factory.create_app(
            config={
                "AUTH_ENABLED": True,
                "AUTH_PUBLIC_ORIGIN": "https://tagent.example.org:5173",
                "AUTH_NOTEBOOK_ORIGIN": "https://other.example.org:8502",
                "AUTH_COOKIE_SECURE": True,
                "AUTH_SERVICE": object(),
                "PERSONAL_SERVICE": object(),
            },
            registry=object(),
        )

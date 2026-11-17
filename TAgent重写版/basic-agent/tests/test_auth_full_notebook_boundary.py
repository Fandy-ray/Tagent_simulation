"""Account mode must not expose the newer shared Lite notebook storage."""

from types import SimpleNamespace

import pytest

from app import factory


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

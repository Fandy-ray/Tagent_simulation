"""Loopback-only TAgent account fixture for the full OpenNotebook integration probe.

This is opt-in test infrastructure. It uses an in-memory identity database and
must never be used as a production entry point.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet
from werkzeug.serving import make_server
from werkzeug.wrappers import Response

from app.auth.mail import DisabledMailer
from app.auth.personal import PersonalService
from app.auth.service import AuthService
from app.auth.store import IdentityStore
from app.factory import create_app
from tools.init_auth_db import SCHEMA


def main() -> None:
    if os.getenv("RUN_TAGENT_AUTH_INTEGRATION_FIXTURE") != "1":
        raise RuntimeError("Explicit local integration-test opt-in is required")
    port = int(os.getenv("TAGENT_AUTH_INTEGRATION_PORT", "18801"))
    if not 1024 <= port <= 65535:
        raise ValueError("Invalid integration fixture port")

    store = IdentityStore("mem://", "tagent_integration", "accounts", "", "")
    try:
        for statement in SCHEMA:
            store.query(statement)
        service = AuthService(
            store,
            DisabledMailer(),
            "https://tagent.example.org",
            registration_open=True,
        )
        app = create_app({
            "TESTING": True,
            "AUTH_ENABLED": True,
            "AUTH_PUBLIC_ORIGIN": "https://tagent.example.org",
            "AUTH_NOTEBOOK_ORIGIN": "https://tagent.example.org:8502",
            "AUTH_COOKIE_SECURE": True,
            "AUTH_STORE": store,
            "AUTH_SERVICE": service,
            "PERSONAL_SERVICE": PersonalService(
                store, Fernet.generate_key().decode()
            ),
        })

        normal_wsgi = app.wsgi_app

        def fixture_marker(environ, start_response):
            if environ.get("PATH_INFO") == "/__integration_fixture":
                return Response(
                    '{"fixture":"in_memory_tagent_auth"}',
                    content_type="application/json",
                )(environ, start_response)
            return normal_wsgi(environ, start_response)

        app.wsgi_app = fixture_marker

        server = make_server("127.0.0.1", port, app, threaded=False)
        print(f"TAGENT_AUTH_FIXTURE_READY 127.0.0.1:{port}", flush=True)
        server.serve_forever()
    finally:
        store.close()


if __name__ == "__main__":
    main()

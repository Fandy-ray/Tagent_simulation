"""The account cleanup client signs only loopback calls for one exact account."""

import hashlib
import hmac
from io import BytesIO
from uuid import uuid4

import httpx
import pytest

from app.auth.notebook_lifecycle import NotebookLifecycle
from app.errors.api_errors import AgentAPIError


def test_lifecycle_client_signs_disable_and_purge():
    secret = "l" * 48
    account = str(uuid4())
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        timestamp = request.headers["x-tagent-lifecycle-time"]
        payload = f"{request.method}\n{request.url.path}\n{timestamp}".encode()
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert hmac.compare_digest(
            request.headers["x-tagent-lifecycle-signature"], expected
        )
        assert request.url.host == "127.0.0.1"
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={
            "disabled" if request.url.path.endswith("/disable") else "deleted": True
        })

    client = NotebookLifecycle(
        "http://127.0.0.1:5055", secret, httpx.MockTransport(handler)
    )
    client.disable(account)
    client.purge(account)
    assert seen == [
        ("POST", f"/api/internal/accounts/{account}/disable"),
        ("DELETE", f"/api/internal/accounts/{account}/purge"),
    ]


def test_lifecycle_client_rejects_remote_target_and_pending_cleanup():
    with pytest.raises(ValueError, match="loopback"):
        NotebookLifecycle("https://example.org:5055", "l" * 48)
    client = NotebookLifecycle(
        "http://127.0.0.1:5055", "l" * 48,
        httpx.MockTransport(lambda _: httpx.Response(202)),
    )
    with pytest.raises(AgentAPIError) as error:
        client.purge(str(uuid4()))
    assert error.value.code == "notebook_cleanup_pending"


def test_lifecycle_export_streams_zip_and_rejects_wrong_content_type():
    account = str(uuid4())
    client = NotebookLifecycle(
        "http://127.0.0.1:5055", "l" * 48,
        httpx.MockTransport(lambda _: httpx.Response(
            200, content=b"PK\x03\x04archive", headers={"content-type": "application/zip"}
        )),
    )
    output = BytesIO()
    client.download(account, output)
    assert output.getvalue() == b"PK\x03\x04archive"

    invalid = NotebookLifecycle(
        "http://127.0.0.1:5055", "l" * 48,
        httpx.MockTransport(lambda _: httpx.Response(
            200, content=b"{}", headers={"content-type": "application/json"}
        )),
    )
    with pytest.raises(AgentAPIError) as error:
        invalid.download(account, BytesIO())
    assert error.value.code == "notebook_export_unavailable"

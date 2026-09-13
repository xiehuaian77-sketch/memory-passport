"""Tests for transport, error mapping, and retry policy."""

import httpx
import pytest
from memory_passport import MemoryPassportClient
from memory_passport.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    MemoryPassportError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)


def test_error_mapping_401(mock_handler, mock_client):
    mock_handler.register("GET", "/api/memories/m1", status_code=401, json_data={"detail": "Unauthorized token"})
    with pytest.raises(AuthenticationError) as exc:
        mock_client.memories.get("m1")
    assert exc.value.status_code == 401
    assert "Unauthorized" in exc.value.message


def test_error_mapping_403(mock_handler, mock_client):
    mock_handler.register("GET", "/api/memories/m1", status_code=403, json_data={"detail": "Forbidden"})
    with pytest.raises(AuthorizationError):
        mock_client.memories.get("m1")


def test_error_mapping_404(mock_handler, mock_client):
    mock_handler.register("GET", "/api/memories/missing", status_code=404, json_data={"detail": "Memory not found"})
    with pytest.raises(NotFoundError):
        mock_client.memories.get("missing")


def test_error_mapping_409(mock_handler, mock_client):
    mock_handler.register("POST", "/api/memories", status_code=409, json_data={"detail": "Key already exists"})
    with pytest.raises(ConflictError):
        mock_client.memories.create(key="k", content="c")


def test_error_mapping_422(mock_handler, mock_client):
    mock_handler.register("POST", "/api/memories", status_code=422, json_data={
        "detail": [{"loc": ["body", "content"], "msg": "Field required"}]
    })
    with pytest.raises(ValidationError) as exc:
        mock_client.memories.create(key="k", content="")
    assert "Field required" in exc.value.message


def test_error_mapping_429(mock_handler, mock_client):
    mock_handler.register("POST", "/api/chat", status_code=429, json_data={"detail": "Quota exceeded"}, headers={"Retry-After": "3.5"})
    with pytest.raises(RateLimitError) as exc:
        mock_client.chat.chat("hello")
    assert exc.value.retry_after == 3.5


def test_error_mapping_500(mock_handler, mock_client):
    mock_handler.register("POST", "/api/memories", status_code=500, json_data={"detail": "Database crash"})
    with pytest.raises(ServerError):
        mock_client.memories.create(key="k", content="c")


def test_post_does_not_auto_retry(mock_handler, mock_client):
    # Non-idempotent POST failing with 503 should NOT retry
    mock_handler.register("POST", "/api/memories", status_code=503, json_data={"detail": "Temporarily unavailable"})
    with pytest.raises(ServerError):
        mock_client.memories.create(key="k", content="c")
    assert len(mock_handler.requests) == 1


def test_get_retries_on_503(mock_handler, mock_client):
    attempts = 0

    def flaky_handler(request):
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            return httpx.Response(503, headers={"content-type": "application/json"}, content=b'{"detail": "Fail once"}')
        import json
        data = {
            "id": "mem-ok",
            "user_id": "u1",
            "key": "k",
            "content": "c",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        return httpx.Response(200, headers={"content-type": "application/json"}, content=json.dumps(data).encode("utf-8"))

    mock_handler._default_handler = flaky_handler
    mem = mock_client.memories.get("mem-ok")
    assert mem.id == "mem-ok"
    assert attempts == 2


def test_malformed_json_response(mock_handler, mock_client):
    def bad_json(request):
        return httpx.Response(200, headers={"content-type": "application/json"}, content=b"{broken json")

    mock_handler._default_handler = bad_json
    with pytest.raises(MemoryPassportError) as exc:
        mock_client.memories.get("m1")
    assert "Failed to parse server JSON response" in str(exc.value)


def test_network_connection_error():
    def fail_connect(request):
        raise httpx.ConnectError("Failed to resolve host")

    transport = httpx.MockTransport(fail_connect)
    client = httpx.Client(base_url="http://broken.server", transport=transport)
    sdk_client = MemoryPassportClient(base_url="http://broken.server", httpx_client=client, max_retries=0)
    with pytest.raises(NetworkError) as exc:
        sdk_client.memories.get("m1")
    assert "Network error" in str(exc.value)

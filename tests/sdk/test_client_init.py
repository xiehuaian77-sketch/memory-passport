"""Tests for client initialization, authentication header injection, and security."""

from memory_passport import MemoryPassportClient


def test_client_init_defaults():
    client = MemoryPassportClient(base_url="https://api.example.com/", api_key="test-key")
    assert client.base_url == "https://api.example.com"
    client.close()


def test_client_init_from_env(monkeypatch):
    monkeypatch.setenv("MEMORY_PASSPORT_API_KEY", "env-secret-token")
    client = MemoryPassportClient(base_url="http://localhost:8000")
    assert client._transport._credential == "env-secret-token"
    client.close()


def test_client_repr_masks_credentials():
    secret_key = "sk_live_very_secret_key_12345"
    client = MemoryPassportClient(base_url="https://api.example.com", api_key=secret_key)
    repr_str = repr(client)
    assert secret_key not in repr_str
    assert "https://api.example.com" in repr_str
    client.close()


def test_authorization_header_injected(mock_handler, mock_client):
    mock_handler.register("GET", "/api/memories/test-id", status_code=200, json_data={
        "id": "test-id",
        "user_id": "user-1",
        "key": "k",
        "content": "c",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    })
    mock_client.memories.get("test-id")
    assert len(mock_handler.requests) == 1
    req = mock_handler.requests[0]
    assert req.headers["authorization"] == "Bearer test-api-key"
    assert "memory-passport-python" in req.headers["user-agent"]

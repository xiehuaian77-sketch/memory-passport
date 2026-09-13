"""Tests for credential sanitization and privacy guarantees."""

import pytest
from memory_passport.exceptions import AuthenticationError, NotFoundError


def test_fake_api_key_not_in_exception_str(mock_handler, mock_client):
    secret_key = "test-api-key"
    mock_handler.register("GET", "/api/memories/secret-id", status_code=404, json_data={"detail": "Not found"})
    with pytest.raises(NotFoundError) as exc:
        mock_client.memories.get("secret-id")

    err_str = str(exc.value)
    err_repr = repr(exc.value)
    assert secret_key not in err_str
    assert secret_key not in err_repr


def test_auth_error_does_not_leak_bearer_header(mock_handler, mock_client):
    mock_handler.register("GET", "/api/memories/m", status_code=401, json_data={"detail": "Invalid token provided"})
    with pytest.raises(AuthenticationError) as exc:
        mock_client.memories.get("m")

    assert "Bearer" not in str(exc.value)
    assert "test-api-key" not in str(exc.value)


def test_extra_server_field_resilience():
    from memory_passport.models import Memory
    data = {
        "id": "mem-1",
        "user_id": "u1",
        "key": "k",
        "content": "c",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "brand_new_v2_field": {"complex": 123},
    }
    m = Memory.model_validate(data)
    assert m.id == "mem-1"

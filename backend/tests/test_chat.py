"""Phase 3.0A: AI Chat Core integration and unit tests."""

from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient

from app.providers.llm_provider import (
    LLMCommunicationError,
    LLMConfigError,
)
from app.services.chat_service import ChatService


@pytest.mark.asyncio
async def test_chat_unauthenticated(client: AsyncClient):
    """Unauthenticated requests to POST /api/chat must return 401."""
    resp = await client.post("/api/chat", json={"message": "Hello AI"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_empty_message_validation(auth_client: AsyncClient):
    """Empty or whitespace-only messages must be rejected with 422."""
    # Empty string
    r1 = await auth_client.post("/api/chat", json={"message": ""})
    assert r1.status_code == 422

    # Whitespace only
    r2 = await auth_client.post("/api/chat", json={"message": "   \n\t  "})
    assert r2.status_code == 422

    # Missing message field
    r3 = await auth_client.post("/api/chat", json={})
    assert r3.status_code == 422


@pytest.mark.asyncio
async def test_chat_invalid_parameters(auth_client: AsyncClient):
    """Invalid payload structures must return 422."""
    resp = await auth_client.post("/api/chat", json={"message": None})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_normal_chat_success(auth_client: AsyncClient):
    """Successful chat generation returns response without memory injection or side-effects."""
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = "Hello! I am your AI assistant."

    with patch("app.services.chat_service.get_ai_provider", return_value=mock_provider):
        resp = await auth_client.post("/api/chat", json={"message": "Introduce yourself"})
        assert resp.status_code == 200
        data = resp.json()

        # Both response and reply fields are present
        assert data["response"] == "Hello! I am your AI assistant."
        assert data["reply"] == "Hello! I am your AI assistant."

        # In Phase 3.0A: no retrieval and no extraction
        assert data["extracted_memories"] == []
        assert data["loaded_memories"] == []

        # Verify prompt passed cleanly to provider
        mock_provider.generate.assert_called_once_with(prompt="Introduce yourself")


@pytest.mark.asyncio
async def test_chat_config_error_returns_503(auth_client: AsyncClient):
    """Missing or invalid LLM configuration returns 503 Service Unavailable."""
    mock_provider = AsyncMock()
    mock_provider.generate.side_effect = LLMConfigError("LLM_API_KEY is not configured")

    with patch("app.services.chat_service.get_ai_provider", return_value=mock_provider):
        resp = await auth_client.post("/api/chat", json={"message": "Hello"})
        assert resp.status_code == 503
        data = resp.json()
        assert "AI service is not configured" in data["detail"]


@pytest.mark.asyncio
async def test_chat_communication_error_returns_502(auth_client: AsyncClient):
    """Upstream AI provider communication failure returns 502 Bad Gateway."""
    mock_provider = AsyncMock()
    mock_provider.generate.side_effect = LLMCommunicationError("Connection timeout")

    with patch("app.services.chat_service.get_ai_provider", return_value=mock_provider):
        resp = await auth_client.post("/api/chat", json={"message": "Hello"})
        assert resp.status_code == 502
        data = resp.json()
        assert "Failed to communicate with AI provider" in data["detail"]


@pytest.mark.asyncio
async def test_chat_error_does_not_leak_secret(auth_client: AsyncClient):
    """Error responses must never leak internal API keys, tokens, or credentials."""
    secret_key = "sk-dashscope-secret-super-sensitive-12345"
    mock_provider = AsyncMock()
    mock_provider.generate.side_effect = LLMCommunicationError(
        f"Internal exception containing {secret_key}"
    )

    with patch("app.services.chat_service.get_ai_provider", return_value=mock_provider):
        resp = await auth_client.post("/api/chat", json={"message": "Trigger error"})
        assert resp.status_code == 502
        assert secret_key not in resp.text


@pytest.mark.asyncio
async def test_chat_user_id_authentication_boundary(auth_client: AsyncClient):
    """Verify user identity from JWT authentication is correctly propagated."""
    received_user_ids = []

    class CapturingChatService(ChatService):
        async def chat(self, message: str, user_id: str) -> str:
            received_user_ids.append(user_id)
            return "Captured"

    from app.main import app
    from app.services.chat_service import get_chat_service

    app.dependency_overrides[get_chat_service] = lambda: CapturingChatService(
        provider=AsyncMock()
    )
    try:
        resp = await auth_client.post("/api/chat", json={"message": "Hi"})
        assert resp.status_code == 200
        assert len(received_user_ids) == 1
        assert received_user_ids[0] is not None
        assert len(received_user_ids[0]) > 0
    finally:
        app.dependency_overrides.pop(get_chat_service, None)


@pytest.mark.asyncio
async def test_chat_service_unit():
    """Unit tests verifying ChatService validation and delegation behavior."""
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = "Service response"
    service = ChatService(provider=mock_provider)

    # Valid message
    result = await service.chat("  What is 2+2?  ", user_id="usr-123")
    assert result == "Service response"
    mock_provider.generate.assert_called_once_with(prompt="What is 2+2?")

    # Whitespace message raises ValueError
    with pytest.raises(ValueError, match="Message cannot be empty"):
        await service.chat("   ", user_id="usr-123")

    # Empty message raises ValueError
    with pytest.raises(ValueError, match="Message cannot be empty"):
        await service.chat("", user_id="usr-123")

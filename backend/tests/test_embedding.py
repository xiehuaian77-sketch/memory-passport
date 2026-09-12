"""Unit and integration tests for Phase 2.3B: DashScope Embedding Provider."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import APIConnectionError

from app.providers.embedding_provider import (
    DashScopeEmbeddingProvider,
    EmbeddingCommunicationError,
    EmbeddingConfigError,
    EmbeddingInputError,
    EmbeddingValidationError,
)

# ──────────────────────── Unit Tests (Mocked) ────────────────────────

@pytest.mark.asyncio
async def test_embedding_provider_missing_api_key():
    """Missing API key raises EmbeddingConfigError."""
    provider = DashScopeEmbeddingProvider(api_key="")
    with pytest.raises(EmbeddingConfigError) as exc_info:
        await provider.embed("Valid input text")
    assert "not configured" in str(exc_info.value)


@pytest.mark.asyncio
async def test_embedding_provider_empty_text():
    """Empty or whitespace-only input text raises EmbeddingInputError."""
    provider = DashScopeEmbeddingProvider(api_key="mock-test-key")
    with pytest.raises(EmbeddingInputError) as exc_info:
        await provider.embed("")
    assert "non-empty" in str(exc_info.value)

    with pytest.raises(EmbeddingInputError):
        await provider.embed("     ")


@pytest.mark.asyncio
async def test_embedding_provider_invalid_response():
    """Empty or malformed response data raises EmbeddingValidationError."""
    provider = DashScopeEmbeddingProvider(api_key="mock-test-key")

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.data = []  # empty data list
    mock_client.embeddings.create = AsyncMock(return_value=mock_resp)
    provider._client = mock_client

    with pytest.raises(EmbeddingValidationError) as exc_info:
        await provider.embed("Some text")
    assert "empty or malformed" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_embedding_provider_dimension_validation():
    """Dimension mismatch or non-numeric elements raise EmbeddingValidationError."""
    provider = DashScopeEmbeddingProvider(api_key="mock-test-key", dimensions=1024)

    # 1. Returned dimension is 512 instead of 1024
    mock_client = MagicMock()
    mock_item = MagicMock()
    mock_item.embedding = [0.1] * 512
    mock_resp = MagicMock()
    mock_resp.data = [mock_item]
    mock_client.embeddings.create = AsyncMock(return_value=mock_resp)
    provider._client = mock_client

    with pytest.raises(EmbeddingValidationError) as exc_info:
        await provider.embed("Some text")
    assert "dimension mismatch" in str(exc_info.value).lower()

    # 2. Returned embedding contains non-numeric elements
    mock_item.embedding = ["not_a_number"] * 1024
    with pytest.raises(EmbeddingValidationError) as exc_info2:
        await provider.embed("Some text")
    assert "non-numeric" in str(exc_info2.value).lower()


@pytest.mark.asyncio
async def test_embedding_provider_api_error():
    """Network connection or upstream API errors raise EmbeddingCommunicationError."""
    provider = DashScopeEmbeddingProvider(api_key="mock-test-key")

    mock_client = MagicMock()
    mock_client.embeddings.create = AsyncMock(
        side_effect=APIConnectionError(request=MagicMock())
    )
    provider._client = mock_client

    with pytest.raises(EmbeddingCommunicationError) as exc_info:
        await provider.embed("Some text")
    assert "API" in str(exc_info.value)


# ──────────────────────── Live DashScope Test ────────────────────────

@pytest.mark.asyncio
async def test_real_dashscope_embedding_if_key_available():
    """Live API test against Alibaba Cloud DashScope qwen3.7-text-embedding-flash (1024-dim)."""
    from app.config import settings

    api_key = settings.get_embedding_api_key()
    if not api_key:
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("LLM_API_KEY=") or line.strip().startswith("DASHSCOPE_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break

    if not api_key:
        pytest.skip("No DashScope API key available in environment; skipping live test")

    provider = DashScopeEmbeddingProvider(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen3.7-text-embedding-flash",
        dimensions=1024,
    )

    from sqlalchemy import func, select

    from app.models.memory import Memory
    from tests.conftest import TestSession

    async with TestSession() as session:
        count_before = await session.scalar(select(func.count(Memory.id)))
        assert count_before == 0

    test_text = "我喜欢研究人工智能 Agent 和自动化工作流。"
    embedding = await provider.embed(test_text)

    # Confirm NO DB write occurred
    async with TestSession() as session:
        count_after = await session.scalar(select(func.count(Memory.id)))
        assert count_after == 0, "Embedding generation must not write to the database"

    # 1. Returned type is list
    assert isinstance(embedding, list), "Embedding must be a list"

    # 2. Returned dimension is exactly 1024
    assert len(embedding) == 1024, f"Expected 1024 dimensions, got {len(embedding)}"

    # 3. All items are float numbers
    assert all(isinstance(x, float) for x in embedding), "All embedding elements must be floats"

    # 4. Check vector magnitude is non-zero
    magnitude = sum(x * x for x in embedding)
    assert magnitude > 0.0, "Embedding vector magnitude must be non-zero"

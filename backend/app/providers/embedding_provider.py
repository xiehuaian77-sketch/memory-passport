"""Embedding Provider abstraction and DashScope implementation.

Provides:
- EmbeddingProvider: Protocol defining async embed(text: str) -> list[float]
- DashScopeEmbeddingProvider: Concrete implementation calling Alibaba Cloud DashScope
  OpenAI-compatible embeddings API with model qwen3.7-text-embedding-flash (1024 dim).
- get_embedding_provider(): Factory function.
"""

from __future__ import annotations

import logging
from typing import Protocol

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """Base exception for embedding errors."""


class EmbeddingConfigError(EmbeddingError):
    """Raised when embedding configuration or API key is missing or invalid."""


class EmbeddingInputError(EmbeddingError, ValueError):
    """Raised when embedding input is empty, whitespace, or invalid."""


class EmbeddingCommunicationError(EmbeddingError):
    """Raised when communication with embedding API fails."""


class EmbeddingValidationError(EmbeddingError):
    """Raised when the embedding response or dimensions are invalid."""


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers.

    Implementations must provide an async embed method.
    """

    async def embed(self, text: str) -> list[float]:
        ...


class DashScopeEmbeddingProvider:
    """Embedding provider using Alibaba Cloud DashScope OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        self._api_key = api_key or settings.get_embedding_api_key()
        self._base_url = base_url or settings.embedding_base_url
        self._model = model or settings.embedding_model
        self._dimensions = dimensions or settings.embedding_dimensions
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if not self._api_key:
            raise EmbeddingConfigError("Embedding API key is not configured. Please set it in .env.")
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self._client

    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector for text using DashScope API.

        Validates:
        - text is non-empty and non-whitespace
        - text length does not exceed limit
        - response contains list of numbers with exact target dimensions (1024)
        """
        if not text or not text.strip():
            raise EmbeddingInputError("Input text for embedding must be non-empty string.")

        if len(text) > 8000:
            raise EmbeddingInputError(
                f"Input text length ({len(text)}) exceeds maximum limit of 8000 characters."
            )

        client = self._get_client()

        try:
            resp = await client.embeddings.create(
                model=self._model,
                input=text,
            )
        except (APIConnectionError, RateLimitError, APITimeoutError, APIError) as exc:
            logger.error("DashScope Embedding API call failed: %s", exc.__class__.__name__)
            raise EmbeddingCommunicationError(
                f"Failed to communicate with DashScope Embedding API: {exc.__class__.__name__}"
            ) from exc
        except Exception as exc:
            logger.error("Unexpected error in DashScope embedding: %s", exc.__class__.__name__)
            raise EmbeddingCommunicationError("Unexpected error during embedding generation") from exc

        if not resp.data or not hasattr(resp.data[0], "embedding"):
            raise EmbeddingValidationError("Embedding API returned empty or malformed data")

        vec = resp.data[0].embedding
        if not isinstance(vec, list):
            raise EmbeddingValidationError(f"Expected embedding to be list, got {type(vec)}")

        if len(vec) != self._dimensions:
            raise EmbeddingValidationError(
                f"Embedding dimension mismatch: expected {self._dimensions}, got {len(vec)}"
            )

        try:
            float_vec = [float(x) for x in vec]
        except (TypeError, ValueError) as exc:
            raise EmbeddingValidationError("Embedding contains non-numeric values") from exc

        return float_vec


def get_embedding_provider() -> EmbeddingProvider:
    """Factory function to get the configured EmbeddingProvider."""
    return DashScopeEmbeddingProvider()

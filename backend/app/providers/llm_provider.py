"""AI Provider abstraction and implementations.

Provides:
- AIProvider Protocol defining the interface for LLM text generation.
- QwenProvider implementing AIProvider using OpenAI Python SDK for
  Alibaba Cloud DashScope (OpenAI-compatible) API.
- get_ai_provider() factory function.
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


class LLMConfigError(RuntimeError):
    """Raised when LLM configuration is missing or invalid."""


class LLMCommunicationError(RuntimeError):
    """Raised when communicating with the LLM API fails."""


class AIProvider(Protocol):
    """Protocol for LLM providers.

    Implementations must provide an async ``generate`` method returning plain text.
    """

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        ...


class QwenProvider:
    """Concrete AIProvider using OpenAI SDK against Alibaba Cloud DashScope."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.llm_api_key
        self._base_url = base_url or settings.llm_base_url
        self._model = model or settings.llm_model
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if not self._api_key:
            raise LLMConfigError("LLM_API_KEY is not configured. Please set it in .env.")
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self._client

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate a response from DashScope / Qwen."""
        client = self._get_client()
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            resp = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.2,
                max_tokens=2048,
            )
            return resp.choices[0].message.content or ""
        except (APIConnectionError, RateLimitError, APITimeoutError, APIError) as exc:
            logger.error("DashScope API call failed: %s", exc.__class__.__name__)
            raise LLMCommunicationError(f"Failed to communicate with LLM API: {exc.__class__.__name__}") from exc
        except Exception as exc:
            logger.error("Unexpected error in LLM provider: %s", exc.__class__.__name__)
            raise LLMCommunicationError("Unexpected error during LLM generation") from exc


def get_ai_provider() -> AIProvider:
    """Factory function to get the configured AIProvider."""
    return QwenProvider()

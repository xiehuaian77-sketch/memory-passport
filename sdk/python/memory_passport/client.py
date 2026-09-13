"""Top-level client for Memory Passport Python SDK."""

from __future__ import annotations

# Standard library imports
import os
from collections.abc import Mapping
from types import TracebackType
from typing import Self

# Third‑party imports
import httpx

# Local package imports
from memory_passport.resources.audit import AuditResource
from memory_passport.resources.chat import ChatResource
from memory_passport.resources.conflicts import ConflictsResource
from memory_passport.resources.conversations import ConversationsResource
from memory_passport.resources.evaluation import EvaluationResource
from memory_passport.resources.governance import GovernanceResource
from memory_passport.resources.graph import GraphResource
from memory_passport.resources.lifecycle import LifecycleResource
from memory_passport.resources.memories import MemoriesResource
from memory_passport.resources.search import SearchResource
from memory_passport.transport import MemoryPassportTransport


class MemoryPassportClient:
    """Official synchronous client for Memory Passport REST API.

    Usage:
        from memory_passport import MemoryPassportClient

        client = MemoryPassportClient(
            base_url="http://localhost:8000",
            api_key="your-api-key",
        )
        memories = client.memories.list()
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        *,
        api_key: str | None = None,
        access_token: str | None = None,
        timeout: float | httpx.Timeout = 30.0,
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
        write_timeout: float = 10.0,
        pool_timeout: float = 5.0,
        max_retries: int = 2,
        custom_headers: Mapping[str, str] | None = None,
        httpx_client: httpx.Client | None = None,
    ) -> None:
        resolved_key = (
            api_key
            or access_token
            or os.environ.get("MEMORY_PASSPORT_API_KEY")
            or os.environ.get("MEMORY_PASSPORT_ACCESS_TOKEN")
        )

        self._transport = MemoryPassportTransport(
            base_url=base_url,
            api_key=resolved_key,
            timeout=timeout,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            write_timeout=write_timeout,
            pool_timeout=pool_timeout,
            max_retries=max_retries,
            custom_headers=custom_headers,
            httpx_client=httpx_client,
        )

        # Resource namespaces
        self.memories = MemoriesResource(self._transport)
        self.search = SearchResource(self._transport)
        self.graph = GraphResource(self._transport)
        self.lifecycle = LifecycleResource(self._transport)
        self.conflicts = ConflictsResource(self._transport)
        self.governance = GovernanceResource(self._transport)
        self.audit = AuditResource(self._transport)
        self.conversations = ConversationsResource(self._transport)
        self.chat = ChatResource(self._transport)
        self.evaluation = EvaluationResource(self._transport)

    @property
    def base_url(self) -> str:
        return self._transport.base_url

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_val: BaseException | None, exc_tb: TracebackType | None) -> None:
        self.close()

    def __repr__(self) -> str:
        # Strictly mask credentials: never display API key or tokens
        return f"<MemoryPassportClient base_url={self.base_url!r}>"

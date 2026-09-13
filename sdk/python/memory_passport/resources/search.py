"""Search and retrieval resource client."""

from __future__ import annotations

from datetime import datetime
from memory_passport.models.common import TemporalMode
from memory_passport.models.search import (
    AssembledContext,
    SemanticSearchResponse,
)
from memory_passport.transport import MemoryPassportTransport


class SearchResource:
    """Resource client for search and context retrieval endpoints."""

    def __init__(self, transport: MemoryPassportTransport) -> None:
        self._transport = transport

    def semantic(self, query: str, *, limit: int = 10) -> SemanticSearchResponse:
        payload = {
            "query": query,
            "limit": limit,
            "search_mode": "semantic",
        }
        res = self._transport.request("POST", "/api/memories/search", json=payload)
        return SemanticSearchResponse.model_validate(res)

    def keyword(self, query: str, *, limit: int = 10) -> SemanticSearchResponse:
        payload = {
            "query": query,
            "limit": limit,
            "search_mode": "keyword",
        }
        res = self._transport.request("POST", "/api/memories/search", json=payload)
        return SemanticSearchResponse.model_validate(res)

    def hybrid(self, query: str, *, limit: int = 10) -> SemanticSearchResponse:
        payload = {
            "query": query,
            "limit": limit,
            "search_mode": "hybrid",
        }
        res = self._transport.request("POST", "/api/memories/hybrid-search", json=payload)
        return SemanticSearchResponse.model_validate(res)

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 10,
        min_relevance: float = 0.30,
        min_importance: float = 0.0,
        min_confidence: float = 0.0,
        memory_types: list[str] | None = None,
        recency_half_life_days: float = 30.0,
        max_memories: int = 10,
        max_content_chars: int = 500,
        max_context_chars: int = 4000,
        status: str | None = "active",
        temporal_mode: str | TemporalMode = TemporalMode.CURRENT,
        reference_time: datetime | None = None,
        graph_enabled: bool = False,
        graph_seed_limit: int = 5,
        graph_max_expanded: int = 20,
    ) -> AssembledContext:
        """Retrieve assembled context with server-side graph expansion and temporal evaluation."""
        t_mode = temporal_mode.value if isinstance(temporal_mode, TemporalMode) else temporal_mode
        payload = {
            "query": query,
            "top_k": top_k,
            "min_relevance": min_relevance,
            "min_importance": min_importance,
            "min_confidence": min_confidence,
            "memory_types": memory_types,
            "recency_half_life_days": recency_half_life_days,
            "max_memories": max_memories,
            "max_content_chars": max_content_chars,
            "max_context_chars": max_context_chars,
            "status": status,
            "temporal_mode": t_mode,
            "reference_time": reference_time.isoformat() if reference_time else None,
            "graph_enabled": graph_enabled,
            "graph_seed_limit": graph_seed_limit,
            "graph_max_expanded": graph_max_expanded,
        }
        res = self._transport.request("POST", "/api/memories/retrieve", json=payload)
        return AssembledContext.model_validate(res)

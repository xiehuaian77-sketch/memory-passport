"""Search and context retrieval models."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from memory_passport.models.common import BaseSDKModel


class SemanticSearchItem(BaseSDKModel):
    id: str
    content: str
    memory_type: str
    importance: float = 0.5
    confidence: float = 1.0
    similarity: float | None = None
    keyword_score: float | None = None
    hybrid_score: float | None = None
    created_at: datetime
    updated_at: datetime


class SemanticSearchResponse(BaseSDKModel):
    items: list[SemanticSearchItem]
    query: str
    limit: int
    search_mode: str = "semantic"


class AssembledMemoryItem(BaseSDKModel):
    id: str
    memory_type: str
    content: str
    source: str
    importance: float
    confidence: float
    retrieval_score: float
    hybrid_score: float
    recency_score: float | None = None
    is_truncated: bool = False
    original_char_count: int = 0


class AssembledContext(BaseSDKModel):


    items: list[AssembledMemoryItem] = Field(default_factory=list)
    total_memories: int = 0
    total_chars: int = 0
    max_context_chars: int
    max_content_chars: int

    def format_text(self) -> str:
        """Format context into prompt injection string."""
        if not self.items:
            return ""
        blocks: list[str] = []
        for i, item in enumerate(self.items, 1):
            blocks.append(
                f"[{i}] ({item.memory_type}) {item.content} "
                f"(relevance: {item.retrieval_score:.2f})"
            )
        return "\n".join(blocks)

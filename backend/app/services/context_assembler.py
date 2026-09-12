"""Context Assembler service (Phase 2.5B).

Assembles retrieval policy results into a deduplicated, length-bounded,
and stably ordered context object for downstream AI / MCP consumption.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ContextAssemblyConfig(BaseModel):
    """Configuration for context assembly."""

    max_memories: int = Field(
        default=10,
        ge=1,
        description="Maximum number of memories in the assembled context",
    )
    max_content_chars: int = Field(
        default=500,
        ge=1,
        description="Maximum characters allowed for a single memory content",
    )
    max_context_chars: int = Field(
        default=4000,
        ge=1,
        description="Maximum total characters of memory contents in assembled context",
    )

    model_config = {"extra": "forbid"}

    @field_validator("max_memories", "max_content_chars", "max_context_chars")
    @classmethod
    def validate_positive_integers(cls, v: int, info: Any) -> int:
        if v < 1:
            raise ValueError(f"{info.field_name} must be >= 1, got {v}")
        return v


class AssembledMemoryItem(BaseModel):
    """A single memory item prepared and budgeted for context."""

    id: str = Field(description="Memory unique identifier")
    memory_type: str = Field(description="Memory type or category")
    content: str = Field(
        description="Memory content (truncated if exceeding max_content_chars)"
    )
    source: str = Field(description="Source of memory, e.g. manual, ai_extracted")
    importance: float = Field(description="Importance weight in [0.0, 1.0]")
    confidence: float = Field(description="Confidence weight in [0.0, 1.0]")
    retrieval_score: float = Field(
        description="Multi-factor retrieval score from retrieval policy"
    )
    hybrid_score: float = Field(description="Original hybrid search score")
    recency_score: float | None = Field(
        default=None, description="Recency decay score if provided by retrieval policy"
    )
    is_truncated: bool = Field(
        default=False,
        description="Whether content was truncated due to max_content_chars",
    )
    original_char_count: int = Field(
        default=0,
        description="Character count of the original memory content before truncation",
    )

    model_config = {"extra": "ignore"}


class AssembledContext(BaseModel):
    """Aggregated, budgeted context ready for AI consumption."""

    items: list[AssembledMemoryItem] = Field(
        default_factory=list, description="Ordered list of assembled memory items"
    )
    total_memories: int = Field(
        default=0, description="Number of memories included in context"
    )
    total_chars: int = Field(
        default=0, description="Total characters across all assembled memory contents"
    )
    max_context_chars: int = Field(
        description="Context total character budget"
    )
    max_content_chars: int = Field(
        description="Single memory character limit"
    )

    model_config = {"extra": "ignore"}

    def format_text(self) -> str:
        """Render context items as formatted text suitable for prompt injection."""
        if not self.items:
            return ""
        blocks: list[str] = []
        for i, item in enumerate(self.items, 1):
            blocks.append(
                f"[{i}] ({item.memory_type}) {item.content} "
                f"(relevance: {item.retrieval_score:.2f})"
            )
        return "\n".join(blocks)

    def to_dict(self) -> dict[str, Any]:
        """Serialize context to dictionary."""
        return self.model_dump()


def _get_val(target: Any, *attr_names: str, default: Any = None) -> Any:
    """Helper to safely extract field values from dicts, dataclasses, or Pydantic/ORM models."""
    for name in attr_names:
        if isinstance(target, dict) and name in target:
            val = target[name]
            if val is not None:
                return val
        elif hasattr(target, name):
            val = getattr(target, name)
            if val is not None:
                return val
    return default


class ContextAssembler:
    """Service to assemble retrieval results into a bounded, deduplicated Context."""

    def __init__(self, config: ContextAssemblyConfig | None = None) -> None:
        self.config = config or ContextAssemblyConfig()

    def assemble(self, candidates: Sequence[Any]) -> AssembledContext:
        """Assemble retrieval results into an AssembledContext.

        Steps:
        1. Return empty context for empty input.
        2. Deduplicate candidates by memory ID (first encounter in retrieval order wins).
        3. For each unique candidate:
           a. Check max_memories limit.
           b. Truncate content if len > max_content_chars without modifying original memory.
           c. Check context total character budget: if adding item exceeds max_context_chars, skip it.
           d. Add item to assembled list.
        4. Return AssembledContext with complete metadata.
        """
        if not candidates:
            return AssembledContext(
                items=[],
                total_memories=0,
                total_chars=0,
                max_context_chars=self.config.max_context_chars,
                max_content_chars=self.config.max_content_chars,
            )

        seen_ids: set[str] = set()
        assembled_items: list[AssembledMemoryItem] = []
        current_chars: int = 0

        for candidate in candidates:
            if len(assembled_items) >= self.config.max_memories:
                break

            # Extract memory object if wrapped (e.g. ScoredMemory)
            mem = getattr(candidate, "memory", candidate)
            mem_id = str(_get_val(mem, "id", default="") or "")
            if not mem_id:
                continue

            # Deduplication: same memory ID is only included once
            if mem_id in seen_ids:
                continue
            seen_ids.add(mem_id)

            # Extract attributes
            mem_type = str(_get_val(mem, "memory_type", "category", default="context"))
            source = str(_get_val(mem, "source", default="manual"))
            importance = float(_get_val(mem, "importance", default=0.5))
            confidence = float(_get_val(mem, "confidence", default=1.0))

            # Scores: preserve original retrieval scores without mutation
            retrieval_score = float(
                _get_val(
                    candidate,
                    "retrieval_score",
                    default=_get_val(candidate, "hybrid_score", default=0.0),
                )
            )
            hybrid_score = float(_get_val(candidate, "hybrid_score", default=0.0))
            raw_recency = _get_val(candidate, "recency_score", default=None)
            recency_score = float(raw_recency) if raw_recency is not None else None

            # Content truncation (without modifying original memory object)
            raw_content = str(_get_val(mem, "content", default="") or "")
            orig_len = len(raw_content)

            if orig_len > self.config.max_content_chars:
                truncated_content = raw_content[: self.config.max_content_chars]
                is_truncated = True
            else:
                truncated_content = raw_content
                is_truncated = False

            item_len = len(truncated_content)

            # Context budget check: final context contents cannot exceed max_context_chars
            if current_chars + item_len > self.config.max_context_chars:
                continue

            assembled_items.append(
                AssembledMemoryItem(
                    id=mem_id,
                    memory_type=mem_type,
                    content=truncated_content,
                    source=source,
                    importance=importance,
                    confidence=confidence,
                    retrieval_score=retrieval_score,
                    hybrid_score=hybrid_score,
                    recency_score=recency_score,
                    is_truncated=is_truncated,
                    original_char_count=orig_len,
                )
            )
            current_chars += item_len

        return AssembledContext(
            items=assembled_items,
            total_memories=len(assembled_items),
            total_chars=current_chars,
            max_context_chars=self.config.max_context_chars,
            max_content_chars=self.config.max_content_chars,
        )

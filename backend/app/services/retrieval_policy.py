"""Memory Retrieval Policy layer (Phase 2.5A).

Applies deterministic filtering, recency exponential decay, multi-factor re-ranking,
and top-k selection on search candidate memories.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from app.models.memory import Memory


class RetrievalPolicyConfig(BaseModel):
    """Configuration for retrieval policy execution."""

    top_k: int = Field(default=10, ge=1, le=50, description="Max items to retrieve")
    min_relevance: float = Field(
        default=0.30, ge=0.0, le=1.0, description="Minimum hybrid score required"
    )
    min_importance: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum importance required"
    )
    min_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum confidence required"
    )
    memory_types: list[str] | None = Field(
        default=None, description="Optional allowed memory types / categories"
    )
    recency_half_life_days: float = Field(
        default=30.0, gt=0.0, description="Recency decay half life in days"
    )
    status: str | None = Field(
        default="active", description="Filter by status: active, archived, or None for all"
    )
    temporal_mode: str = Field(
        default="current",
        pattern=r"^(current|historical|any)$",
        description="Temporal retrieval mode: current (default), historical, any",
    )
    reference_time: datetime | None = Field(
        default=None,
        description="Optional reference time for temporal filtering (defaults to now)",
    )

    model_config = {"extra": "forbid"}

    @field_validator("memory_types")
    @classmethod
    def validate_memory_types(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            cleaned = [t.strip() for t in v if t and t.strip()]
            return cleaned if cleaned else None
        return None


@dataclass(frozen=True)
class ScoredMemory:
    """Wrapper holding a Memory, its original search scores, recency, and retrieval score."""

    memory: Memory
    similarity: float | None
    keyword_score: float | None
    hybrid_score: float
    recency_score: float
    retrieval_score: float


class MemoryRetrievalPolicy:
    """Deterministic policy engine for memory retrieval."""

    def __init__(self, config: RetrievalPolicyConfig | None = None) -> None:
        self.config = config or RetrievalPolicyConfig()

    @staticmethod
    def calculate_recency(
        dt: datetime | None,
        now: datetime,
        half_life_days: float,
    ) -> float:
        """Calculate exponential recency score in [0.0, 1.0].

        recency_score = 0.5 ** (age_days / half_life)
        """
        if dt is None:
            return 0.0

        # Normalize timezones
        if dt.tzinfo is None and now.tzinfo is not None:
            dt = dt.replace(tzinfo=timezone.utc)
        elif dt.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        age_seconds = max(0.0, (now - dt).total_seconds())
        age_days = age_seconds / 86400.0
        recency = 0.5 ** (age_days / half_life_days)
        return max(0.0, min(1.0, round(recency, 4)))

    def apply(
        self,
        candidates: Sequence[Any],
        now: datetime | None = None,
    ) -> list[ScoredMemory]:
        """Apply retrieval policy to candidate items."""
        if not candidates:
            return []

        ref_now = self.config.reference_time or now or datetime.now(timezone.utc)
        if ref_now.tzinfo is None:
            ref_now = ref_now.replace(tzinfo=timezone.utc)

        allowed_types = (
            set(self.config.memory_types) if self.config.memory_types else None
        )

        filtered_and_scored: list[ScoredMemory] = []

        for c in candidates:
            mem = getattr(c, "memory", c)
            hybrid_sc = float(getattr(c, "hybrid_score", 0.0))
            sim = getattr(c, "similarity", None)
            kw_sc = getattr(c, "keyword_score", None)

            mem_status = getattr(mem, "status", None) or "active"
            v_from = getattr(mem, "valid_from", None)
            v_until = getattr(mem, "valid_until", None)
            superseded_by = getattr(mem, "superseded_by_memory_id", None)

            if v_from is not None and v_from.tzinfo is None:
                v_from = v_from.replace(tzinfo=timezone.utc)
            if v_until is not None and v_until.tzinfo is None:
                v_until = v_until.replace(tzinfo=timezone.utc)

            # 0. Temporal Filtering
            mode = self.config.temporal_mode
            if mode == "current":
                if mem_status != "active":
                    continue
                if superseded_by is not None or mem_status == "superseded":
                    continue
                if v_until is not None and v_until <= ref_now:
                    continue
                if v_from is not None and v_from > ref_now:
                    continue
            elif mode == "historical":
                is_historical = (
                    mem_status == "superseded"
                    or superseded_by is not None
                    or (v_until is not None and v_until <= ref_now)
                    or mem_status == "archived"
                )
                if not is_historical:
                    continue
            elif mode == "any":
                if self.config.status is not None and mem_status != self.config.status:
                    continue

            # 1. Filter: min_relevance (hybrid_score)
            if hybrid_sc < self.config.min_relevance:
                continue

            # 2. Filter: min_importance
            importance = float(getattr(mem, "importance", 0.5))
            if importance < self.config.min_importance:
                continue

            # 3. Filter: min_confidence
            confidence = float(getattr(mem, "confidence", 1.0))
            if confidence < self.config.min_confidence:
                continue

            # 4. Filter: memory_types
            mem_type = getattr(mem, "memory_type", None) or getattr(mem, "category", None)
            if allowed_types is not None and mem_type not in allowed_types:
                continue

            # 5. Compute Recency Score
            target_dt = getattr(mem, "updated_at", None) or getattr(mem, "created_at", None)
            recency_sc = self.calculate_recency(
                target_dt, ref_now, self.config.recency_half_life_days
            )

            # 6. Compute Retrieval Score
            # Formula: 0.70 * hybrid_score + 0.15 * importance + 0.10 * confidence + 0.05 * recency_score
            retrieval_sc = round(
                0.70 * hybrid_sc
                + 0.15 * importance
                + 0.10 * confidence
                + 0.05 * recency_sc,
                4,
            )

            filtered_and_scored.append(
                ScoredMemory(
                    memory=mem,
                    similarity=sim,
                    keyword_score=kw_sc,
                    hybrid_score=hybrid_sc,
                    recency_score=recency_sc,
                    retrieval_score=retrieval_sc,
                )
            )

        # 7. Sorting:
        # retrieval_score DESC -> hybrid_score DESC -> importance DESC -> updated_at DESC -> id ASC
        def sort_key(item: ScoredMemory) -> tuple[float, float, float, float, str]:
            dt = getattr(item.memory, "updated_at", None) or getattr(item.memory, "created_at", None)
            ts = dt.timestamp() if dt else 0.0
            mid = str(getattr(item.memory, "id", ""))
            return (
                -item.retrieval_score,
                -item.hybrid_score,
                -float(getattr(item.memory, "importance", 0.5)),
                -ts,
                mid,
            )

        filtered_and_scored.sort(key=sort_key)

        # 8. Top-K
        return filtered_and_scored[: self.config.top_k]

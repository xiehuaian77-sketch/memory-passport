"""Graph-aware Retrieval Service (Phase 5.4B).

Enhances base memory retrieval results with bounded 1-hop relationship graph signals.
Base retrieval remains primary; graph expansion is a secondary additive enhancement.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.repositories import memory_relationship_repo
from app.services.retrieval_policy import ScoredMemory


# Relationship type bonus weights (capped at +0.15 total bonus)
GRAPH_RELATIONSHIP_WEIGHTS: dict[str, float] = {
    "updates": 0.15,
    "supersedes": 0.15,
    "contradicts": 0.10,
    "relevant_to": 0.05,
}
MAX_GRAPH_BONUS = 0.15
HARD_MAX_SEEDS = 10
HARD_MAX_EXPANDED = 50


class GraphAwareRetrievalService:
    """Orchestrates 1-hop relationship graph expansion and deterministic re-ranking."""

    @staticmethod
    def calculate_edge_bonus(rel_type: str | None, confidence: float | None) -> float:
        """Compute bonus for a single relationship edge."""
        if not rel_type:
            return 0.0
        normalized_type = str(rel_type).lower().split(".")[-1]
        weight = GRAPH_RELATIONSHIP_WEIGHTS.get(normalized_type, 0.0)
        conf = 1.0 if confidence is None else max(0.0, min(1.0, float(confidence)))
        return weight * conf

    @classmethod
    async def expand_and_rerank(
        cls,
        db: AsyncSession,
        user_id: str,
        base_scored_memories: list[ScoredMemory],
        *,
        graph_enabled: bool = False,
        graph_seed_limit: int = 5,
        graph_max_expanded: int = 20,
        top_k: int = 10,
        min_relevance: float = 0.30,
        min_importance: float = 0.0,
        min_confidence: float = 0.0,
        memory_types: list[str] | None = None,
        temporal_mode: str = "current",
        reference_time: datetime | None = None,
        status: str | None = "active",
    ) -> list[ScoredMemory]:
        """Expand base retrieval candidates with 1-hop graph neighbors and deterministically re-rank.

        Steps:
        1. If graph_enabled is False or base candidates empty, return base candidates.
        2. Pick top min(len(base), seed_limit) candidates as seeds (hard cap 10).
        3. Query 1-hop neighbors of seeds from DB with user isolation and temporal filtering.
        4. Calculate graph_bonus per candidate (max +0.15, no negative).
        5. Combine scores:
           - Existing base candidates: final_score = min(1.0, base_score + bonus)
           - New graph neighbors: final_score = min(1.0, bonus) (filtered if < min_relevance)
        6. Apply graph_max_expanded cap (hard cap 50) on new graph-derived memories.
        7. Deterministically sort: (-final_score, -base_score, -importance, -timestamp, id ASC).
        8. Slice to top_k.
        """
        if not graph_enabled or not base_scored_memories:
            return base_scored_memories[:top_k]

        safe_seed_limit = max(1, min(graph_seed_limit, HARD_MAX_SEEDS))
        safe_max_expanded = max(1, min(graph_max_expanded, HARD_MAX_EXPANDED))

        # 1. Select seeds from top base candidates
        seeds = base_scored_memories[:safe_seed_limit]
        seed_ids = [str(s.memory.id) for s in seeds if getattr(s, "memory", None)]
        if not seed_ids:
            return base_scored_memories[:top_k]

        # 2. Batch query 1-hop neighbors
        raw_edges = await memory_relationship_repo.list_batch_related_memories(
            db=db,
            user_id=user_id,
            memory_ids=seed_ids,
            temporal_mode=temporal_mode,
            reference_time=reference_time,
            status=status,
            limit=safe_max_expanded * 2,
        )

        # 3. Aggregate bonuses and index neighbor memories
        neighbor_bonuses: dict[str, float] = {}
        neighbor_memories: dict[str, Memory] = {}

        for edge in raw_edges:
            mem = edge["memory"]
            mem_id = str(mem.id)
            bonus = cls.calculate_edge_bonus(edge.get("rel_type"), edge.get("rel_confidence"))
            neighbor_bonuses[mem_id] = neighbor_bonuses.get(mem_id, 0.0) + bonus
            if mem_id not in neighbor_memories:
                neighbor_memories[mem_id] = mem

        # Clamp total bonus per memory to MAX_GRAPH_BONUS [0.0, 0.15]
        clamped_bonuses = {
            mid: round(min(MAX_GRAPH_BONUS, max(0.0, b)), 4)
            for mid, b in neighbor_bonuses.items()
        }

        # 4. Score base candidates + graph bonus
        base_map: dict[str, ScoredMemory] = {
            str(s.memory.id): s for s in base_scored_memories if getattr(s, "memory", None)
        }

        final_candidates: list[ScoredMemory] = []
        seen_ids: set[str] = set()

        for mid, base_item in base_map.items():
            bonus = clamped_bonuses.get(mid, 0.0)
            new_retrieval_score = round(min(1.0, base_item.retrieval_score + bonus), 4)
            final_candidates.append(
                ScoredMemory(
                    memory=base_item.memory,
                    similarity=base_item.similarity,
                    keyword_score=base_item.keyword_score,
                    hybrid_score=base_item.hybrid_score,
                    recency_score=base_item.recency_score,
                    retrieval_score=new_retrieval_score,
                )
            )
            seen_ids.add(mid)

        # 5. Add new graph-derived neighbors (subject to min_relevance gate and max_expanded cap)
        new_expanded_candidates: list[ScoredMemory] = []
        for mid, mem in neighbor_memories.items():
            if mid in seen_ids:
                continue

            bonus = clamped_bonuses.get(mid, 0.0)
            # Candidate gate: must meet min_relevance
            if bonus < min_relevance:
                continue

            if float(getattr(mem, "importance", 0.5)) < min_importance:
                continue

            if float(getattr(mem, "confidence", 1.0)) < min_confidence:
                continue

            mem_type = getattr(mem, "memory_type", None) or getattr(mem, "category", None)
            if memory_types is not None and mem_type not in memory_types:
                continue

            new_expanded_candidates.append(
                ScoredMemory(
                    memory=mem,
                    similarity=None,
                    keyword_score=None,
                    hybrid_score=0.0,
                    recency_score=0.0,
                    retrieval_score=bonus,
                )
            )

        # Cap the number of newly introduced items
        if len(new_expanded_candidates) > safe_max_expanded:
            new_expanded_candidates.sort(
                key=lambda x: (-x.retrieval_score, str(x.memory.id))
            )
            new_expanded_candidates = new_expanded_candidates[:safe_max_expanded]

        final_candidates.extend(new_expanded_candidates)

        # 6. Deterministic Re-ranking:
        # (-final_score, -base_score, -importance, -timestamp, id ASC)
        def sort_key(item: ScoredMemory) -> tuple[float, float, float, float, str]:
            mem = item.memory
            mid = str(getattr(mem, "id", ""))
            base_score = base_map[mid].retrieval_score if mid in base_map else 0.0
            importance = float(getattr(mem, "importance", 0.5))
            dt = getattr(mem, "updated_at", None) or getattr(mem, "created_at", None)
            ts = dt.timestamp() if dt else 0.0
            return (
                -item.retrieval_score,
                -base_score,
                -importance,
                -ts,
                mid,
            )

        final_candidates.sort(key=sort_key)

        # 7. Deduplication by ID (if any remain) & slice to top_k
        deduped: list[ScoredMemory] = []
        final_seen: set[str] = set()
        for item in final_candidates:
            mid = str(item.memory.id)
            if mid not in final_seen:
                final_seen.add(mid)
                deduped.append(item)
                if len(deduped) >= top_k:
                    break

        return deduped

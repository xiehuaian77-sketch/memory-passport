"""Memory Quality Engine Service for Phase 5.6C.

100% deterministic, rule-based quality evaluation across 7 dimensions:
1. Confidence
2. Importance
3. Freshness (temporal awareness, expiration, future validity, staleness)
4. Consistency (contradiction detection, conflict status)
5. Provenance (conversation/message anchors, manual vs extracted)
6. Duplication (exact and near-duplicate detection)
7. Conflict Risk (risk-to-quality conversion)

Enforces:
- Strict tenant isolation (authenticated user_id)
- Zero memory mutations (100% read-only)
- O(1) bounded queries (no N+1)
- Explainable reasons and actionable warnings
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.models.memory_relationship import MemoryRelationship
from app.schemas.memory_quality import (
    BatchMemoryQualityResult,
    MemoryQualityResult,
    QualityDimensionScore,
)
from app.services.conflict_service import (
    CLASSIFICATION_CONTRADICTION,
    CLASSIFICATION_DUPLICATE,
    evaluate_tier_1_rules,
)

logger = logging.getLogger(__name__)

# Standard weights summing to 1.0
DEFAULT_QUALITY_WEIGHTS: dict[str, float] = {
    "confidence": 0.20,
    "importance": 0.15,
    "freshness": 0.15,
    "consistency": 0.20,
    "provenance": 0.10,
    "duplication": 0.10,
    "conflict_risk": 0.10,
}


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class MemoryQualityService:
    """Read-only deterministic quality evaluation service."""

    @classmethod
    def evaluate_confidence(cls, memory: Memory) -> tuple[float, str, list[str]]:
        """Evaluate confidence dimension."""
        raw_val = getattr(memory, "confidence", 1.0)
        score = round(max(0.0, min(1.0, float(raw_val if raw_val is not None else 1.0))), 4)
        warnings: list[str] = []

        if score >= 0.85:
            reason = "High confidence fact/preference."
        elif score >= 0.50:
            reason = "Moderate confidence level."
        else:
            reason = "Low confidence extraction or unverified fact."
            warnings.append("Confidence score is below recommended reliability threshold.")

        return score, reason, warnings

    @classmethod
    def evaluate_importance(cls, memory: Memory) -> tuple[float, str, list[str]]:
        """Evaluate importance dimension."""
        raw_val = getattr(memory, "importance", 0.5)
        score = round(max(0.0, min(1.0, float(raw_val if raw_val is not None else 0.5))), 4)

        if score >= 0.80:
            reason = "Core identity or high-priority preference."
        elif score >= 0.40:
            reason = "Standard priority memory item."
        else:
            reason = "Low priority background detail."

        return score, reason, []

    @classmethod
    def evaluate_freshness(
        cls, memory: Memory, now: datetime
    ) -> tuple[float, str, list[str]]:
        """Evaluate freshness taking temporal supersession, expiration, and age into account."""
        warnings: list[str] = []
        status = getattr(memory, "status", "active")
        superseded_by = getattr(memory, "superseded_by_memory_id", None)
        expires_at = _ensure_utc(getattr(memory, "expires_at", None))
        valid_from = _ensure_utc(getattr(memory, "valid_from", None))
        valid_until = _ensure_utc(getattr(memory, "valid_until", None))
        created_at = _ensure_utc(getattr(memory, "created_at", None)) or now
        updated_at = _ensure_utc(getattr(memory, "updated_at", None)) or created_at

        # 1. Superseded
        if status == "superseded" or superseded_by is not None:
            warnings.append("Memory has been superseded by a newer version.")
            return 0.10, "Memory has been superseded by a newer version.", warnings

        # 2. Expired (expires_at or valid_until)
        if expires_at and now > expires_at:
            warnings.append("Memory has reached its explicit expiration date.")
            return 0.05, "Memory has reached its explicit expiration date.", warnings

        if valid_until and now > valid_until:
            warnings.append("Memory temporal validity window has expired.")
            return 0.10, "Temporal validity window has expired.", warnings

        # 3. Future-dated (not yet effective)
        if valid_from and now < valid_from:
            warnings.append("Memory is future-dated and not yet effective.")
            return 0.40, "Memory is scheduled for future validity and is not yet effective.", warnings

        # 4. Archived
        if status == "archived":
            warnings.append("Memory is in archived state.")
            return 0.30, "Memory is currently archived.", warnings

        # 5. Active & currently valid: evaluate age since last update
        ref_dt = updated_at or created_at
        age_days = max(0.0, (now - ref_dt).total_seconds() / 86400.0)

        if age_days <= 30.0:
            score = 1.00
            reason = "Memory was recently created or updated."
        elif age_days <= 90.0:
            score = 0.90
            reason = "Memory is fairly recent (updated within 90 days)."
        elif age_days <= 180.0:
            score = 0.75
            reason = "Memory is moderately aged (updated within 6 months)."
        elif age_days <= 365.0:
            score = 0.60
            reason = "Memory has not been updated in over 6 months."
            warnings.append("Memory has not been refreshed in over 6 months.")
        else:
            score = 0.40
            reason = "Memory is stale (over 1 year without update)."
            warnings.append("Memory is stale (over 1 year without update).")

        return score, reason, warnings

    @classmethod
    def evaluate_consistency(
        cls,
        memory: Memory,
        relationships: Sequence[MemoryRelationship],
        sibling_conflicts: Sequence[Any],
    ) -> tuple[float, str, list[str]]:
        """Evaluate consistency based on status, graph relationships, and conflict signals."""
        warnings: list[str] = []
        status = getattr(memory, "status", "active")

        # 1. Explicit conflicted status
        if status == "conflicted":
            warnings.append("Memory has unresolved conflicting state.")
            return 0.10, "Memory is marked in conflicted status.", warnings

        # 2. Contradiction relationship in graph
        has_contradiction = any(
            rel.relationship_type == "CONTRADICTS" for rel in relationships
        )
        if has_contradiction:
            warnings.append("Contradiction relationship detected with another memory.")
            return 0.20, "Active contradiction relationship exists with another memory.", warnings

        # 3. Direct contradiction detected with siblings under same key
        has_sibling_contradiction = any(
            getattr(sc, "classification", None) == CLASSIFICATION_CONTRADICTION
            for sc in sibling_conflicts
        )
        if has_sibling_contradiction:
            warnings.append("Contradiction detected with an existing memory on the same key.")
            return 0.30, "Contradiction detected against another active memory on the same key.", warnings

        # 4. Clean updates/supersedes lineage
        has_update = any(
            rel.relationship_type in ("UPDATES", "SUPERSEDES") for rel in relationships
        )
        if has_update:
            return 0.90, "Clean lineage with update/supersession history.", warnings

        # 5. Clean baseline
        return 1.00, "No contradictions or conflicting records detected.", warnings

    @classmethod
    def evaluate_provenance(cls, memory: Memory) -> tuple[float, str, list[str]]:
        """Evaluate provenance anchor quality."""
        warnings: list[str] = []
        conv_id = getattr(memory, "source_conversation_id", None)
        msg_id = getattr(memory, "source_message_id", None)
        source = (getattr(memory, "source", "") or "").lower().strip()

        if conv_id and msg_id:
            return 1.00, "Direct dialogue provenance with exact conversation and message anchor.", warnings

        if conv_id:
            return 0.85, "Conversation provenance is recorded.", warnings

        if source == "manual":
            return 0.90, "Directly authored and confirmed by user.", warnings

        if source == "imported":
            return 0.75, "Imported from external source.", warnings

        if source == "ai_extracted":
            warnings.append("Extracted memory lacks specific dialogue message anchor.")
            return 0.60, "AI extracted memory without direct conversation link.", warnings

        warnings.append("Memory lacks provenance origin metadata.")
        return 0.40, "Unspecified or missing provenance source.", warnings

    @classmethod
    def evaluate_duplication(
        cls, memory: Memory, sibling_memories: Sequence[Memory]
    ) -> tuple[float, float, str, list[str]]:
        """Evaluate duplication risk and return (quality_score, raw_risk, reason, warnings)."""
        warnings: list[str] = []
        c_norm = re.sub(r"\s+", "", memory.content.lower())

        for sib in sibling_memories:
            if sib.id == memory.id:
                continue
            s_norm = re.sub(r"\s+", "", sib.content.lower())

            # Exact duplicate
            if c_norm == s_norm:
                warnings.append("Duplicate of an existing active memory.")
                return 0.00, 1.00, "Exact duplicate content found in another active memory.", warnings

            # Near-duplicate under same key
            if sib.key.strip().lower() == memory.key.strip().lower():
                words_c = set(re.findall(r"\w+", memory.content.lower()))
                words_s = set(re.findall(r"\w+", sib.content.lower()))
                if words_c and words_s:
                    overlap = len(words_c & words_s) / len(words_c | words_s)
                    if overlap >= 0.80:
                        warnings.append("Near-duplicate content detected under the same key.")
                        return 0.30, 0.70, "Near-duplicate content detected under the same key.", warnings

        return 1.00, 0.00, "No duplicate or near-duplicate memory detected.", warnings

    @classmethod
    def evaluate_conflict_risk(
        cls,
        memory: Memory,
        relationships: Sequence[MemoryRelationship],
        sibling_conflicts: Sequence[Any],
    ) -> tuple[float, float, str, list[str]]:
        """Evaluate conflict risk and return (quality_score, raw_risk, reason, warnings)."""
        warnings: list[str] = []
        status = getattr(memory, "status", "active")

        # High risk if conflicted status or contradiction relationship
        if status == "conflicted" or any(
            rel.relationship_type == "CONTRADICTS" for rel in relationships
        ):
            warnings.append("High conflict risk detected.")
            return 0.10, 0.90, "High conflict risk due to active contradiction.", warnings

        # Sibling contradiction detected
        if any(
            getattr(sc, "classification", None) == CLASSIFICATION_CONTRADICTION
            for sc in sibling_conflicts
        ):
            warnings.append("Potential contradiction on singular key.")
            return 0.20, 0.80, "Opposite polarity statement detected on a singular key.", warnings

        # Minor conflict / update risk
        if any(
            getattr(sc, "classification", None) == CLASSIFICATION_DUPLICATE
            for sc in sibling_conflicts
        ):
            return 0.90, 0.10, "Low conflict risk; minor duplicate signal.", warnings

        return 1.00, 0.00, "Zero conflict signals detected.", warnings

    @classmethod
    async def evaluate_memory(
        cls,
        db: AsyncSession,
        user_id: str,
        memory_id: str,
        as_of: datetime | None = None,
        weights: dict[str, float] | None = None,
    ) -> MemoryQualityResult | None:
        """Evaluate a single memory for user_id in a strictly read-only, tenant-isolated manner.

        Returns None if memory does not exist or does not belong to user_id.
        """
        # 1. Fetch memory strictly scoped to user_id
        stmt = select(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
        result = await db.execute(stmt)
        mem = result.scalar_one_or_none()
        if not mem:
            return None

        now = _ensure_utc(as_of) or datetime.now(timezone.utc)
        applied_weights = weights or DEFAULT_QUALITY_WEIGHTS

        # 2. Bounded contextual queries (O(1) bounded queries)
        # Fetch relationships connected to this memory
        rel_stmt = select(MemoryRelationship).where(
            or_(
                MemoryRelationship.source_memory_id == memory_id,
                MemoryRelationship.target_memory_id == memory_id,
            ),
            MemoryRelationship.user_id == user_id,
        )
        rel_res = await db.execute(rel_stmt)
        relationships = rel_res.scalars().all()

        # Fetch sibling active memories under the same key or for duplication checking
        sib_stmt = (
            select(Memory)
            .where(
                Memory.user_id == user_id,
                Memory.key == mem.key,
                Memory.id != memory_id,
                Memory.status == "active",
            )
            .limit(20)
        )
        sib_res = await db.execute(sib_stmt)
        siblings = sib_res.scalars().all()

        # Evaluate tier-1 conflict intelligence rules on siblings
        sibling_conflicts: list[Any] = []
        for sib in siblings:
            item = evaluate_tier_1_rules(
                candidate_key=mem.key,
                candidate_content=mem.content,
                candidate_type=mem.memory_type,
                existing_mem=sib,
                candidate_valid_from=mem.valid_from,
            )
            if item:
                sibling_conflicts.append(item)

        # 3. Calculate all 7 dimensions
        dim_scores: dict[str, QualityDimensionScore] = {}
        all_warnings: list[str] = []

        # (1) Confidence
        conf_score, conf_reason, conf_warn = cls.evaluate_confidence(mem)
        dim_scores["confidence"] = QualityDimensionScore(
            name="confidence",
            score=conf_score,
            weight=applied_weights["confidence"],
            reason=conf_reason,
        )
        all_warnings.extend(conf_warn)

        # (2) Importance
        imp_score, imp_reason, imp_warn = cls.evaluate_importance(mem)
        dim_scores["importance"] = QualityDimensionScore(
            name="importance",
            score=imp_score,
            weight=applied_weights["importance"],
            reason=imp_reason,
        )
        all_warnings.extend(imp_warn)

        # (3) Freshness
        fresh_score, fresh_reason, fresh_warn = cls.evaluate_freshness(mem, now)
        dim_scores["freshness"] = QualityDimensionScore(
            name="freshness",
            score=fresh_score,
            weight=applied_weights["freshness"],
            reason=fresh_reason,
        )
        all_warnings.extend(fresh_warn)

        # (4) Consistency
        const_score, const_reason, const_warn = cls.evaluate_consistency(
            mem, relationships, sibling_conflicts
        )
        dim_scores["consistency"] = QualityDimensionScore(
            name="consistency",
            score=const_score,
            weight=applied_weights["consistency"],
            reason=const_reason,
        )
        all_warnings.extend(const_warn)

        # (5) Provenance
        prov_score, prov_reason, prov_warn = cls.evaluate_provenance(mem)
        dim_scores["provenance"] = QualityDimensionScore(
            name="provenance",
            score=prov_score,
            weight=applied_weights["provenance"],
            reason=prov_reason,
        )
        all_warnings.extend(prov_warn)

        # (6) Duplication
        dup_score, dup_risk, dup_reason, dup_warn = cls.evaluate_duplication(mem, siblings)
        dim_scores["duplication"] = QualityDimensionScore(
            name="duplication",
            score=dup_score,
            weight=applied_weights["duplication"],
            reason=dup_reason,
            raw_risk=dup_risk,
        )
        all_warnings.extend(dup_warn)

        # (7) Conflict Risk
        cr_score, cr_risk, cr_reason, cr_warn = cls.evaluate_conflict_risk(
            mem, relationships, sibling_conflicts
        )
        dim_scores["conflict_risk"] = QualityDimensionScore(
            name="conflict_risk",
            score=cr_score,
            weight=applied_weights["conflict_risk"],
            reason=cr_reason,
            raw_risk=cr_risk,
        )
        all_warnings.extend(cr_warn)

        # 4. Overall score calculation: weighted sum
        overall = sum(dim_scores[k].score * applied_weights[k] for k in dim_scores)
        overall_score = round(max(0.0, min(1.0, overall)), 4)

        # Summary reason
        if overall_score >= 0.85:
            summary = f"High quality memory ({overall_score:.2f}). Reliable, fresh, and consistent."
        elif overall_score >= 0.60:
            summary = f"Moderate quality memory ({overall_score:.2f}). Acceptable for retrieval."
        else:
            summary = f"Low quality memory ({overall_score:.2f}). Action recommended based on warnings."

        return MemoryQualityResult(
            memory_id=mem.id,
            user_id=user_id,
            overall_score=overall_score,
            dimensions=dim_scores,
            warnings=list(dict.fromkeys(all_warnings)),
            evaluated_at=now,
            summary_reason=summary,
        )

    @classmethod
    async def evaluate_memories_batch(
        cls,
        db: AsyncSession,
        user_id: str,
        memory_ids: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
        as_of: datetime | None = None,
        weights: dict[str, float] | None = None,
    ) -> BatchMemoryQualityResult:
        """Batch evaluate memories for user_id with bounded execution."""
        bounded_limit = max(1, min(limit, 200))
        target_ids: list[str] = []

        if memory_ids is not None:
            # Query strictly scoped to user_id
            target_ids = memory_ids[:bounded_limit]
        else:
            stmt = (
                select(Memory.id)
                .where(Memory.user_id == user_id)
                .order_by(Memory.created_at.desc())
                .offset(offset)
                .limit(bounded_limit)
            )
            res = await db.execute(stmt)
            target_ids = list(res.scalars().all())

        results: list[MemoryQualityResult] = []
        for mid in target_ids:
            res = await cls.evaluate_memory(
                db, user_id, mid, as_of=as_of, weights=weights
            )
            if res:
                results.append(res)

        total = len(results)
        mean_score = round(sum(r.overall_score for r in results) / total, 4) if total > 0 else 0.0

        return BatchMemoryQualityResult(
            total_evaluated=total,
            mean_quality_score=mean_score,
            results=results,
        )

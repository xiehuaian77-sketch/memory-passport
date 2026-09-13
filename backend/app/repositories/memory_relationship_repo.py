"""Repository layer for MemoryRelationship model.

All operations enforce strict user isolation and idempotency where appropriate.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select, delete as sql_delete, and_, or_, literal, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory_relationship import MemoryRelationship
from app.models.memory import Memory
from app.schemas.memory_relationship import RelationshipType

# ------------------------------------------------------------
# CREATE (idempotent)
# ------------------------------------------------------------
async def create_relationship(
    db: AsyncSession,
    user_id: str,
    source_memory_id: str,
    target_memory_id: str,
    relationship_type: RelationshipType,
    confidence: float | None = None,
) -> MemoryRelationship:
    """Create a relationship or return existing one.

    The function is idempotent: if a relationship with the same
    `(user_id, source_memory_id, target_memory_id, relationship_type)` already exists,
    it is returned without creating a duplicate.
    """
    # Check for existing relationship
    stmt = select(MemoryRelationship).where(
        MemoryRelationship.user_id == user_id,
        MemoryRelationship.source_memory_id == source_memory_id,
        MemoryRelationship.target_memory_id == target_memory_id,
        MemoryRelationship.relationship_type == relationship_type,
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    rel = MemoryRelationship(
        id=str(uuid.uuid4()),
        user_id=user_id,
        source_memory_id=source_memory_id,
        target_memory_id=target_memory_id,
        relationship_type=relationship_type,
        confidence=confidence,
    )
    db.add(rel)
    await db.flush()
    await db.refresh(rel)
    return rel

# ------------------------------------------------------------
# READ single relationship
# ------------------------------------------------------------
async def get_relationship(
    db: AsyncSession, user_id: str, relationship_id: str
) -> MemoryRelationship | None:
    stmt = select(MemoryRelationship).where(
        MemoryRelationship.id == relationship_id,
        MemoryRelationship.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

# ------------------------------------------------------------
# DELETE
# ------------------------------------------------------------
async def delete_relationship(
    db: AsyncSession, user_id: str, relationship_id: str
) -> bool:
    stmt = sql_delete(MemoryRelationship).where(
        MemoryRelationship.id == relationship_id,
        MemoryRelationship.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.rowcount > 0  # type: ignore[union-attr]

# ------------------------------------------------------------
# LIST relationships for a user (optional filters)
# ------------------------------------------------------------
async def list_by_user(
    db: AsyncSession,
    user_id: str,
    offset: int = 0,
    limit: int = 100,
) -> Sequence[MemoryRelationship]:
    stmt = (
        select(MemoryRelationship)
        .where(MemoryRelationship.user_id == user_id)
        .order_by(MemoryRelationship.created_at.desc())
        .offset(offset)
        .limit(min(limit, 200))
    )
    result = await db.execute(stmt)
    return result.scalars().all()

# ------------------------------------------------------------
# LIST relationships for a specific memory
# ------------------------------------------------------------
async def list_by_memory(
    db: AsyncSession,
    user_id: str,
    memory_id: str,
    offset: int = 0,
    limit: int = 100,
) -> Sequence[MemoryRelationship]:
    stmt = (
        select(MemoryRelationship)
        .where(
            MemoryRelationship.user_id == user_id,
            or_(
                MemoryRelationship.source_memory_id == memory_id,
                MemoryRelationship.target_memory_id == memory_id,
            ),
        )
        .order_by(MemoryRelationship.created_at.desc())
        .offset(offset)
        .limit(min(limit, 200))
    )
    result = await db.execute(stmt)
    return result.scalars().all()

# ------------------------------------------------------------
# ONE‑HOP related memories query
# ------------------------------------------------------------
async def list_related_memories(
    db: AsyncSession,
    user_id: str,
    memory_id: str,
    direction: str = "both",
    relationship_type: RelationshipType | None = None,
    confidence_min: float | None = None,
    temporal_mode: str = "current",
    reference_time: datetime | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """Return target/source memories that are directly related to the given `memory_id`.

    Strictly one-hop, joining `memory_relationships` with `memories`.
    Filters by direction ('outgoing', 'incoming', 'both'), relationship_type,
    confidence_min, temporal_mode ('current', 'historical', 'any'), and reference_time.
    Hard cap limit <= 200 is enforced. No N+1 queries.
    """
    safe_limit = max(1, min(limit, 200))
    ref_now = reference_time or datetime.now(timezone.utc)
    if ref_now.tzinfo is None:
        ref_now = ref_now.replace(tzinfo=timezone.utc)

    # 1. Temporal filter conditions on the related Memory
    mem_temporal_conditions = []
    if temporal_mode == "current":
        mem_temporal_conditions.extend([
            Memory.status == "active",
            Memory.superseded_by_memory_id.is_(None),
            or_(Memory.valid_until.is_(None), Memory.valid_until > ref_now),
            or_(Memory.valid_from.is_(None), Memory.valid_from <= ref_now),
        ])
    elif temporal_mode == "historical":
        mem_temporal_conditions.append(
            or_(
                Memory.status.in_(["superseded", "archived"]),
                Memory.superseded_by_memory_id.is_not(None),
                and_(Memory.valid_until.is_not(None), Memory.valid_until <= ref_now),
            )
        )
    # "any" applies no extra temporal restrictions

    # 2. Relationship filters
    rel_conditions = []
    if relationship_type is not None:
        rel_conditions.append(MemoryRelationship.relationship_type == relationship_type)
    if confidence_min is not None:
        rel_conditions.append(MemoryRelationship.confidence >= confidence_min)

    # 3. Outgoing query: memory_id is source, related memory is target
    q_out = select(
        Memory.id.label("mem_id"),
        Memory.user_id.label("mem_user_id"),
        Memory.content.label("mem_content"),
        Memory.memory_type.label("mem_memory_type"),
        Memory.status.label("mem_status"),
        Memory.importance.label("mem_importance"),
        Memory.confidence.label("mem_confidence"),
        Memory.valid_from.label("mem_valid_from"),
        Memory.valid_until.label("mem_valid_until"),
        Memory.superseded_by_memory_id.label("mem_superseded_by_memory_id"),
        MemoryRelationship.id.label("rel_id"),
        MemoryRelationship.relationship_type.label("rel_type"),
        MemoryRelationship.confidence.label("rel_confidence"),
        MemoryRelationship.created_at.label("rel_created_at"),
        literal("outgoing").label("direction"),
    ).join(
        MemoryRelationship,
        and_(
            MemoryRelationship.target_memory_id == Memory.id,
            MemoryRelationship.source_memory_id == memory_id,
            MemoryRelationship.user_id == user_id,
        ),
    ).where(
        Memory.user_id == user_id,
        *mem_temporal_conditions,
        *rel_conditions,
    )

    # 4. Incoming query: memory_id is target, related memory is source
    q_in = select(
        Memory.id.label("mem_id"),
        Memory.user_id.label("mem_user_id"),
        Memory.content.label("mem_content"),
        Memory.memory_type.label("mem_memory_type"),
        Memory.status.label("mem_status"),
        Memory.importance.label("mem_importance"),
        Memory.confidence.label("mem_confidence"),
        Memory.valid_from.label("mem_valid_from"),
        Memory.valid_until.label("mem_valid_until"),
        Memory.superseded_by_memory_id.label("mem_superseded_by_memory_id"),
        MemoryRelationship.id.label("rel_id"),
        MemoryRelationship.relationship_type.label("rel_type"),
        MemoryRelationship.confidence.label("rel_confidence"),
        MemoryRelationship.created_at.label("rel_created_at"),
        literal("incoming").label("direction"),
    ).join(
        MemoryRelationship,
        and_(
            MemoryRelationship.source_memory_id == Memory.id,
            MemoryRelationship.target_memory_id == memory_id,
            MemoryRelationship.user_id == user_id,
        ),
    ).where(
        Memory.user_id == user_id,
        *mem_temporal_conditions,
        *rel_conditions,
    )

    if direction == "outgoing":
        stmt = (
            q_out.order_by(
                MemoryRelationship.created_at.desc(),
                MemoryRelationship.id.desc(),
            )
            .offset(offset)
            .limit(safe_limit)
        )
    elif direction == "incoming":
        stmt = (
            q_in.order_by(
                MemoryRelationship.created_at.desc(),
                MemoryRelationship.id.desc(),
            )
            .offset(offset)
            .limit(safe_limit)
        )
    else:  # "both"
        subq = union_all(q_out, q_in).subquery()
        stmt = (
            select(subq)
            .order_by(subq.c.rel_created_at.desc(), subq.c.rel_id.desc())
            .offset(offset)
            .limit(safe_limit)
        )

    result = await db.execute(stmt)
    return [dict(row) for row in result.mappings().all()]


# ------------------------------------------------------------
# BATCH ONE‑HOP related memories query (for graph retrieval)
# ------------------------------------------------------------
async def list_batch_related_memories(
    db: AsyncSession,
    user_id: str,
    memory_ids: Sequence[str],
    temporal_mode: str = "current",
    reference_time: datetime | None = None,
    status: str | None = "active",
    limit: int = 50,
) -> list[dict]:
    """Return 1-hop related memories connected to any of the given seed `memory_ids`.

    Executes bounded, indexed batch queries (strictly 1-hop, no N+1).
    Enforces user isolation and temporal validity constraints.
    Returns list of dicts:
        {
            "memory": Memory,
            "seed_id": str,
            "rel_type": RelationshipType,
            "rel_confidence": float | None,
            "rel_id": str,
            "direction": "outgoing" | "incoming",
        }
    """
    valid_seed_ids = list({str(m) for m in memory_ids if m})
    if not valid_seed_ids:
        return []

    safe_limit = max(1, min(limit, 200))
    ref_now = reference_time or datetime.now(timezone.utc)
    if ref_now.tzinfo is None:
        ref_now = ref_now.replace(tzinfo=timezone.utc)

    # 1. Temporal filter conditions on the related Memory
    mem_temporal_conditions = []
    if temporal_mode == "current":
        mem_temporal_conditions.extend([
            Memory.status == "active",
            Memory.superseded_by_memory_id.is_(None),
            or_(Memory.valid_until.is_(None), Memory.valid_until > ref_now),
            or_(Memory.valid_from.is_(None), Memory.valid_from <= ref_now),
        ])
    elif temporal_mode == "historical":
        mem_temporal_conditions.append(
            or_(
                Memory.status.in_(["superseded", "archived"]),
                Memory.superseded_by_memory_id.is_not(None),
                and_(Memory.valid_until.is_not(None), Memory.valid_until <= ref_now),
            )
        )
    elif temporal_mode == "any":
        if status is not None:
            mem_temporal_conditions.append(Memory.status == status)

    # 2. Outgoing query (seed is source, neighbor is target)
    q_out = (
        select(
            Memory,
            MemoryRelationship.source_memory_id.label("seed_id"),
            MemoryRelationship.relationship_type.label("rel_type"),
            MemoryRelationship.confidence.label("rel_confidence"),
            MemoryRelationship.id.label("rel_id"),
            literal("outgoing").label("direction"),
        )
        .join(
            MemoryRelationship,
            and_(
                MemoryRelationship.target_memory_id == Memory.id,
                MemoryRelationship.source_memory_id.in_(valid_seed_ids),
                MemoryRelationship.user_id == user_id,
            ),
        )
        .where(
            Memory.user_id == user_id,
            *mem_temporal_conditions,
        )
        .order_by(MemoryRelationship.created_at.desc(), MemoryRelationship.id.desc())
        .limit(safe_limit)
    )

    # 3. Incoming query (seed is target, neighbor is source)
    q_in = (
        select(
            Memory,
            MemoryRelationship.target_memory_id.label("seed_id"),
            MemoryRelationship.relationship_type.label("rel_type"),
            MemoryRelationship.confidence.label("rel_confidence"),
            MemoryRelationship.id.label("rel_id"),
            literal("incoming").label("direction"),
        )
        .join(
            MemoryRelationship,
            and_(
                MemoryRelationship.source_memory_id == Memory.id,
                MemoryRelationship.target_memory_id.in_(valid_seed_ids),
                MemoryRelationship.user_id == user_id,
            ),
        )
        .where(
            Memory.user_id == user_id,
            *mem_temporal_conditions,
        )
        .order_by(MemoryRelationship.created_at.desc(), MemoryRelationship.id.desc())
        .limit(safe_limit)
    )

    res_out = await db.execute(q_out)
    res_in = await db.execute(q_in)

    records: list[dict] = []
    for row in res_out.all():
        records.append({
            "memory": row[0],
            "seed_id": str(row[1]),
            "rel_type": row[2],
            "rel_confidence": row[3],
            "rel_id": str(row[4]),
            "direction": str(row[5]),
        })
    for row in res_in.all():
        records.append({
            "memory": row[0],
            "seed_id": str(row[1]),
            "rel_type": row[2],
            "rel_confidence": row[3],
            "rel_id": str(row[4]),
            "direction": str(row[5]),
        })

    return records

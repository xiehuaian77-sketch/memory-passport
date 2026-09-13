"""Repository layer for MemoryRelationship model.

All operations enforce strict user isolation and idempotency where appropriate.
"""

from __future__ import annotations

import uuid
from typing import Sequence, List

from sqlalchemy import select, delete as sql_delete, and_, or_
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
    limit: int = 20,
    offset: int = 0,
) -> List[Memory]:
    """Return target memories that are related to the given `memory_id`.

    Joins `memory_relationships` with `memories` and returns Memory objects.
    Pagination is applied after the join.
    """
    stmt = (
        select(Memory)
        .join(
            MemoryRelationship,
            and_(
                MemoryRelationship.target_memory_id == Memory.id,
                MemoryRelationship.source_memory_id == memory_id,
            ),
        )
        .where(MemoryRelationship.user_id == user_id, Memory.user_id == user_id)
        .order_by(Memory.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

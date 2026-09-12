# backend/app/repositories/memory_repo.py
"""
Repository layer for Memory model.
All DB operations enforce user-level isolation using the supplied ``user_id``.
"""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.schemas.memory import MemoryCreate, MemoryUpdate

# ------------------------------------------------------------
# CREATE
# ------------------------------------------------------------
async def create(db: AsyncSession, user_id: str, data: MemoryCreate) -> Memory:
    """Create a new Memory row.

    ``category`` from legacy payload is accepted as an alias for ``memory_type``.
    """
    mem_type = data.memory_type or getattr(data, "category", None) or "preference"
    mem = Memory(
        user_id=user_id,
        memory_type=mem_type,
        key=data.key,
        content=data.content,
        source=data.source,
        confidence=data.confidence,
        importance=data.importance,
        tags=data.tags,
    )
    db.add(mem)
    await db.flush()
    await db.refresh(mem)
    return mem

# ------------------------------------------------------------
# READ (single)
# ------------------------------------------------------------
async def get_by_id(db: AsyncSession, memory_id: str, user_id: str) -> Memory | None:
    stmt = select(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

# ------------------------------------------------------------
# LIST
# ------------------------------------------------------------
async def list_by_user(
    db: AsyncSession,
    user_id: str,
    offset: int = 0,
    limit: int = 100,
) -> Sequence[Memory]:
    stmt = (
        select(Memory)
        .where(Memory.user_id == user_id)
        .order_by(Memory.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

# ------------------------------------------------------------
# UPDATE
# ------------------------------------------------------------
async def update(
    db: AsyncSession, memory: Memory, data: MemoryUpdate
) -> Memory:
    # Apply only provided fields
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(memory, field, value)
    # Handle legacy category field if present
    if hasattr(data, "category") and data.category is not None:
        memory.memory_type = data.category
    await db.flush()
    await db.refresh(memory)
    return memory

# ------------------------------------------------------------
# DELETE
# ------------------------------------------------------------
async def delete(db: AsyncSession, memory_id: str, user_id: str) -> bool:
    stmt = delete(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
    result = await db.execute(stmt)
    return result.rowcount > 0  # type: ignore[union-attr]

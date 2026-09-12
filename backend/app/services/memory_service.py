"""Memory service — business logic for memory CRUD, embedding, and search."""

from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.schemas.memory import MemoryCreate, MemoryUpdate
from app.services.embedding_service import (
    embedding_to_json,
    generate_embedding,
    json_to_embedding,
    rank_by_similarity,
)

logger = logging.getLogger(__name__)


async def create_memory(
    db: AsyncSession,
    user_id: str,
    data: MemoryCreate,
    *,
    auto_embed: bool = True,
) -> Memory:
    """Create a new memory, optionally generating its embedding."""
    embedding_json = None
    if auto_embed:
        try:
            vec = await generate_embedding(f"{data.key}: {data.content}")
            embedding_json = embedding_to_json(vec)
        except Exception as e:
            logger.warning("Embedding generation failed, saving without: %s", e)

    # Prefer explicit category field; fallback to memory_type or default
    mem_type = data.category if getattr(data, "category", None) is not None else (data.memory_type or "preference")
    mem = Memory(
        user_id=user_id,
        memory_type=mem_type,
        key=data.key,
        content=data.content,
        embedding_json=embedding_json,
        source=data.source,
        confidence=data.confidence,
        importance=data.importance,
        is_shared=data.is_shared,
        tags=data.tags,
    )
    db.add(mem)
    await db.flush()
    await db.refresh(mem)
    return mem


async def get_memories(
    db: AsyncSession,
    user_id: str,
    category: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> Sequence[Memory]:
    """Get memories for a user, optionally filtered by category."""
    stmt = select(Memory).where(Memory.user_id == user_id)
    if category:
        stmt = stmt.where(Memory.memory_type == category)
    stmt = stmt.order_by(Memory.updated_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_memory_by_id(
    db: AsyncSession, memory_id: str, user_id: str
) -> Memory | None:
    """Get a single memory by ID, scoped to user."""
    stmt = select(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_memory(
    db: AsyncSession, memory: Memory, data: MemoryUpdate
) -> Memory:
    """Update memory fields and re-embed if content changed."""
    # Track if key/content changed for re-embedding
    changed = False
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "category":
            # Update canonical column memory_type
            memory.memory_type = value
            continue
        setattr(memory, field, value)
        if field in ("key", "content"):
            changed = True
    if changed:
        try:
            vec = await generate_embedding(f"{memory.key}: {memory.content}")
            memory.embedding_json = embedding_to_json(vec)
        except Exception as e:
            logger.warning("Re-embedding failed: %s", e)
    await db.flush()
    await db.refresh(memory)
    return memory


async def delete_memory(db: AsyncSession, memory_id: str, user_id: str) -> bool:
    """Delete a memory by ID."""
    stmt = delete(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
    result = await db.execute(stmt)
    return result.rowcount > 0  # type: ignore[union-attr]


async def search_memories(
    db: AsyncSession,
    user_id: str,
    query: str,
    top_k: int = 5,
    category: str | None = None,
) -> list[tuple[Memory, float]]:
    """Semantic search over user's memories using cosine similarity."""
    try:
        # Generate query embedding
        query_vec = await generate_embedding(query)
        query_np = __import__("numpy").array(query_vec, dtype="float32")

        # Load all user memories with embeddings
        stmt = select(Memory).where(
            Memory.user_id == user_id,
            Memory.embedding_json.isnot(None),
        )
        if category:
            stmt = stmt.where(Memory.memory_type == category)
        result = await db.execute(stmt)
        memories = result.scalars().all()

        # Build candidates
        candidates = []
        mem_map: dict[str, Memory] = {}
        for m in memories:
            vec = json_to_embedding(m.embedding_json)
            if vec is not None:
                candidates.append((m.id, vec))
                mem_map[m.id] = m

        if candidates:
            ranked = rank_by_similarity(query_np, candidates, top_k=top_k)
            return [(mem_map[mid], score) for mid, score in ranked if mid in mem_map]
    except Exception as e:
        logger.info("Vector search unavailable (%s), falling back to keyword search", e)

    # Fallback: keyword/substring match over memories
    stmt = select(Memory).where(Memory.user_id == user_id)
    if category:
        stmt = stmt.where(Memory.memory_type == category)
    result = await db.execute(stmt)
    all_memories = result.scalars().all()

    q_lower = query.lower().strip()
    q_words = set(q_lower.split()) if q_lower else set()
    scored: list[tuple[Memory, float]] = []

    for m in all_memories:
        text = f"{m.key} {m.content} {m.tags or ''}".lower()
        if not q_words:
            scored.append((m, 1.0))
        else:
            matches = sum(1 for w in q_words if w in text)
            if matches > 0:
                scored.append((m, round(matches / len(q_words), 4)))
            elif q_lower in text:
                scored.append((m, 0.8))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


async def get_all_memories_as_dicts(
    db: AsyncSession,
    user_id: str,
    shared_only: bool = False,
) -> list[dict]:
    """Get all memories as plain dicts (for AI prompt injection)."""
    stmt = select(Memory).where(Memory.user_id == user_id)
    if shared_only:
        stmt = stmt.where(Memory.is_shared.is_(True))
    result = await db.execute(stmt)
    memories = result.scalars().all()
    return [
        {
            "category": m.category,
            "key": m.key,
            "content": m.content,
            "confidence": m.confidence,
            "source": m.source,
        }
        for m in memories
    ]


async def delete_all_user_memories(db: AsyncSession, user_id: str) -> int:
    """Delete all memories for a user. Returns count deleted."""
    stmt = delete(Memory).where(Memory.user_id == user_id)
    result = await db.execute(stmt)
    return result.rowcount  # type: ignore[union-attr]

# backend/app/repositories/memory_repo.py
"""
Repository layer for Memory model.
All DB operations enforce user-level isolation using the supplied ``user_id``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.models.memory import Memory
from app.schemas.memory import MemoryCreate, MemoryUpdate
from sqlalchemy import delete as sql_delete
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession


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
        status=getattr(data, "status", None) or "active",
        version=1,
        source_conversation_id=getattr(data, "source_conversation_id", None),
        source_message_id=getattr(data, "source_message_id", None),
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
    status: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> Sequence[Memory]:
    stmt = select(Memory).where(Memory.user_id == user_id)
    if status is not None:
        stmt = stmt.where(Memory.status == status)
    stmt = stmt.order_by(Memory.updated_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


# ------------------------------------------------------------
# BACKFILL HELPERS (Phase 2.3F)
# ------------------------------------------------------------
async def count_unembedded(db: AsyncSession, user_id: str | None = None) -> int:
    """Count memories where embedding is NULL, optionally filtered by user_id."""
    from sqlalchemy import func

    stmt = select(func.count(Memory.id)).where(Memory.embedding.is_(None))
    if user_id:
        stmt = stmt.where(Memory.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar() or 0


async def get_unembedded_batch(
    db: AsyncSession, user_id: str | None = None, limit: int = 50
) -> Sequence[Memory]:
    """Fetch a batch of memories where embedding is NULL, ordered by created_at."""
    stmt = (
        select(Memory)
        .where(Memory.embedding.is_(None))
        .order_by(Memory.created_at.asc())
        .limit(limit)
    )
    if user_id:
        stmt = stmt.where(Memory.user_id == user_id)
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
    stmt = sql_delete(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
    result = await db.execute(stmt)
    return result.rowcount > 0  # type: ignore[union-attr]

# ------------------------------------------------------------
# SEMANTIC SEARCH (pgvector cosine similarity)
# ------------------------------------------------------------
async def semantic_search(
    db: AsyncSession,
    user_id: str,
    query_vector: list[float],
    limit: int = 10,
    status: str | None = "active",
) -> list[tuple[Memory, float]]:
    """Search user's memories using cosine distance on pgvector embedding.

    Returns list of (Memory, similarity) tuples ordered by similarity DESC.
    similarity = 1.0 - cosine_distance.
    Enforces user_id isolation and status filtering in the database query.
    """
    bind = db.get_bind()
    dialect = bind.dialect.name if bind else "postgresql"

    if dialect == "postgresql":
        dist_expr = Memory.embedding.cosine_distance(query_vector)
        stmt = select(Memory, dist_expr.label("distance")).where(
            Memory.user_id == user_id,
            Memory.embedding.isnot(None),
        )
        if status is not None:
            stmt = stmt.where(Memory.status == status)
        stmt = stmt.order_by(dist_expr.asc()).limit(limit)
        result = await db.execute(stmt)
        rows = result.all()
        return [
            (row[0], max(-1.0, min(1.0, round(1.0 - float(row[1]), 4))))
            for row in rows
        ]
    else:
        # SQLite compatibility for testing
        stmt = select(Memory).where(
            Memory.user_id == user_id,
            Memory.embedding.isnot(None),
        )
        if status is not None:
            stmt = stmt.where(Memory.status == status)
        result = await db.execute(stmt)
        memories = result.scalars().all()
        scored: list[tuple[Memory, float]] = []
        for m in memories:
            vec = m.embedding
            if vec is None:
                continue
            if isinstance(vec, str):
                vec = [float(x.strip()) for x in vec.strip("[]").split(",") if x.strip()]
            dot = sum(x * y for x, y in zip(query_vector, vec))
            norm_q = sum(x * x for x in query_vector) ** 0.5
            norm_v = sum(x * x for x in vec) ** 0.5
            if norm_q == 0.0 or norm_v == 0.0:
                sim = 0.0
            else:
                sim = max(-1.0, min(1.0, round(dot / (norm_q * norm_v), 4)))
            scored.append((m, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]


# ------------------------------------------------------------
# KEYWORD SEARCH (PostgreSQL FTS + exact/partial term matching)
# ------------------------------------------------------------
async def keyword_search(
    db: AsyncSession,
    user_id: str,
    query: str,
    limit: int = 10,
    status: str | None = "active",
) -> list[tuple[Memory, float]]:
    """Search user's memories using PostgreSQL FTS and keyword matching on content.

    Returns list of (Memory, keyword_score) tuples ordered by keyword_score DESC.
    keyword_score is normalized to [0.0, 1.0].
    Enforces user_id isolation and status filtering in the database query.
    """
    bind = db.get_bind()
    dialect = bind.dialect.name if bind else "postgresql"
    q_clean = query.strip()
    if not q_clean:
        return []

    tokens = [w for w in re.findall(r"[\w]+", q_clean) if w]

    if dialect == "postgresql":
        # Parameterized PostgreSQL FTS + phrase/token ILIKE on Memory.content
        # Strict user isolation: WHERE user_id = :user_id
        fts_match_clause = text(
            "to_tsvector('simple', memories.content) @@ websearch_to_tsquery('simple', :query_fts)"
        )
        conditions = [fts_match_clause]
        params: dict = {
            "query_fts": q_clean,
            "user_id": user_id,
            "full_query_pat": f"%{q_clean}%",
        }

        # Add whole phrase ILIKE
        conditions.append(text("memories.content ILIKE :full_query_pat"))

        # Add token ILIKE clauses if tokens present
        for idx, t in enumerate(tokens[:5]):
            param_name = f"t_pat_{idx}"
            params[param_name] = f"%{t}%"
            conditions.append(text(f"memories.content ILIKE :{param_name}"))

        stmt = select(Memory).where(
            Memory.user_id == user_id,
            or_(*conditions),
        )
        if status is not None:
            stmt = stmt.where(Memory.status == status)
        stmt = stmt.params(**params)
        result = await db.execute(stmt)
        memories = result.scalars().all()
    else:
        # SQLite fallback for unit testing
        conditions = [Memory.content.ilike(f"%{q_clean}%")]
        for t in tokens[:5]:
            conditions.append(Memory.content.ilike(f"%{t}%"))

        stmt = select(Memory).where(
            Memory.user_id == user_id,
            or_(*conditions),
        )
        if status is not None:
            stmt = stmt.where(Memory.status == status)
        result = await db.execute(stmt)
        memories = result.scalars().all()

    # Compute normalized keyword score in [0.0, 1.0]
    scored: list[tuple[Memory, float]] = []
    q_lower = q_clean.lower()

    for mem in memories:
        c_lower = mem.content.lower()
        if q_lower in c_lower:
            score = 1.0
        elif tokens:
            matched_count = sum(1 for t in tokens if t.lower() in c_lower)
            score = matched_count / len(tokens)
        else:
            score = 0.5

        if score > 0.0:
            scored.append((mem, max(0.0, min(1.0, round(score, 4)))))

    # Stable deterministic ordering: score DESC, created_at DESC, id DESC
    scored.sort(
        key=lambda x: (
            x[1],
            x[0].created_at.timestamp() if x[0].created_at else 0.0,
            x[0].id,
        ),
        reverse=True,
    )
    return scored[:limit]

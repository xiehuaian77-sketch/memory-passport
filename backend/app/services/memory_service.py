"""Memory service — business logic for memory CRUD, embedding, and search."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

if TYPE_CHECKING:
    from app.schemas.memory import ConflictItem, MemoryRetrievalRequest
    from app.services.context_assembler import AssembledContext

from app.models.governance import AuditAction, AuditActorType
from app.models.memory import Memory
from app.providers.embedding_provider import (
    EmbeddingError,
    EmbeddingProvider,
    get_embedding_provider,
)
from app.schemas.memory import MemoryCreate, MemoryUpdate
from app.services.embedding_service import (
    embedding_to_json,
    generate_embedding,
    json_to_embedding,
    rank_by_similarity,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def create_memory(
    db: AsyncSession,
    user_id: str,
    data: MemoryCreate,
    *,
    auto_embed: bool = True,
    embedding_provider: EmbeddingProvider | None = None,
) -> Memory:
    """Create a new memory, optionally generating its embedding via EmbeddingProvider."""
    # Prefer explicit category field; fallback to memory_type or default
    mem_type = data.category if getattr(data, "category", None) is not None else (data.memory_type or "preference")
    mem = Memory(
        user_id=user_id,
        memory_type=mem_type,
        key=data.key,
        content=data.content,
        embedding=None,
        embedding_json=None,
        source=data.source,
        confidence=data.confidence,
        importance=data.importance,
        is_shared=data.is_shared,
        tags=data.tags,
        status=getattr(data, "status", None) or "active",
        version=1,
        source_conversation_id=getattr(data, "source_conversation_id", None),
        source_message_id=getattr(data, "source_message_id", None),
        valid_from=getattr(data, "valid_from", None),
        valid_until=getattr(data, "valid_until", None),
        superseded_by_memory_id=getattr(data, "superseded_by_memory_id", None),
    )
    db.add(mem)
    # First persist Memory to guarantee no data loss if embedding generation fails
    await db.flush()

    if auto_embed:
        provider = embedding_provider or get_embedding_provider()
        try:
            # Canonical embedding input: memory.content ONLY
            vec = await provider.embed(data.content)
            mem.embedding = vec
            mem.embedding_json = embedding_to_json(vec)
            await db.flush()
        except (EmbeddingError, Exception) as exc:
            # Catch embedding errors safely without leaking secrets or failing memory creation
            logger.warning(
                "Embedding generation failed for memory %s, preserving memory with embedding=None: %s",
                mem.id,
                exc.__class__.__name__,
            )
            mem.embedding = None
            mem.embedding_json = None

    await db.refresh(mem)

    # Log audit event (CONFIRM if from conversation extraction, else CREATE)
    from app.services import governance_service
    evt_action = (
        AuditAction.CONFIRM
        if (getattr(data, "source", None) == "ai_extracted" or mem.source_conversation_id)
        else AuditAction.CREATE
    )
    await governance_service.log_event(
        db=db,
        user_id=user_id,
        action=evt_action,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        memory_id=mem.id,
        from_version=None,
        to_version=1,
        metadata={"key": mem.key, "memory_type": mem.memory_type, "source": mem.source},
    )

    return mem


async def get_memories(
    db: AsyncSession,
    user_id: str,
    category: str | None = None,
    memory_type: str | None = None,
    source: str | None = None,
    status: str | None = "active",
    offset: int = 0,
    limit: int = 100,
) -> Sequence[Memory]:
    """Get memories for a user, optionally filtered by category/memory_type, source, and status."""
    stmt = select(Memory).where(Memory.user_id == user_id)
    target_type = memory_type or category
    if target_type:
        stmt = stmt.where(Memory.memory_type == target_type)
    if source:
        stmt = stmt.where(Memory.source == source)
    if status is not None and status.lower() != "all":
        stmt = stmt.where(Memory.status == status)
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
    db: AsyncSession,
    memory: Memory,
    data: MemoryUpdate,
    *,
    embedding_provider: EmbeddingProvider | None = None,
) -> Memory:
    """Update memory fields and re-embed if content changed. Increments memory version."""
    # Check if content actually changed
    content_changed = (
        data.content is not None and data.content != memory.content
    )
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "category":
            # Update canonical column memory_type
            memory.memory_type = value
            continue
        setattr(memory, field, value)

    # Monotonically increment version on update
    old_version = memory.version or 1
    memory.version = old_version + 1

    if content_changed:
        provider = embedding_provider or get_embedding_provider()
        try:
            # Canonical embedding input: memory.content ONLY
            vec = await provider.embed(memory.content)
            memory.embedding = vec
            memory.embedding_json = embedding_to_json(vec)
        except EmbeddingError as exc:
            logger.warning(
                "Re-embedding failed for memory %s: %s",
                memory.id,
                exc.__class__.__name__,
            )
            memory.embedding = None
            memory.embedding_json = None

    await db.flush()
    await db.refresh(memory)

    # Log audit event for UPDATE
    from app.services import governance_service
    await governance_service.log_event(
        db=db,
        user_id=memory.user_id,
        action=AuditAction.UPDATE,
        actor_type=AuditActorType.USER,
        actor_id=memory.user_id,
        memory_id=memory.id,
        from_version=old_version,
        to_version=memory.version,
        metadata={"key": memory.key, "updated_fields": list(data.model_dump(exclude_unset=True).keys())},
    )

    return memory


async def delete_memory(db: AsyncSession, memory_id: str, user_id: str) -> bool:
    """Delete a memory by ID after recording audit log."""
    mem = await get_memory_by_id(db, memory_id=memory_id, user_id=user_id)
    if not mem:
        return False

    # Log DELETE audit event before hard delete so memory details are captured
    from app.services import governance_service
    await governance_service.log_event(
        db=db,
        user_id=user_id,
        action=AuditAction.DELETE,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        memory_id=mem.id,
        from_version=mem.version,
        to_version=mem.version,
        metadata={"deleted_memory_id": mem.id, "deleted_key": mem.key},
    )

    stmt = delete(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
    result = await db.execute(stmt)
    return result.rowcount > 0  # type: ignore[union-attr]


async def archive_memory(
    db: AsyncSession, memory_id: str, user_id: str
) -> Memory | None:
    """Archive a memory by setting status='archived'. Enforces user isolation."""
    mem = await get_memory_by_id(db, memory_id=memory_id, user_id=user_id)
    if not mem:
        return None
    mem.status = "archived"
    await db.flush()
    await db.refresh(mem)

    from app.services import governance_service
    await governance_service.log_event(
        db=db,
        user_id=user_id,
        action=AuditAction.ARCHIVE,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        memory_id=mem.id,
        from_version=mem.version,
        to_version=mem.version,
        metadata={"key": mem.key, "status": "archived"},
    )

    return mem


async def restore_memory(
    db: AsyncSession, memory_id: str, user_id: str
) -> Memory | None:
    """Restore an archived memory by setting status='active'. Enforces user isolation."""
    mem = await get_memory_by_id(db, memory_id=memory_id, user_id=user_id)
    if not mem:
        return None
    mem.status = "active"
    await db.flush()
    await db.refresh(mem)

    from app.services import governance_service
    await governance_service.log_event(
        db=db,
        user_id=user_id,
        action=AuditAction.RESTORE,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        memory_id=mem.id,
        from_version=mem.version,
        to_version=mem.version,
        metadata={"key": mem.key, "status": "active"},
    )

    return mem


async def supersede_memory(
    db: AsyncSession,
    old_memory_id: str,
    replacement_memory_id: str,
    user_id: str,
    valid_until: datetime | None = None,
) -> Memory:
    """Supersede an old memory with a replacement memory in an atomic transaction.

    Validates:
    - old_memory_id != replacement_memory_id (HTTP 400)
    - Both memories exist and belong to user_id (HTTP 404)
    - old_memory must not already be superseded (HTTP 409)
    - replacement_memory must not be superseded (HTTP 400)
    - valid_until must not be earlier than old_memory.valid_from (HTTP 400)
    """
    if old_memory_id == replacement_memory_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A memory cannot supersede itself",
        )

    old_mem = await get_memory_by_id(db, memory_id=old_memory_id, user_id=user_id)
    if not old_mem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Old memory not found",
        )

    new_mem = await get_memory_by_id(db, memory_id=replacement_memory_id, user_id=user_id)
    if not new_mem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Replacement memory not found",
        )

    if old_mem.status == "superseded":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Memory is already superseded",
        )

    if new_mem.status == "superseded":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Replacement memory is already superseded",
        )

    now_utc = datetime.now(timezone.utc)
    effective_time = valid_until or new_mem.valid_from or now_utc
    if effective_time.tzinfo is None:
        effective_time = effective_time.replace(tzinfo=timezone.utc)

    if old_mem.valid_from is not None:
        old_v_from = old_mem.valid_from
        if old_v_from.tzinfo is None:
            old_v_from = old_v_from.replace(tzinfo=timezone.utc)
        if effective_time < old_v_from:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="valid_until cannot be earlier than valid_from",
            )

    old_mem.status = "superseded"
    old_mem.superseded_by_memory_id = new_mem.id
    old_mem.valid_until = effective_time

    if new_mem.valid_from is None:
        new_mem.valid_from = effective_time

    await db.flush()
    await db.refresh(old_mem)
    await db.refresh(new_mem)

    from app.services import governance_service
    await governance_service.log_event(
        db=db,
        user_id=user_id,
        action=AuditAction.SUPERSEDE,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        memory_id=old_mem.id,
        from_version=old_mem.version,
        to_version=old_mem.version,
        metadata={
            "old_memory_id": old_mem.id,
            "replacement_memory_id": new_mem.id,
            "superseded_at": effective_time.isoformat(),
        },
    )

    return old_mem


async def detect_conflicts(
    db: AsyncSession,
    user_id: str,
    key: str,
    content: str,
    memory_type: str = "preference",
    *,
    candidate_valid_from: datetime | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    llm_enabled: bool = True,
) -> list[ConflictItem]:
    """Detect conflicts between candidate memory and active memories using 3-tier cascade. Strictly read-only."""
    from app.services import conflict_service

    return await conflict_service.evaluate_conflicts(
        db=db,
        user_id=user_id,
        key=key,
        content=content,
        memory_type=memory_type,
        candidate_valid_from=candidate_valid_from,
        embedding_provider=embedding_provider,
        llm_enabled=llm_enabled,
    )


async def semantic_search(
    db: AsyncSession,
    user_id: str,
    query: str,
    limit: int = 10,
    status: str | None = "active",
    *,
    embedding_provider: EmbeddingProvider | None = None,
) -> list[tuple[Memory, float]]:
    """Execute pure semantic search over user's memories using pgvector cosine similarity."""
    provider = embedding_provider or get_embedding_provider()
    query_vec = await provider.embed(query)
    from app.repositories import memory_repo

    return await memory_repo.semantic_search(
        db, user_id=user_id, query_vector=query_vec, limit=limit, status=status
    )


DEFAULT_SEMANTIC_WEIGHT = 0.7
DEFAULT_KEYWORD_WEIGHT = 0.3


async def keyword_search(
    db: AsyncSession,
    user_id: str,
    query: str,
    limit: int = 10,
    status: str | None = "active",
) -> list[tuple[Memory, float]]:
    """Execute keyword search over user's memories using PostgreSQL FTS / content matching."""
    from app.repositories import memory_repo

    return await memory_repo.keyword_search(
        db, user_id=user_id, query=query, limit=limit, status=status
    )


class HybridSearchResult:
    """Wrapper holding a Memory and its similarity, keyword, and hybrid fusion scores."""

    def __init__(
        self,
        memory: Memory,
        similarity: float | None,
        keyword_score: float | None,
        hybrid_score: float,
    ):
        self.memory = memory
        self.similarity = similarity
        self.keyword_score = keyword_score
        self.hybrid_score = hybrid_score


async def hybrid_search(
    db: AsyncSession,
    user_id: str,
    query: str,
    limit: int = 10,
    status: str | None = "active",
    *,
    semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT,
    keyword_weight: float = DEFAULT_KEYWORD_WEIGHT,
    embedding_provider: EmbeddingProvider | None = None,
) -> list[HybridSearchResult]:
    """Execute hybrid search combining semantic search and keyword FTS search.

    Score normalization and fusion:
      semantic_score = max(0.0, min(1.0, similarity)) if similarity is not None else 0.0
      keyword_score = max(0.0, min(1.0, kw_score)) if kw_score is not None else 0.0
      hybrid_score = round(semantic_weight * semantic_score + keyword_weight * keyword_score, 4)

    Deterministic ordering:
      ORDER BY hybrid_score DESC, created_at DESC, id DESC
    """
    from app.repositories import memory_repo

    # Clamp weights
    total_weight = semantic_weight + keyword_weight
    if total_weight <= 0:
        semantic_weight = DEFAULT_SEMANTIC_WEIGHT
        keyword_weight = DEFAULT_KEYWORD_WEIGHT
        total_weight = 1.0
    w_sem = semantic_weight / total_weight
    w_kw = keyword_weight / total_weight

    # 1. Fetch semantic candidates
    fetch_limit = max(limit * 2, 20)
    sem_map: dict[str, tuple[Memory, float]] = {}
    try:
        provider = embedding_provider or get_embedding_provider()
        query_vec = await provider.embed(query)
        sem_results = await memory_repo.semantic_search(
            db, user_id=user_id, query_vector=query_vec, limit=fetch_limit, status=status
        )
        for mem, sim in sem_results:
            sem_map[mem.id] = (mem, sim)
    except EmbeddingError as exc:
        logger.warning(
            "Semantic search branch unavailable (%s), continuing with keyword branch only",
            exc.__class__.__name__,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Semantic search branch encountered error (%s), continuing with keyword branch only",
            exc,
        )

    # 2. Fetch keyword candidates
    kw_results = await memory_repo.keyword_search(
        db, user_id=user_id, query=query, limit=fetch_limit, status=status
    )
    kw_map: dict[str, tuple[Memory, float]] = {mem.id: (mem, score) for mem, score in kw_results}

    # 3. Fuse candidates
    all_memory_ids = list(dict.fromkeys(list(sem_map.keys()) + list(kw_map.keys())))
    if not all_memory_ids:
        return []

    fused_results: list[HybridSearchResult] = []
    for mid in all_memory_ids:
        mem = sem_map[mid][0] if mid in sem_map else kw_map[mid][0]

        # Normalized semantic score
        sim = sem_map[mid][1] if mid in sem_map else None
        sem_score = max(0.0, min(1.0, sim)) if sim is not None else 0.0

        # Normalized keyword score
        kw_sc = kw_map[mid][1] if mid in kw_map else None
        kw_score = max(0.0, min(1.0, kw_sc)) if kw_sc is not None else 0.0

        # Score fusion
        hybrid_sc = round(w_sem * sem_score + w_kw * kw_score, 4)

        if hybrid_sc > 0.0:
            fused_results.append(
                HybridSearchResult(
                    memory=mem,
                    similarity=sim,
                    keyword_score=kw_sc,
                    hybrid_score=hybrid_sc,
                )
            )

    # 4. Deterministic stable tie-breaking: hybrid_score DESC, created_at DESC, id DESC
    fused_results.sort(
        key=lambda x: (
            x.hybrid_score,
            x.memory.created_at.timestamp() if x.memory.created_at else 0.0,
            x.memory.id,
        ),
        reverse=True,
    )
    return fused_results[:limit]


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
    except Exception as e:  # noqa: BLE001
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


async def retrieve_context(
    db: AsyncSession,
    user_id: str,
    request: MemoryRetrievalRequest,
    *,
    embedding_provider: EmbeddingProvider | None = None,
) -> AssembledContext:
    """End-to-end memory retrieval pipeline (Phase 2.5C).

    Pipeline:
    1. Hybrid Search (fetch candidates bounded by top_k * 3, user-isolated)
    2. Retrieval Policy (filtering, recency decay, re-ranking, top-k slice)
    3. Context Assembly (deduplication by ID, content truncation, budget enforcement)
    """
    from app.services.context_assembler import ContextAssembler, ContextAssemblyConfig
    from app.services.retrieval_policy import MemoryRetrievalPolicy, RetrievalPolicyConfig

    fetch_limit = max(getattr(request, "top_k", 10) * 3, 30)
    status_filter = getattr(request, "status", "active")
    temporal_mode = getattr(request, "temporal_mode", "current")
    reference_time = getattr(request, "reference_time", None)

    # If temporal_mode is historical or any, broaden candidate search beyond active
    search_status = status_filter
    if temporal_mode in ("historical", "any") and (status_filter == "active"):
        search_status = None

    search_results = await hybrid_search(
        db,
        user_id=user_id,
        query=request.query,
        limit=fetch_limit,
        status=search_status,
        embedding_provider=embedding_provider,
    )

    policy_config = RetrievalPolicyConfig(
        top_k=getattr(request, "top_k", 10),
        min_relevance=getattr(request, "min_relevance", 0.30),
        min_importance=getattr(request, "min_importance", 0.0),
        min_confidence=getattr(request, "min_confidence", 0.0),
        memory_types=getattr(request, "memory_types", None),
        recency_half_life_days=getattr(request, "recency_half_life_days", 30.0),
        status=status_filter,
        temporal_mode=temporal_mode,
        reference_time=reference_time,
    )
    policy = MemoryRetrievalPolicy(policy_config)
    scored_memories = policy.apply(search_results)

    assembly_config = ContextAssemblyConfig(
        max_memories=getattr(request, "max_memories", 10),
        max_content_chars=getattr(request, "max_content_chars", 500),
        max_context_chars=getattr(request, "max_context_chars", 4000),
    )
    assembler = ContextAssembler(assembly_config)
    return assembler.assemble(scored_memories)

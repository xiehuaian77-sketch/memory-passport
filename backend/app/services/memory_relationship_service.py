'''MemoryRelationship Service – business logic for CRUD of memory relationships.

The service operates on an explicit ``current_user_id`` that is supplied by the
router/auth dependency chain.  It never inspects request objects or JWTs itself,
ensuring we honour the existing authentication architecture.

Responsibilities:
* Validate that ``source_memory_id`` and ``target_memory_id`` both belong to the
  ``current_user_id`` (user isolation).
* Disallow self‑relationships (source == target) – this is a 400‑level
  validation error.
* Enforce that the supplied ``relationship_type`` is one of the supported
  enum values (UPDATES, SUPERSEDES, CONTRADICTS, RELEVANT_TO).
* Delegate persistence to the pure‑data ``memory_relationship_repo`` which
  implements idempotent creation and other DB‑level operations.
* Raise ``HTTPException`` with the project's standard 404/400 semantics for
  cross‑user or validation failures so that callers receive the same error
  style as other services.
'''

from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.models.memory_relationship import MemoryRelationship
from app.repositories.memory_relationship_repo import (
    create_relationship as repo_create_relationship,
    get_relationship as repo_get_relationship,
    delete_relationship as repo_delete_relationship,
    list_by_user as repo_list_by_user,
    list_by_memory as repo_list_by_memory,
    list_related_memories as repo_list_related_memories,
)
from app.schemas.memory_relationship import (
    RelatedMemoryOut,
    RelationshipType,
)
from app.services.memory_service import get_memory_by_id

# ---------------------------------------------------------------------------
# CREATE (idempotent)
# ---------------------------------------------------------------------------
async def create_relationship(
    db,
    current_user_id: str,
    source_memory_id: str,
    target_memory_id: str,
    relationship_type: RelationshipType,
    confidence: float | None = None,
) -> MemoryRelationship:
    """Create a relationship between two memories owned by ``current_user_id``.

    The function is idempotent – if an identical relationship already exists the
    existing ORM object is returned.

    Validation steps:
    1. ``relationship_type`` must be one of UPDATES, SUPERSEDES, CONTRADICTS, RELEVANT_TO.
    2. ``confidence`` if provided must be in [0.0, 1.0].
    3. ``source_memory_id`` must differ from ``target_memory_id`` (self‑relation).
    4. Both memories must exist and belong to ``current_user_id``; otherwise a
       404 is raised to avoid leaking existence information.
    """

    # 1. Relationship type validation
    allowed_types = {
        RelationshipType.UPDATES,
        RelationshipType.SUPERSEDES,
        RelationshipType.CONTRADICTS,
        RelationshipType.RELEVANT_TO,
    }
    allowed_values = {t.value for t in allowed_types}
    raw_type = relationship_type.value if isinstance(relationship_type, RelationshipType) else str(relationship_type)
    if raw_type not in allowed_values:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported relationship_type: '{relationship_type}'. Allowed types: {', '.join(sorted(allowed_values))}",
        )
    rel_type_enum = RelationshipType(raw_type)

    # 2. Confidence range validation [0.0, 1.0]
    if confidence is not None and (confidence < 0.0 or confidence > 1.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="confidence must be between 0.0 and 1.0",
        )

    # 3. Self‑relationship check
    if source_memory_id == target_memory_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_memory_id and target_memory_id must differ",
        )

    # 4. Ownership validation – fetch both memories scoped to the user.
    source_mem = await get_memory_by_id(db, memory_id=source_memory_id, user_id=current_user_id)
    target_mem = await get_memory_by_id(db, memory_id=target_memory_id, user_id=current_user_id)
    if not source_mem or not target_mem:
        # The project prefers a 404 for cross‑user resource access.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or both memory IDs not found for the current user",
        )

    # 5. Delegate to repository; it handles the duplicate‑check.
    rel = await repo_create_relationship(
        db=db,
        user_id=current_user_id,
        source_memory_id=source_memory_id,
        target_memory_id=target_memory_id,
        relationship_type=rel_type_enum,
        confidence=confidence,
    )

    # 6. Log audit event (transactionally bound to session)
    from app.models.governance import AuditAction, AuditActorType
    from app.services import governance_service

    audit_meta = {
        "relationship_id": rel.id,
        "source_memory_id": rel.source_memory_id,
        "target_memory_id": rel.target_memory_id,
        "relationship_type": rel.relationship_type.value if hasattr(rel.relationship_type, "value") else str(rel.relationship_type),
        "confidence": rel.confidence,
    }
    await governance_service.log_event(
        db=db,
        user_id=current_user_id,
        action=AuditAction.RELATIONSHIP_CREATE,
        actor_type=AuditActorType.USER,
        actor_id=current_user_id,
        memory_id=rel.source_memory_id,
        metadata=audit_meta,
    )

    return rel

# ---------------------------------------------------------------------------
# READ SINGLE
# ---------------------------------------------------------------------------
async def get_relationship(
    db,
    current_user_id: str,
    relationship_id: str,
) -> MemoryRelationship | None:
    """Retrieve a relationship scoped to ``current_user_id``.

    Returns ``None`` when the relationship does not exist or belongs to another
    user – the router can translate this to the project's 404 response.
    """
    return await repo_get_relationship(db, relationship_id=relationship_id, user_id=current_user_id)

# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------
async def delete_relationship(
    db,
    current_user_id: str,
    relationship_id: str,
    memory_id: str | None = None,
) -> bool:
    """Delete a relationship owned by ``current_user_id``.

    ``True`` is returned when a row was deleted; ``False`` (treated as 404 by the
    router) when the relationship does not exist or is owned by a different user.
    """
    rel = await repo_get_relationship(db, relationship_id=relationship_id, user_id=current_user_id)
    if not rel:
        return False
    if memory_id and rel.source_memory_id != memory_id and rel.target_memory_id != memory_id:
        return False

    # Log audit event before deletion
    from app.models.governance import AuditAction, AuditActorType
    from app.services import governance_service

    audit_meta = {
        "relationship_id": rel.id,
        "source_memory_id": rel.source_memory_id,
        "target_memory_id": rel.target_memory_id,
        "relationship_type": rel.relationship_type.value if hasattr(rel.relationship_type, "value") else str(rel.relationship_type),
        "confidence": rel.confidence,
    }
    await governance_service.log_event(
        db=db,
        user_id=current_user_id,
        action=AuditAction.RELATIONSHIP_DELETE,
        actor_type=AuditActorType.USER,
        actor_id=current_user_id,
        memory_id=rel.source_memory_id,
        metadata=audit_meta,
    )

    return await repo_delete_relationship(db, relationship_id=relationship_id, user_id=current_user_id)

# ---------------------------------------------------------------------------
# LIST BY USER
# ---------------------------------------------------------------------------
async def list_by_user(
    db,
    current_user_id: str,
    offset: int = 0,
    limit: int = 100,
) -> list[MemoryRelationship]:
    """List relationships for ``current_user_id`` with pagination.
    """
    return await repo_list_by_user(db, user_id=current_user_id, offset=offset, limit=limit)

# ---------------------------------------------------------------------------
# LIST BY MEMORY
# ---------------------------------------------------------------------------
async def list_relationships_for_memory(
    db,
    current_user_id: str,
    memory_id: str,
    offset: int = 0,
    limit: int = 100,
) -> list[MemoryRelationship]:
    """List relationships for a memory owned by ``current_user_id``."""
    mem = await get_memory_by_id(db, memory_id=memory_id, user_id=current_user_id)
    if not mem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    return list(
        await repo_list_by_memory(
            db=db,
            user_id=current_user_id,
            memory_id=memory_id,
            offset=offset,
            limit=limit,
        )
    )

# ---------------------------------------------------------------------------
# ONE‑HOP RELATED MEMORIES
# ---------------------------------------------------------------------------
async def list_related_memories(
    db,
    current_user_id: str,
    memory_id: str,
    direction: str = "both",
    relationship_type: RelationshipType | str | None = None,
    confidence_min: float | None = None,
    temporal_mode: str = "current",
    reference_time: datetime | None = None,
    offset: int = 0,
    limit: int = 20,
) -> list[RelatedMemoryOut]:
    """Return target/source memories that are directly related to ``memory_id``.

    The underlying repository joins ``memory_relationships`` with ``memories``
    while enforcing ``user_id`` isolation for both the source and the target.
    """
    # 1. Ownership & existence validation on the focus memory
    mem = await get_memory_by_id(db, memory_id=memory_id, user_id=current_user_id)
    if not mem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    # 2. Limit defense
    if limit < 1 or limit > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="limit must be between 1 and 200",
        )

    # 3. Direction validation
    if direction not in ("outgoing", "incoming", "both"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid direction: '{direction}'. Must be one of: outgoing, incoming, both",
        )

    # 4. Confidence filter validation
    if confidence_min is not None and (confidence_min < 0.0 or confidence_min > 1.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="confidence_min must be between 0.0 and 1.0",
        )

    # 5. Relationship type validation
    rel_type_enum: RelationshipType | None = None
    if relationship_type is not None:
        allowed_types = {
            RelationshipType.UPDATES,
            RelationshipType.SUPERSEDES,
            RelationshipType.CONTRADICTS,
            RelationshipType.RELEVANT_TO,
        }
        allowed_values = {t.value for t in allowed_types}
        raw_type = (
            relationship_type.value
            if isinstance(relationship_type, RelationshipType)
            else str(relationship_type)
        )
        if raw_type not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported relationship_type: '{relationship_type}'. Allowed types: {', '.join(sorted(allowed_values))}",
            )
        rel_type_enum = RelationshipType(raw_type)

    # 6. Temporal mode validation
    if temporal_mode not in ("current", "historical", "any"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid temporal_mode: '{temporal_mode}'. Must be one of: current, historical, any",
        )

    # 7. Timezone normalization for reference_time
    ref_now = reference_time
    if ref_now is not None and ref_now.tzinfo is None:
        ref_now = ref_now.replace(tzinfo=timezone.utc)

    # 8. Query repository
    rows = await repo_list_related_memories(
        db=db,
        user_id=current_user_id,
        memory_id=memory_id,
        direction=direction,
        relationship_type=rel_type_enum,
        confidence_min=confidence_min,
        temporal_mode=temporal_mode,
        reference_time=ref_now,
        offset=offset,
        limit=limit,
    )

    # 9. Format response as RelatedMemoryOut
    results = []
    for r in rows:
        results.append(
            RelatedMemoryOut(
                id=r["mem_id"],
                memory_id=r["mem_id"],
                user_id=r["mem_user_id"],
                content=r["mem_content"],
                memory_type=r["mem_memory_type"],
                category=r["mem_memory_type"],
                status=r["mem_status"],
                importance=r["mem_importance"],
                confidence=r["mem_confidence"],
                valid_from=r["mem_valid_from"],
                valid_until=r["mem_valid_until"],
                superseded_by_memory_id=r["mem_superseded_by_memory_id"],
                relationship_id=r["rel_id"],
                relationship_type=r["rel_type"],
                relationship_confidence=r["rel_confidence"],
                direction=r["direction"],
            )
        )
    return results

# Exported symbols for ``__all__`` – helpful for static analysis.
__all__ = [
    "create_relationship",
    "get_relationship",
    "delete_relationship",
    "list_by_user",
    "list_relationships_for_memory",
    "list_related_memories",
]

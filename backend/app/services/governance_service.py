"""Memory Governance & Audit Service (Phase 3.2)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from app.models.governance import AuditAction, AuditActorType
from app.repositories import governance_repo
from app.schemas.governance import (
    AuditLogOut,
    MemoryExplainResponse,
    MemoryHistoryResponse,
    UserMemoryPolicyOut,
    UserMemoryPolicyUpdate,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def log_event(
    db: AsyncSession,
    user_id: str,
    action: AuditAction | str,
    actor_type: AuditActorType | str = AuditActorType.USER,
    actor_id: str = "",
    memory_id: str | None = None,
    from_version: int | None = None,
    to_version: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLogOut:
    """Log a memory governance or lifecycle audit event."""
    actor_id_val = actor_id or user_id
    entry = await governance_repo.create_audit_log(
        db=db,
        user_id=user_id,
        action=action,
        actor_type=actor_type,
        actor_id=actor_id_val,
        memory_id=memory_id,
        from_version=from_version,
        to_version=to_version,
        metadata=metadata,
    )
    meta_dict = {}
    if entry.metadata_json:
        try:
            meta_dict = json.loads(entry.metadata_json)
        except Exception:
            meta_dict = {}
    return AuditLogOut(
        id=entry.id,
        memory_id=entry.memory_id,
        user_id=entry.user_id,
        actor_type=entry.actor_type,
        actor_id=entry.actor_id,
        action=entry.action,
        from_version=entry.from_version,
        to_version=entry.to_version,
        metadata=meta_dict,
        created_at=entry.created_at,
    )


async def explain_memory(
    db: AsyncSession,
    memory_id: str,
    user_id: str,
) -> MemoryExplainResponse | None:
    """Produce an explainability and provenance summary for a memory."""
    from app.services import memory_service

    mem = await memory_service.get_memory_by_id(db, memory_id=memory_id, user_id=user_id)
    if not mem:
        return None

    # Detect conflicts for active memory
    conflicts = await memory_service.detect_conflicts(
        db,
        user_id=user_id,
        key=mem.key,
        content=mem.content,
        memory_type=mem.memory_type,
    )
    # Filter out self from conflict results
    active_conflicts = [c for c in conflicts if c.existing_memory_id != mem.id]

    # Fetch audit trail summary
    audit_logs = await governance_repo.list_audit_logs_for_memory(
        db, memory_id=memory_id, user_id=user_id
    )
    latest_event = audit_logs[-1] if audit_logs else None

    summary = {
        "total_events": len(audit_logs),
        "latest_action": latest_event.action if latest_event else "UNKNOWN",
        "latest_actor": f"{latest_event.actor_type}:{latest_event.actor_id}" if latest_event else "UNKNOWN",
        "latest_timestamp": latest_event.created_at.isoformat() if latest_event else mem.updated_at.isoformat(),
    }

    return MemoryExplainResponse(
        memory_id=mem.id,
        key=mem.key,
        memory_type=mem.memory_type,
        content=mem.content,
        status=mem.status,
        version=mem.version,
        source=mem.source,
        source_conversation_id=mem.source_conversation_id,
        source_message_id=mem.source_message_id,
        created_at=mem.created_at,
        updated_at=mem.updated_at,
        is_active=(mem.status == "active"),
        has_conflicts=len(active_conflicts) > 0,
        conflict_count=len(active_conflicts),
        audit_summary=summary,
    )


async def get_memory_history(
    db: AsyncSession,
    memory_id: str,
    user_id: str,
) -> MemoryHistoryResponse | None:
    """Get complete chronological audit history for a memory."""
    from app.services import memory_service

    mem = await memory_service.get_memory_by_id(db, memory_id=memory_id, user_id=user_id)
    if not mem:
        return None

    logs = await governance_repo.list_audit_logs_for_memory(
        db, memory_id=memory_id, user_id=user_id
    )
    events: list[AuditLogOut] = []
    for l in logs:
        meta_dict = {}
        if l.metadata_json:
            try:
                meta_dict = json.loads(l.metadata_json)
            except Exception:
                meta_dict = {}
        events.append(
            AuditLogOut(
                id=l.id,
                memory_id=l.memory_id,
                user_id=l.user_id,
                actor_type=l.actor_type,
                actor_id=l.actor_id,
                action=l.action,
                from_version=l.from_version,
                to_version=l.to_version,
                metadata=meta_dict,
                created_at=l.created_at,
            )
        )
    return MemoryHistoryResponse(
        memory_id=mem.id,
        total_events=len(events),
        history=events,
    )


async def get_user_policy(
    db: AsyncSession,
    user_id: str,
) -> UserMemoryPolicyOut:
    policy = await governance_repo.get_or_create_policy(db, user_id)
    return UserMemoryPolicyOut.model_validate(policy)


async def update_user_policy(
    db: AsyncSession,
    user_id: str,
    update_data: UserMemoryPolicyUpdate,
) -> UserMemoryPolicyOut:
    policy = await governance_repo.update_user_policy(db, user_id, update_data)
    return UserMemoryPolicyOut.model_validate(policy)

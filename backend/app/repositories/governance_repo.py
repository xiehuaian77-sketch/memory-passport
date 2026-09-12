"""Governance & Audit repository (Phase 3.2)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.governance import AuditAction, AuditActorType, MemoryAuditLog, UserMemoryPolicy
from app.schemas.governance import UserMemoryPolicyUpdate


# ------------------------------------------------------------
# AUDIT LOG REPO
# ------------------------------------------------------------

SENSITIVE_KEYS = {
    "password", "hashed_password", "secret", "token", "api_key",
    "jwt", "prompt", "conversation_history", "messages"
}


def sanitize_metadata(meta: dict[str, Any] | None) -> str:
    """Sanitize metadata to ensure no sensitive secrets or full prompts are saved."""
    if not meta:
        return "{}"
    clean: dict[str, Any] = {}
    for k, v in meta.items():
        k_lower = str(k).lower()
        if any(sk in k_lower for sk in SENSITIVE_KEYS):
            continue
        # Restrict string length if too long
        if isinstance(v, str) and len(v) > 500:
            clean[k] = v[:500] + "...[truncated]"
        elif isinstance(v, (int, float, bool, list, dict)) or v is None:
            clean[k] = v
        else:
            clean[k] = str(v)[:500]
    return json.dumps(clean, ensure_ascii=False)


async def create_audit_log(
    db: AsyncSession,
    user_id: str,
    action: str | AuditAction,
    actor_type: str | AuditActorType,
    actor_id: str,
    memory_id: str | None = None,
    from_version: int | None = None,
    to_version: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> MemoryAuditLog:
    action_val = action.value if isinstance(action, AuditAction) else str(action)
    actor_type_val = actor_type.value if isinstance(actor_type, AuditActorType) else str(actor_type)
    meta_str = sanitize_metadata(metadata)

    log_entry = MemoryAuditLog(
        memory_id=memory_id,
        user_id=user_id,
        actor_type=actor_type_val,
        actor_id=str(actor_id),
        action=action_val,
        from_version=from_version,
        to_version=to_version,
        metadata_json=meta_str,
    )
    db.add(log_entry)
    await db.flush()
    return log_entry


async def list_audit_logs_for_memory(
    db: AsyncSession,
    memory_id: str,
    user_id: str,
) -> Sequence[MemoryAuditLog]:
    """Fetch audit logs for a specific memory, ordered chronologically. Enforces user isolation."""
    stmt = (
        select(MemoryAuditLog)
        .where(
            MemoryAuditLog.memory_id == memory_id,
            MemoryAuditLog.user_id == user_id,
        )
        .order_by(MemoryAuditLog.created_at.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def list_audit_logs_for_user(
    db: AsyncSession,
    user_id: str,
    offset: int = 0,
    limit: int = 100,
) -> Sequence[MemoryAuditLog]:
    stmt = (
        select(MemoryAuditLog)
        .where(MemoryAuditLog.user_id == user_id)
        .order_by(MemoryAuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# ------------------------------------------------------------
# USER POLICY REPO
# ------------------------------------------------------------

async def get_user_policy(
    db: AsyncSession,
    user_id: str,
) -> UserMemoryPolicy | None:
    stmt = select(UserMemoryPolicy).where(UserMemoryPolicy.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_or_create_policy(
    db: AsyncSession,
    user_id: str,
) -> UserMemoryPolicy:
    policy = await get_user_policy(db, user_id)
    if policy is not None:
        return policy

    # Create safe default policy
    policy = UserMemoryPolicy(
        user_id=user_id,
        memory_enabled=True,
        require_confirmation=True,
        allow_memory_retrieval=True,
        allow_ai_extraction=True,
    )
    db.add(policy)
    await db.flush()
    await db.refresh(policy)
    return policy


async def update_user_policy(
    db: AsyncSession,
    user_id: str,
    update_data: UserMemoryPolicyUpdate,
) -> UserMemoryPolicy:
    policy = await get_or_create_policy(db, user_id)
    for field, val in update_data.model_dump(exclude_unset=True).items():
        if val is not None:
            setattr(policy, field, val)
    await db.flush()
    await db.refresh(policy)
    return policy

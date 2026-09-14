"""Agent Permission Service (Phase 6.5).

Handles scoped permission grants, lifecycle evaluations, and security checks.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import TYPE_CHECKING

from app.models.agent import AgentStatus
from app.models.governance import AuditAction, AuditActorType
from app.models.permission_grant import AgentPermission, PermissionGrant
from app.repositories import agent_repo, permission_grant_repo
from app.services import governance_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("memory_passport.agent_permission_service")

ALLOWED_PERMISSIONS = {
    AgentPermission.READ_MEMORY.value,
    AgentPermission.READ_PREFERENCES.value,
    AgentPermission.CREATE_MEMORY.value,
    AgentPermission.UPDATE_MEMORY.value,
}


def _validate_permission_str(perm: str) -> str:
    cleaned = perm.strip().upper()
    if cleaned not in ALLOWED_PERMISSIONS:
        raise ValueError(
            f"Invalid or unsupported permission: '{perm}'. "
            f"Allowed permissions are: {sorted(list(ALLOWED_PERMISSIONS))}"
        )
    return cleaned


async def grant_permission(
    db: AsyncSession,
    *,
    user_id: str,
    agent_id: str,
    permission: AgentPermission | str,
    expires_at: datetime | None = None,
) -> PermissionGrant:
    """Grant or re-activate a permission for an agent owned by user_id."""
    perm_val = _validate_permission_str(
        permission.value if isinstance(permission, AgentPermission) else str(permission)
    )

    agent = await agent_repo.get_by_id(db, agent_id=agent_id, user_id=user_id)
    if agent is None:
        raise LookupError("Agent not found")

    if agent.status != AgentStatus.ACTIVE.value:
        raise ValueError("Cannot grant permission to a revoked agent")

    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    grant = await permission_grant_repo.upsert_grant(
        db,
        user_id=user_id,
        agent_id=agent_id,
        permission=perm_val,
        expires_at=expires_at,
    )

    try:
        expires_iso = grant.expires_at.isoformat() if grant.expires_at else None
        await governance_service.log_event(
            db=db,
            user_id=user_id,
            action=AuditAction.PERMISSION_GRANT,
            actor_type=AuditActorType.USER,
            actor_id=user_id,
            metadata={
                "agent_id": agent_id,
                "permission": perm_val,
                "expires_at": expires_iso,
            },
        )
    except Exception as exc:
        logger.warning("Failed to log PERMISSION_GRANT audit event: %s", exc)

    return grant


async def revoke_permission(
    db: AsyncSession,
    *,
    user_id: str,
    agent_id: str,
    permission: AgentPermission | str,
) -> PermissionGrant | None:
    """Revoke a specific permission for an agent."""
    perm_val = _validate_permission_str(
        permission.value if isinstance(permission, AgentPermission) else str(permission)
    )

    agent = await agent_repo.get_by_id(db, agent_id=agent_id, user_id=user_id)
    if agent is None:
        return None

    grant = await permission_grant_repo.revoke_grant(
        db,
        user_id=user_id,
        agent_id=agent_id,
        permission=perm_val,
    )
    if grant is None:
        return None

    try:
        await governance_service.log_event(
            db=db,
            user_id=user_id,
            action=AuditAction.PERMISSION_REVOKE,
            actor_type=AuditActorType.USER,
            actor_id=user_id,
            metadata={
                "agent_id": agent_id,
                "permission": perm_val,
            },
        )
    except Exception as exc:
        logger.warning("Failed to log PERMISSION_REVOKE audit event: %s", exc)

    return grant


async def list_permissions(
    db: AsyncSession,
    *,
    user_id: str,
    agent_id: str,
) -> list[PermissionGrant]:
    """List all permission grants for an agent."""
    agent = await agent_repo.get_by_id(db, agent_id=agent_id, user_id=user_id)
    if agent is None:
        raise LookupError("Agent not found")
    return await permission_grant_repo.list_by_agent(db, user_id=user_id, agent_id=agent_id)


async def check_permission(
    db: AsyncSession,
    *,
    user_id: str,
    agent_id: str,
    permission: AgentPermission | str,
) -> bool:
    """Evaluate whether an agent is currently authorized for a specific permission.

    Evaluates:
    1. Agent exists and belongs to user_id
    2. Agent.status == ACTIVE
    3. Grant exists and belongs to (user_id, agent_id)
    4. Grant.status == ACTIVE
    5. Grant is not expired (expires_at is None or in future)
    """
    try:
        perm_val = _validate_permission_str(
            permission.value if isinstance(permission, AgentPermission) else str(permission)
        )
    except ValueError:
        return False

    agent = await agent_repo.get_by_id(db, agent_id=agent_id, user_id=user_id)
    if agent is None or agent.status != AgentStatus.ACTIVE.value:
        return False

    grant = await permission_grant_repo.get(
        db,
        user_id=user_id,
        agent_id=agent_id,
        permission=perm_val,
    )
    if grant is None:
        return False

    return grant.is_effective_active

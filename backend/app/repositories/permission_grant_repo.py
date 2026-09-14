"""Permission Grant Repository (Phase 6.5).

Provides data access routines for PermissionGrant entities with strict user_id tenant boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permission_grant import GrantStatus, PermissionGrant


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get(
    db: AsyncSession,
    *,
    user_id: str,
    agent_id: str,
    permission: str,
) -> PermissionGrant | None:
    """Retrieve specific grant for an agent under user_id."""
    stmt = select(PermissionGrant).where(
        PermissionGrant.user_id == user_id,
        PermissionGrant.agent_id == agent_id,
        PermissionGrant.permission == permission,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_by_agent(
    db: AsyncSession,
    *,
    user_id: str,
    agent_id: str,
) -> list[PermissionGrant]:
    """List all permission grants for a specific agent under user_id."""
    stmt = (
        select(PermissionGrant)
        .where(
            PermissionGrant.user_id == user_id,
            PermissionGrant.agent_id == agent_id,
        )
        .order_by(PermissionGrant.created_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_by_user(
    db: AsyncSession,
    *,
    user_id: str,
) -> list[PermissionGrant]:
    """List all permission grants owned by user_id."""
    stmt = (
        select(PermissionGrant)
        .where(PermissionGrant.user_id == user_id)
        .order_by(PermissionGrant.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def upsert_grant(
    db: AsyncSession,
    *,
    user_id: str,
    agent_id: str,
    permission: str,
    expires_at: datetime | None,
) -> PermissionGrant:
    """Create or re-activate a permission grant."""
    existing = await get(db, user_id=user_id, agent_id=agent_id, permission=permission)
    now = _utcnow()
    if existing is not None:
        existing.status = GrantStatus.ACTIVE.value
        existing.expires_at = expires_at
        existing.revoked_at = None
        existing.updated_at = now
        await db.flush()
        await db.refresh(existing)
        return existing

    grant = PermissionGrant(
        user_id=user_id,
        agent_id=agent_id,
        permission=permission,
        status=GrantStatus.ACTIVE.value,
        created_at=now,
        updated_at=now,
        expires_at=expires_at,
        revoked_at=None,
    )
    db.add(grant)
    await db.flush()
    await db.refresh(grant)
    return grant


async def revoke_grant(
    db: AsyncSession,
    *,
    user_id: str,
    agent_id: str,
    permission: str,
) -> PermissionGrant | None:
    """Revoke a single permission grant."""
    grant = await get(db, user_id=user_id, agent_id=agent_id, permission=permission)
    if grant is None:
        return None
    grant.status = GrantStatus.REVOKED.value
    grant.revoked_at = _utcnow()
    grant.updated_at = _utcnow()
    await db.flush()
    await db.refresh(grant)
    return grant


async def revoke_all_for_agent(
    db: AsyncSession,
    *,
    user_id: str,
    agent_id: str,
) -> list[PermissionGrant]:
    """Revoke all active permissions for an agent."""
    grants = await list_by_agent(db, user_id=user_id, agent_id=agent_id)
    now = _utcnow()
    revoked: list[PermissionGrant] = []
    for g in grants:
        if g.status != GrantStatus.REVOKED.value:
            g.status = GrantStatus.REVOKED.value
            g.revoked_at = now
            g.updated_at = now
            revoked.append(g)
    await db.flush()
    for g in revoked:
        await db.refresh(g)
    return revoked

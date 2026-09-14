"""Agent Repository (Phase 6.5).

Provides data access routines for Agent entities with strict user_id tenant boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent, AgentStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def create(
    db: AsyncSession,
    *,
    user_id: str,
    name: str,
    description: str | None,
    key_hash: str,
) -> Agent:
    """Create a new Agent bound to user_id."""
    agent = Agent(
        user_id=user_id,
        name=name.strip(),
        description=description.strip() if description else None,
        key_hash=key_hash,
        status=AgentStatus.ACTIVE.value,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


async def get_by_id(
    db: AsyncSession,
    agent_id: str,
    *,
    user_id: str,
) -> Agent | None:
    """Retrieve agent ensuring strict tenant boundary."""
    stmt = select(Agent).where(
        Agent.id == agent_id,
        Agent.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_key_hash(
    db: AsyncSession,
    key_hash: str,
) -> Agent | None:
    """Retrieve agent by key_hash for authentication resolution."""
    stmt = select(Agent).where(Agent.key_hash == key_hash)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_by_user(
    db: AsyncSession,
    *,
    user_id: str,
) -> list[Agent]:
    """List all agents belonging to user_id."""
    stmt = (
        select(Agent)
        .where(Agent.user_id == user_id)
        .order_by(Agent.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def revoke(
    db: AsyncSession,
    agent_id: str,
    *,
    user_id: str,
) -> Agent | None:
    """Revoke an agent belonging to user_id."""
    agent = await get_by_id(db, agent_id, user_id=user_id)
    if agent is None:
        return None
    agent.status = AgentStatus.REVOKED.value
    agent.updated_at = _utcnow()
    await db.flush()
    await db.refresh(agent)
    return agent

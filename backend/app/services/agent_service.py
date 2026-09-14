"""Agent Service (Phase 6.5).

Coordinates Agent lifecycle, secure API key generation, and audit logging.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import select

from app.models.agent import Agent, AgentStatus
from app.models.caller import AgentCaller
from app.models.governance import AuditAction, AuditActorType
from app.models.user import User
from app.repositories import agent_repo, permission_grant_repo
from app.services import governance_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("memory_passport.agent_service")


def generate_agent_key() -> str:
    """Generate a cryptographically secure random 64-hex token."""
    return secrets.token_hex(32)


def hash_agent_key(raw_key: str) -> str:
    """Hash an agent API key using SHA-256."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_agent_key(raw_key: str, key_hash: str) -> bool:
    """Verify an agent API key using constant-time comparison."""
    computed = hash_agent_key(raw_key)
    return hmac.compare_digest(computed, key_hash)


async def create_agent(
    db: AsyncSession,
    *,
    user_id: str,
    name: str,
    description: str | None = None,
) -> tuple[Agent, str]:
    """Create a new Agent with an automatically generated secure API key.

    Returns:
        tuple of (agent_orm_instance, plaintext_api_key)
    """
    if not name or not name.strip():
        raise ValueError("Agent name cannot be empty")

    raw_token = generate_agent_key()
    raw_api_key = f"mp_ak_{raw_token}"
    key_hash = hash_agent_key(raw_api_key)

    agent = await agent_repo.create(
        db,
        user_id=user_id,
        name=name,
        description=description,
        key_hash=key_hash,
    )

    try:
        await governance_service.log_event(
            db=db,
            user_id=user_id,
            action=AuditAction.AGENT_REGISTER,
            actor_type=AuditActorType.USER,
            actor_id=user_id,
            metadata={"agent_id": agent.id, "name": agent.name},
        )
    except Exception as exc:
        logger.warning("Failed to log AGENT_REGISTER audit event: %s", exc)

    return agent, raw_api_key


async def get_agent(
    db: AsyncSession,
    *,
    user_id: str,
    agent_id: str,
) -> Agent | None:
    """Retrieve an agent with tenant boundary enforcement."""
    return await agent_repo.get_by_id(db, agent_id=agent_id, user_id=user_id)


async def list_agents(
    db: AsyncSession,
    *,
    user_id: str,
) -> list[Agent]:
    """List all agents for user_id."""
    return await agent_repo.list_by_user(db, user_id=user_id)


async def revoke_agent(
    db: AsyncSession,
    *,
    user_id: str,
    agent_id: str,
) -> Agent | None:
    """Revoke an agent and all of its associated permission grants."""
    agent = await agent_repo.get_by_id(db, agent_id=agent_id, user_id=user_id)
    if agent is None:
        return None

    # Revoke all permission grants
    await permission_grant_repo.revoke_all_for_agent(db, user_id=user_id, agent_id=agent_id)

    # Revoke agent itself
    revoked = await agent_repo.revoke(db, agent_id=agent_id, user_id=user_id)

    try:
        await governance_service.log_event(
            db=db,
            user_id=user_id,
            action=AuditAction.AGENT_REVOKE,
            actor_type=AuditActorType.USER,
            actor_id=user_id,
            metadata={"agent_id": agent_id, "name": agent.name},
        )
    except Exception as exc:
        logger.warning("Failed to log AGENT_REVOKE audit event: %s", exc)

    return revoked


async def authenticate_agent_key(
    db: AsyncSession,
    raw_key: str,
) -> AgentCaller:
    """Authenticate an AI Agent via raw API key.

    Fail-closed: Returns AgentCaller or raises HTTPException(401, 'Invalid agent credentials').
    """
    if not raw_key or not isinstance(raw_key, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent credentials",
        )

    # Must have mp_ak_ prefix and non-empty token
    if not raw_key.startswith("mp_ak_") or len(raw_key) <= 6:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent credentials",
        )

    key_hash = hash_agent_key(raw_key)
    agent = await agent_repo.get_by_key_hash(db, key_hash)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent credentials",
        )

    # Constant-time comparison
    if not verify_agent_key(raw_key, agent.key_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent credentials",
        )

    # Check status: must be ACTIVE
    if agent.status != AgentStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent credentials",
        )

    # Resolve owner User
    user_stmt = select(User).where(User.id == agent.user_id)
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent credentials",
        )

    return AgentCaller(
        user_id=agent.user_id,
        agent_id=agent.id,
        agent=agent,
        user=user,
    )

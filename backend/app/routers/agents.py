"""Agents and Permission Grants Router (Phase 6.5).

Provides REST endpoints for registering AI Agents, managing permission delegations,
and verifying authorization status. All endpoints strictly enforce user_id tenant boundaries.
"""

from __future__ import annotations

import json
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.governance import MemoryAuditLog
from app.models.user import User
from app.schemas.agent import (
    AgentAuditLogOut,
    AgentCreate,
    AgentCreateResponse,
    AgentOut,
    PermissionCheckResponse,
    PermissionGrantCreate,
    PermissionGrantOut,
)
from app.services import agent_permission_service, agent_service

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _grant_to_out(grant) -> PermissionGrantOut:
    return PermissionGrantOut(
        id=grant.id,
        user_id=grant.user_id,
        agent_id=grant.agent_id,
        permission=grant.permission,
        status=grant.status,
        created_at=grant.created_at,
        updated_at=grant.updated_at,
        expires_at=grant.expires_at,
        revoked_at=grant.revoked_at,
        is_active=grant.is_effective_active,
    )


@router.post("", response_model=AgentCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: AgentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a new AI Agent for the authenticated user. Returns plaintext API key ONCE."""
    try:
        agent, api_key = await agent_service.create_agent(
            db,
            user_id=user.id,
            name=body.name,
            description=body.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return AgentCreateResponse(
        id=agent.id,
        user_id=agent.user_id,
        name=agent.name,
        description=agent.description,
        api_key=api_key,
        status=agent.status,
        created_at=agent.created_at,
    )


@router.get("", response_model=list[AgentOut])
async def list_agents(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all AI Agents owned by the authenticated user."""
    agents = await agent_service.list_agents(db, user_id=user.id)
    return [AgentOut.model_validate(a) for a in agents]


@router.get("/audit-logs", response_model=list[AgentAuditLogOut])
async def list_agent_audit_logs(
    agent_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List agent access and permission audit trail events for current user."""
    agent_actions = [
        "AGENT_ACCESS",
        "AGENT_REGISTER",
        "AGENT_REVOKE",
        "PERMISSION_GRANT",
        "PERMISSION_REVOKE",
    ]

    stmt = (
        select(MemoryAuditLog)
        .where(
            MemoryAuditLog.user_id == user.id,
            MemoryAuditLog.action.in_(agent_actions),
        )
        .order_by(MemoryAuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    logs = list((await db.execute(stmt)).scalars().all())

    results: list[AgentAuditLogOut] = []
    for log in logs:
        meta: dict[str, Any] = {}
        if log.metadata_json:
            try:
                meta = json.loads(log.metadata_json) if isinstance(log.metadata_json, str) else (log.metadata_json or {})
            except Exception:
                meta = {}

        if agent_id:
            meta_agent_id = meta.get("agent_id")
            if log.actor_id != agent_id and meta_agent_id != agent_id:
                continue

        results.append(
            AgentAuditLogOut(
                id=log.id,
                user_id=log.user_id,
                actor_type=log.actor_type,
                actor_id=log.actor_id,
                action=log.action,
                tool=meta.get("tool"),
                permission=meta.get("permission"),
                decision=meta.get("decision"),
                reason=meta.get("reason"),
                created_at=log.created_at,
                metadata=meta,
            )
        )

    return results


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve details of a specific AI Agent."""
    agent = await agent_service.get_agent(db, user_id=user.id, agent_id=agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return AgentOut.model_validate(agent)


@router.post("/{agent_id}/revoke", response_model=AgentOut)
async def revoke_agent(
    agent_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an AI Agent and all its permission grants."""
    agent = await agent_service.revoke_agent(db, user_id=user.id, agent_id=agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return AgentOut.model_validate(agent)


@router.post("/{agent_id}/permissions", response_model=PermissionGrantOut, status_code=status.HTTP_201_CREATED)
async def grant_permission(
    agent_id: str,
    body: PermissionGrantCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Grant a scoped permission to an active AI Agent."""
    try:
        grant = await agent_permission_service.grant_permission(
            db,
            user_id=user.id,
            agent_id=agent_id,
            permission=body.permission,
            expires_at=body.expires_at,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return _grant_to_out(grant)


@router.get("/{agent_id}/permissions", response_model=list[PermissionGrantOut])
async def list_permissions(
    agent_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all permission grants for an AI Agent."""
    try:
        grants = await agent_permission_service.list_permissions(
            db,
            user_id=user.id,
            agent_id=agent_id,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from e

    return [_grant_to_out(g) for g in grants]


@router.post("/{agent_id}/permissions/{permission}/revoke", response_model=PermissionGrantOut)
async def revoke_permission(
    agent_id: str,
    permission: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a specific permission grant from an AI Agent."""
    try:
        grant = await agent_permission_service.revoke_permission(
            db,
            user_id=user.id,
            agent_id=agent_id,
            permission=permission,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    if grant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission grant or agent not found")

    return _grant_to_out(grant)


@router.get("/{agent_id}/check-permission/{permission}", response_model=PermissionCheckResponse)
async def check_permission(
    agent_id: str,
    permission: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate whether an agent is authorized for a specific permission."""
    allowed = await agent_permission_service.check_permission(
        db,
        user_id=user.id,
        agent_id=agent_id,
        permission=permission,
    )
    return PermissionCheckResponse(
        allowed=allowed,
        agent_id=agent_id,
        permission=permission,
        reason=None if allowed else "Permission not granted, revoked, or expired",
    )

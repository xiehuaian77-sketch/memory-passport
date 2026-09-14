"""Authorization Service (Phase 6.5 Step 2).

Centralizes permission evaluation, tool-to-permission mapping, and audit logging
for external AI Agents invoking the MCP endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any

from app.models.agent import AgentStatus
from app.models.caller import CallerContext
from app.models.governance import AuditAction, AuditActorType
from app.models.permission_grant import AgentPermission
from app.services import agent_permission_service, governance_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("memory_passport.authorization_service")


@dataclass
class AuthorizationDecision:
    """Result of an authorization evaluation."""
    allowed: bool
    permission: str | None = None
    preference_only: bool = False
    reason: str | None = None


# MCP Tool to AgentPermission mapping (Section VIII)
TOOL_PERMISSION_MAP: dict[str, list[AgentPermission]] = {
    # Memory reading capabilities
    "memory_search": [AgentPermission.READ_MEMORY, AgentPermission.READ_PREFERENCES],
    "memory_retrieve": [AgentPermission.READ_MEMORY, AgentPermission.READ_PREFERENCES],
    "memory_get": [AgentPermission.READ_MEMORY, AgentPermission.READ_PREFERENCES],
    "memory_related": [AgentPermission.READ_MEMORY],
    "memory_relationships": [AgentPermission.READ_MEMORY],
    "memory_explain": [AgentPermission.READ_MEMORY],
    "memory_history": [AgentPermission.READ_MEMORY],

    # Memory creation capabilities
    "memory_create": [AgentPermission.CREATE_MEMORY],

    # Memory modification capabilities
    "memory_update": [AgentPermission.UPDATE_MEMORY],
}

# High-risk lifecycle mutations strictly forbidden for AI Agents (Section IX)
HIGH_RISK_TOOLS: set[str] = {
    "memory_archive",
    "memory_restore",
    "memory_supersede",
    "hard_delete",
    "conflict_resolve",
}

# Conversation & Chat tools forbidden for AI Agents in Phase 6.5 (Section XV)
UNPERMITTED_AGENT_TOOLS: set[str] = {
    "chat",
    "conversation_memory_extract",
    "conversation_memory_confirm",
}


async def authorize_mcp_tool(
    db: AsyncSession,
    *,
    caller: CallerContext,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> AuthorizationDecision:
    """Authorize an MCP tool invocation against caller identity and granted permissions.

    Evaluates:
    1. Human callers pass without agent permission restrictions.
    2. Agent caller existence and ACTIVE status.
    3. Rejection of high-risk tools and unpermitted chat/extract tools.
    4. Exact tool permission matching (fail-closed).
    5. Specific handling of READ_PREFERENCES as a narrower scope.
    """
    if caller.is_human:
        return AuthorizationDecision(allowed=True, reason="Human caller authorized")

    # Agent caller validation
    if not caller.is_agent or not hasattr(caller, "agent_id") or not caller.agent_id:
        return AuthorizationDecision(allowed=False, reason="Invalid agent caller context")

    # Real-time check: agent status must be ACTIVE
    if caller.agent is not None and caller.agent.status != AgentStatus.ACTIVE.value:
        return AuthorizationDecision(allowed=False, reason="Agent is not active or has been revoked")

    # Defense against high-risk tools
    if tool_name in HIGH_RISK_TOOLS:
        return AuthorizationDecision(
            allowed=False,
            reason=f"Tool '{tool_name}' is high-risk and forbidden for AI Agents",
        )

    # Defense against unpermitted conversation tools
    if tool_name in UNPERMITTED_AGENT_TOOLS:
        return AuthorizationDecision(
            allowed=False,
            reason=f"Tool '{tool_name}' is not permitted for AI Agents",
        )

    # Tool existence in agent matrix
    if tool_name not in TOOL_PERMISSION_MAP:
        return AuthorizationDecision(
            allowed=False,
            reason=f"Tool '{tool_name}' is not authorized for AI Agents",
        )

    # Dynamic permission evaluation without caching
    if tool_name in ("memory_search", "memory_retrieve", "memory_get"):
        has_read_mem = await agent_permission_service.check_permission(
            db,
            user_id=caller.user_id,
            agent_id=caller.agent_id,
            permission=AgentPermission.READ_MEMORY,
        )
        if has_read_mem:
            return AuthorizationDecision(
                allowed=True,
                permission=AgentPermission.READ_MEMORY.value,
                preference_only=False,
            )

        has_read_pref = await agent_permission_service.check_permission(
            db,
            user_id=caller.user_id,
            agent_id=caller.agent_id,
            permission=AgentPermission.READ_PREFERENCES,
        )
        if has_read_pref:
            return AuthorizationDecision(
                allowed=True,
                permission=AgentPermission.READ_PREFERENCES.value,
                preference_only=True,
            )

        return AuthorizationDecision(
            allowed=False,
            permission=AgentPermission.READ_MEMORY.value,
            reason="Missing required permission: READ_MEMORY or READ_PREFERENCES",
        )

    if tool_name in ("memory_related", "memory_relationships", "memory_explain", "memory_history"):
        has_read = await agent_permission_service.check_permission(
            db,
            user_id=caller.user_id,
            agent_id=caller.agent_id,
            permission=AgentPermission.READ_MEMORY,
        )
        if has_read:
            return AuthorizationDecision(
                allowed=True,
                permission=AgentPermission.READ_MEMORY.value,
                preference_only=False,
            )
        return AuthorizationDecision(
            allowed=False,
            permission=AgentPermission.READ_MEMORY.value,
            reason="Missing required permission: READ_MEMORY",
        )

    if tool_name == "memory_create":
        has_create = await agent_permission_service.check_permission(
            db,
            user_id=caller.user_id,
            agent_id=caller.agent_id,
            permission=AgentPermission.CREATE_MEMORY,
        )
        if has_create:
            return AuthorizationDecision(
                allowed=True,
                permission=AgentPermission.CREATE_MEMORY.value,
            )
        return AuthorizationDecision(
            allowed=False,
            permission=AgentPermission.CREATE_MEMORY.value,
            reason="Missing required permission: CREATE_MEMORY",
        )

    if tool_name == "memory_update":
        has_update = await agent_permission_service.check_permission(
            db,
            user_id=caller.user_id,
            agent_id=caller.agent_id,
            permission=AgentPermission.UPDATE_MEMORY,
        )
        if has_update:
            return AuthorizationDecision(
                allowed=True,
                permission=AgentPermission.UPDATE_MEMORY.value,
            )
        return AuthorizationDecision(
            allowed=False,
            permission=AgentPermission.UPDATE_MEMORY.value,
            reason="Missing required permission: UPDATE_MEMORY",
        )

    return AuthorizationDecision(allowed=False, reason=f"Unauthorized tool: {tool_name}")


async def log_mcp_audit(
    db: AsyncSession,
    *,
    caller: CallerContext,
    tool_name: str,
    decision: AuthorizationDecision,
) -> None:
    """Record an audit trail entry for an Agent MCP tool invocation."""
    if not caller.is_agent:
        return

    try:
        await governance_service.log_event(
            db=db,
            user_id=caller.user_id,
            action=AuditAction.AGENT_ACCESS,
            actor_type=AuditActorType.AGENT,
            actor_id=caller.agent_id,
            metadata={
                "agent_id": caller.agent_id,
                "tool": tool_name,
                "permission": decision.permission or "NONE",
                "decision": "ALLOW" if decision.allowed else "DENY",
                "reason": decision.reason,
            },
        )
        await db.commit()
    except Exception as exc:
        logger.warning("Failed to record MCP agent audit log: %s", exc)

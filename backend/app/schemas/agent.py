from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from app.models.permission_grant import AgentPermission


class AgentCreate(BaseModel):
    """Payload to register a new AI Agent."""
    name: str = Field(min_length=1, max_length=100, description="Human-friendly Agent identifier")
    description: str | None = Field(default=None, max_length=1000, description="Optional agent description")


class AgentCreateResponse(BaseModel):
    """Response returned ONLY upon agent creation, exposing plaintext api_key once."""
    id: str
    user_id: str
    name: str
    description: str | None
    api_key: str = Field(description="One-time plaintext secret. Store securely; never retrievable again.")
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentOut(BaseModel):
    """Public agent profile. Strictly omits api_key and key_hash."""
    id: str
    user_id: str
    name: str
    description: str | None
    status: str
    has_api_key: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PermissionGrantCreate(BaseModel):
    """Payload to grant a permission to an Agent."""
    permission: AgentPermission = Field(description="Permission atom: READ_MEMORY, READ_PREFERENCES, CREATE_MEMORY, UPDATE_MEMORY")
    expires_at: datetime | None = Field(default=None, description="Optional ISO expiration timestamp. None means permanent.")


class PermissionGrantOut(BaseModel):
    """Permission grant details."""
    id: str
    user_id: str
    agent_id: str
    permission: str
    status: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class PermissionCheckRequest(BaseModel):
    """Internal or test check request."""
    agent_id: str
    permission: AgentPermission


class PermissionCheckResponse(BaseModel):
    """Permission evaluation result."""
    allowed: bool
    agent_id: str
    permission: str
    reason: str | None = None


class AgentAuditLogOut(BaseModel):
    """Audit log representation for agent access and permission lifecycle."""
    id: str
    user_id: str
    actor_type: str
    actor_id: str
    action: str
    tool: str | None = None
    permission: str | None = None
    decision: str | None = None
    reason: str | None = None
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


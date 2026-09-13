"""Audit and Explainability models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from memory_passport.models.common import BaseSDKModel


class MemoryAuditLog(BaseSDKModel):
    id: str
    memory_id: str | None = None
    user_id: str
    actor_type: str
    actor_id: str
    action: str
    from_version: int | None = None
    to_version: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class MemoryExplainResponse(BaseSDKModel):
    memory_id: str
    key: str
    memory_type: str
    content: str
    status: str
    version: int
    source: str
    source_conversation_id: str | None = None
    source_message_id: str | None = None
    created_at: datetime
    updated_at: datetime
    is_active: bool
    has_conflicts: bool
    active_conflicts_count: int
    total_revisions: int
    last_audit_action: str | None = None
    last_audit_at: datetime | None = None

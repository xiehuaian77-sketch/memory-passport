"""Pydantic schemas for Memory Governance & Audit (Phase 3.2)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AuditLogOut(BaseModel):
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

    model_config = {"from_attributes": True}

    @field_validator("metadata", mode="before")
    @classmethod
    def parse_metadata(cls, v: Any) -> dict[str, Any]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        if isinstance(v, dict):
            return v
        return {}


class UserMemoryPolicyOut(BaseModel):
    user_id: str
    memory_enabled: bool = True
    require_confirmation: bool = True
    allow_memory_retrieval: bool = True
    allow_ai_extraction: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserMemoryPolicyUpdate(BaseModel):
    memory_enabled: bool | None = None
    require_confirmation: bool | None = None
    allow_memory_retrieval: bool | None = None
    allow_ai_extraction: bool | None = None


class MemoryExplainResponse(BaseModel):
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
    conflict_count: int
    audit_summary: dict[str, Any] = Field(default_factory=dict)


class MemoryHistoryResponse(BaseModel):
    memory_id: str
    total_events: int
    history: list[AuditLogOut] = Field(default_factory=list)

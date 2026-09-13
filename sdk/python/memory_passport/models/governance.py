"""Governance policy models."""

from __future__ import annotations

from datetime import datetime

from memory_passport.models.common import BaseSDKModel


class UserMemoryPolicy(BaseSDKModel):
    user_id: str
    memory_enabled: bool = True
    require_confirmation: bool = True
    allow_memory_retrieval: bool = True
    allow_ai_extraction: bool = True
    created_at: datetime
    updated_at: datetime


class UserMemoryPolicyUpdate(BaseSDKModel):
    memory_enabled: bool | None = None
    require_confirmation: bool | None = None
    allow_memory_retrieval: bool | None = None
    allow_ai_extraction: bool | None = None

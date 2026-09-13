"""Conversation and extraction models."""

from __future__ import annotations

from datetime import datetime
from memory_passport.models.common import BaseSDKModel


class ConversationMessage(BaseSDKModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime


class Conversation(BaseSDKModel):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    messages: list[ConversationMessage] = []


class ConversationMemoryCandidate(BaseSDKModel):
    id: str
    memory_type: str = "preference"
    key: str
    content: str
    importance: float = 0.5
    confidence: float = 1.0
    tags: list[str] = []
    reason: str = ""
    source: str = "conversation"
    raw_content: str = ""
    signature: str = ""


class ConversationExtractResponse(BaseSDKModel):
    conversation_id: str
    candidates: list[ConversationMemoryCandidate] = []


class CandidateUserEdits(BaseSDKModel):
    key: str | None = None
    content: str | None = None
    tags: str | None = None


class ConversationConfirmCandidate(BaseSDKModel):
    id: str
    signature: str
    memory_type: str = "preference"
    key: str | None = None
    content: str
    importance: float = 0.5
    confidence: float = 1.0
    tags: list[str] | str = []
    raw_content: str = ""
    is_shared: bool = True

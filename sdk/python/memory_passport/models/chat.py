"""Chat models."""

from __future__ import annotations

from typing import Any
from memory_passport.models.common import BaseSDKModel


class ChatMessageInput(BaseSDKModel):
    role: str
    content: str


class ExtractedMemory(BaseSDKModel):
    category: str
    key: str
    content: str
    confidence: float


class ChatResponse(BaseSDKModel):
    response: str
    reply: str | None = None
    conversation_id: str | None = None
    extracted_memories: list[ExtractedMemory] = []
    loaded_memories: list[Any] = []

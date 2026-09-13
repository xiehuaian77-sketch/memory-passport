"""Chat resource client."""

from __future__ import annotations

from typing import Any
from memory_passport.models.chat import ChatMessageInput, ChatResponse
from memory_passport.transport import MemoryPassportTransport


class ChatResource:
    """Resource client for AI Chat endpoint with context injection."""

    def __init__(self, transport: MemoryPassportTransport) -> None:
        self._transport = transport

    def chat(
        self,
        message: str,
        *,
        conversation_id: str | None = None,
        history: list[ChatMessageInput | dict[str, Any]] | None = None,
        agent_role: str = "general",
    ) -> ChatResponse:
        clean_history = [
            h.model_dump() if isinstance(h, ChatMessageInput) else h
            for h in (history or [])
        ]
        payload = {
            "message": message,
            "conversation_id": conversation_id,
            "history": clean_history,
            "agent_role": agent_role,
        }
        res = self._transport.request("POST", "/api/chat", json=payload)
        return ChatResponse.model_validate(res)

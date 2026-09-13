"""Conversations resource client."""

from __future__ import annotations

from typing import Any

from memory_passport.models.conversations import (
    CandidateUserEdits,
    Conversation,
    ConversationConfirmCandidate,
    ConversationExtractResponse,
    ConversationMessage,
)
from memory_passport.models.memories import Memory
from memory_passport.transport import MemoryPassportTransport


class ConversationsResource:
    """Resource client for conversation management and memory extraction."""

    def __init__(self, transport: MemoryPassportTransport) -> None:
        self._transport = transport

    def create(self) -> Conversation:
        res = self._transport.request("POST", "/api/conversations")
        return Conversation.model_validate(res)

    def list(self, *, limit: int = 50) -> list[Conversation]:
        params = {"limit": limit}
        res = self._transport.request("GET", "/api/conversations", params=params)
        return [Conversation.model_validate(c) for c in res]

    def get(self, conversation_id: str) -> Conversation:
        res = self._transport.request("GET", f"/api/conversations/{conversation_id}")
        return Conversation.model_validate(res)

    def delete(self, conversation_id: str) -> None:
        self._transport.request("DELETE", f"/api/conversations/{conversation_id}")

    def get_messages(self, conversation_id: str, *, limit: int = 50) -> list[ConversationMessage]:
        params = {"limit": limit}
        res = self._transport.request(
            "GET",
            f"/api/conversations/{conversation_id}/messages",
            params=params,
        )
        return [ConversationMessage.model_validate(m) for m in res]

    def extract_memory(
        self,
        conversation_id: str,
        *,
        message_ids: list[str] | None = None,
    ) -> ConversationExtractResponse:
        payload = {"message_ids": message_ids} if message_ids else {}
        res = self._transport.request(
            "POST",
            f"/api/conversations/{conversation_id}/extract-memory",
            json=payload,
        )
        return ConversationExtractResponse.model_validate(res)

    def confirm_memory(
        self,
        conversation_id: str,
        *,
        candidate: ConversationConfirmCandidate | dict[str, Any],
        user_edits: CandidateUserEdits | dict[str, Any] | None = None,
    ) -> Memory:
        cand_dict = candidate.model_dump() if isinstance(candidate, ConversationConfirmCandidate) else candidate
        edits_dict = (
            user_edits.model_dump() if isinstance(user_edits, CandidateUserEdits) else user_edits
        )
        payload = {
            "candidate": cand_dict,
            "user_edits": edits_dict,
        }
        res = self._transport.request(
            "POST",
            f"/api/conversations/{conversation_id}/confirm-memory",
            json=payload,
        )
        return Memory.model_validate(res)

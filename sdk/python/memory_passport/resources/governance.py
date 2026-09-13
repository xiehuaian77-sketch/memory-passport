"""Governance resource client."""

from __future__ import annotations

from memory_passport.models.governance import UserMemoryPolicy
from memory_passport.transport import MemoryPassportTransport


class GovernanceResource:
    """Resource client for memory governance policy endpoints."""

    def __init__(self, transport: MemoryPassportTransport) -> None:
        self._transport = transport

    def get_policy(self) -> UserMemoryPolicy:
        res = self._transport.request("GET", "/api/memories/policy")
        return UserMemoryPolicy.model_validate(res)

    def update_policy(
        self,
        *,
        memory_enabled: bool | None = None,
        require_confirmation: bool | None = None,
        allow_memory_retrieval: bool | None = None,
        allow_ai_extraction: bool | None = None,
    ) -> UserMemoryPolicy:
        payload = {}
        if memory_enabled is not None:
            payload["memory_enabled"] = memory_enabled
        if require_confirmation is not None:
            payload["require_confirmation"] = require_confirmation
        if allow_memory_retrieval is not None:
            payload["allow_memory_retrieval"] = allow_memory_retrieval
        if allow_ai_extraction is not None:
            payload["allow_ai_extraction"] = allow_ai_extraction

        res = self._transport.request("PUT", "/api/memories/policy", json=payload)
        return UserMemoryPolicy.model_validate(res)

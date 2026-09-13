"""Lifecycle resource client (archive, restore, supersede)."""

from __future__ import annotations

from datetime import datetime

from memory_passport.models.memories import Memory
from memory_passport.transport import MemoryPassportTransport


class LifecycleResource:
    """Resource client for memory lifecycle operations."""

    def __init__(self, transport: MemoryPassportTransport) -> None:
        self._transport = transport

    def archive(self, memory_id: str) -> Memory:
        res = self._transport.request("POST", f"/api/memories/{memory_id}/archive")
        return Memory.model_validate(res)

    def restore(self, memory_id: str) -> Memory:
        res = self._transport.request("POST", f"/api/memories/{memory_id}/restore")
        return Memory.model_validate(res)

    def supersede(
        self,
        memory_id: str,
        replacement_memory_id: str,
        *,
        valid_until: datetime | None = None,
    ) -> Memory:
        payload = {
            "replacement_memory_id": replacement_memory_id,
            "valid_until": valid_until.isoformat() if valid_until else None,
        }
        res = self._transport.request(
            "POST",
            f"/api/memories/{memory_id}/supersede",
            json=payload,
        )
        return Memory.model_validate(res)

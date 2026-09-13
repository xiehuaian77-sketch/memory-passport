"""Conflicts resource client."""

from __future__ import annotations

from memory_passport.models.common import MemoryType
from memory_passport.models.conflicts import ConflictDetectionResponse
from memory_passport.transport import MemoryPassportTransport


class ConflictsResource:
    """Resource client for /api/memories/detect-conflicts."""

    def __init__(self, transport: MemoryPassportTransport) -> None:
        self._transport = transport

    def detect(
        self,
        *,
        key: str,
        content: str,
        memory_type: str | MemoryType = MemoryType.PREFERENCE,
    ) -> ConflictDetectionResponse:
        m_type = memory_type.value if isinstance(memory_type, MemoryType) else memory_type
        payload = {
            "key": key,
            "content": content,
            "memory_type": m_type,
        }
        res = self._transport.request("POST", "/api/memories/detect-conflicts", json=payload)
        return ConflictDetectionResponse.model_validate(res)

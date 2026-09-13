"""Audit and explainability resource client."""

from __future__ import annotations

from memory_passport.models.audit import MemoryAuditLog, MemoryExplainResponse
from memory_passport.transport import MemoryPassportTransport


class AuditResource:
    """Resource client for memory explanation and history."""

    def __init__(self, transport: MemoryPassportTransport) -> None:
        self._transport = transport

    def explain(self, memory_id: str) -> MemoryExplainResponse:
        res = self._transport.request("GET", f"/api/memories/{memory_id}/explain")
        return MemoryExplainResponse.model_validate(res)

    def history(self, memory_id: str) -> list[MemoryAuditLog]:
        res = self._transport.request("GET", f"/api/memories/{memory_id}/history")
        logs = res.get("history", []) if isinstance(res, dict) else res
        return [MemoryAuditLog.model_validate(log) for log in logs]

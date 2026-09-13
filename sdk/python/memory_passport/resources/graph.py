"""Graph relationships resource client."""

from __future__ import annotations

from datetime import datetime

from memory_passport.models.common import DirectionType, RelationshipType, TemporalMode
from memory_passport.models.graph import MemoryRelationship, RelatedMemory
from memory_passport.transport import MemoryPassportTransport


class GraphResource:
    """Resource client for Memory Relationships API."""

    def __init__(self, transport: MemoryPassportTransport) -> None:
        self._transport = transport

    def create_relationship(
        self,
        source_memory_id: str,
        target_memory_id: str,
        relationship_type: str | RelationshipType,
        *,
        confidence: float = 1.0,
    ) -> MemoryRelationship:
        r_type = (
            relationship_type.value
            if isinstance(relationship_type, RelationshipType)
            else relationship_type
        )
        payload = {
            "source_memory_id": source_memory_id,
            "target_memory_id": target_memory_id,
            "relationship_type": r_type,
            "confidence": confidence,
        }
        res = self._transport.request(
            "POST",
            f"/api/memories/{source_memory_id}/relationships",
            json=payload,
        )
        return MemoryRelationship.model_validate(res)

    def list_relationships(
        self,
        memory_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[MemoryRelationship]:
        params = {"offset": offset, "limit": limit}
        res = self._transport.request(
            "GET",
            f"/api/memories/{memory_id}/relationships",
            params=params,
        )
        return [MemoryRelationship.model_validate(r) for r in res]

    def related(
        self,
        memory_id: str,
        *,
        direction: str | DirectionType = DirectionType.BOTH,
        relationship_type: str | RelationshipType | None = None,
        confidence_min: float | None = None,
        temporal_mode: str | TemporalMode = TemporalMode.CURRENT,
        reference_time: datetime | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[RelatedMemory]:
        d_val = direction.value if isinstance(direction, DirectionType) else direction
        r_type = (
            relationship_type.value
            if isinstance(relationship_type, RelationshipType)
            else relationship_type
        )
        t_mode = (
            temporal_mode.value
            if isinstance(temporal_mode, TemporalMode)
            else temporal_mode
        )

        params = {
            "direction": d_val,
            "relationship_type": r_type,
            "confidence_min": confidence_min,
            "temporal_mode": t_mode,
            "reference_time": reference_time.isoformat() if reference_time else None,
            "offset": offset,
            "limit": limit,
        }
        res = self._transport.request(
            "GET",
            f"/api/memories/{memory_id}/related",
            params=params,
        )
        return [RelatedMemory.model_validate(r) for r in res]

    def delete_relationship(self, memory_id: str, relationship_id: str) -> None:
        self._transport.request(
            "DELETE",
            f"/api/memories/{memory_id}/relationships/{relationship_id}",
        )

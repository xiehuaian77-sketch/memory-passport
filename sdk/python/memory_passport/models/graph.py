"""Graph relationship and one-hop related models."""

from __future__ import annotations

from datetime import datetime
from memory_passport.models.common import BaseSDKModel, RelationshipType


class MemoryRelationship(BaseSDKModel):
    id: str
    user_id: str
    source_memory_id: str
    target_memory_id: str
    relationship_type: RelationshipType | str
    confidence: float
    created_at: datetime | str
    updated_at: datetime | str


class RelatedMemory(BaseSDKModel):
    id: str
    memory_id: str
    user_id: str
    content: str
    memory_type: str = "fact"
    category: str = "fact"
    status: str = "active"
    importance: float = 0.5
    confidence: float = 1.0
    relationship_type: RelationshipType | str
    relationship_confidence: float
    relationship_id: str
    direction: str
    created_at: datetime | str

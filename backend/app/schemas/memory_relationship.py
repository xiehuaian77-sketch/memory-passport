"""Pydantic schemas for MemoryRelationship CRUD operations.

These schemas are used by FastAPI endpoints and service layer for request validation
and response serialization.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, validator

class RelationshipType(str, Enum):
    UPDATES = "UPDATES"
    SUPERSEDES = "SUPERSEDES"
    CONTRADICTS = "CONTRADICTS"
    RELEVANT_TO = "RELEVANT_TO"
    # Extend as needed.

class MemoryRelationshipCreate(BaseModel):
    source_memory_id: str = Field(..., description="ID of the source memory")
    target_memory_id: str = Field(..., description="ID of the target memory")
    relationship_type: RelationshipType = Field(..., description="Type of relationship")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence score (0.0‑1.0)")

    @validator("confidence")
    def round_confidence(cls, v):
        return round(v, 4)

class MemoryRelationshipOut(BaseModel):
    id: str
    user_id: str
    source_memory_id: str
    target_memory_id: str
    relationship_type: RelationshipType
    confidence: float
    created_at: datetime | str
    updated_at: datetime | str

    class Config:
        from_attributes = True


class DirectionType(str, Enum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"
    BOTH = "both"


class TemporalMode(str, Enum):
    CURRENT = "current"
    HISTORICAL = "historical"
    ANY = "any"


class RelatedMemoryOut(BaseModel):
    """Schema representing a related memory and its connecting edge."""
    id: str
    memory_id: str
    user_id: str
    content: str
    memory_type: str = "fact"
    category: str = "fact"
    status: str = "active"
    importance: float = 0.5
    confidence: float = 1.0
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    superseded_by_memory_id: str | None = None

    # Relationship edge metadata
    relationship_id: str
    relationship_type: RelationshipType
    relationship_confidence: float
    direction: str  # "outgoing" | "incoming"

    class Config:
        from_attributes = True

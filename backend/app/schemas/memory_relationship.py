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

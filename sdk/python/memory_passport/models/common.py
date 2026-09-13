"""Common models, base configurations, and enums for Memory Passport SDK."""

from __future__ import annotations

from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class BaseSDKModel(BaseModel):
    """Base Pydantic model for all SDK data structures with forward compatibility."""

    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        from_attributes=True,
    )


class MemoryType(str, Enum):
    PREFERENCE = "preference"
    IDENTITY = "identity"
    TASK = "task"
    CONTEXT = "context"


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    CONFLICTED = "conflicted"
    SUPERSEDED = "superseded"


class TemporalMode(str, Enum):
    CURRENT = "current"
    HISTORICAL = "historical"
    ANY = "any"


class RelationshipType(str, Enum):
    UPDATES = "UPDATES"
    SUPERSEDES = "SUPERSEDES"
    CONTRADICTS = "CONTRADICTS"
    RELEVANT_TO = "RELEVANT_TO"


class DirectionType(str, Enum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"
    BOTH = "both"


class SearchMode(str, Enum):
    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


class SyncPage(BaseSDKModel, Generic[T]):
    """Generic container for paginated list responses."""

    items: list[T]
    offset: int
    limit: int
    total: int | None = None

    @property
    def has_more(self) -> bool:
        if self.total is not None:
            return (self.offset + len(self.items)) < self.total
        return len(self.items) >= self.limit

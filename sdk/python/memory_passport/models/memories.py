"""Memory data models."""

from __future__ import annotations

from datetime import datetime

from memory_passport.models.common import BaseSDKModel, MemoryStatus, MemoryType


class Memory(BaseSDKModel):
    """Memory entity representation matching server response."""

    id: str
    user_id: str
    key: str
    content: str
    category: str | None = None
    source: str = "manual"
    confidence: float = 1.0
    importance: float = 0.5
    is_shared: bool = True
    tags: str = ""
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    status: str = MemoryStatus.ACTIVE.value
    version: int = 1
    source_conversation_id: str | None = None
    source_message_id: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    superseded_by_memory_id: str | None = None

    @property
    def memory_type(self) -> str:
        """Alias category to memory_type for unified domain terminology."""
        return self.category or "preference"

    @property
    def tag_list(self) -> list[str]:
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]


class MemoryCreateInput(BaseSDKModel):
    key: str
    content: str
    memory_type: str | MemoryType = MemoryType.PREFERENCE
    source: str = "manual"
    confidence: float = 1.0
    importance: float = 0.5
    is_shared: bool = True
    tags: str = ""
    status: str = MemoryStatus.ACTIVE.value
    source_conversation_id: str | None = None
    source_message_id: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    superseded_by_memory_id: str | None = None


class MemoryUpdateInput(BaseSDKModel):
    key: str | None = None
    content: str | None = None
    memory_type: str | MemoryType | None = None
    confidence: float | None = None
    is_shared: bool | None = None
    tags: str | None = None
    status: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    superseded_by_memory_id: str | None = None


class MemoryExport(BaseSDKModel):
    memories: list[Memory]
    exported_at: datetime
    passport_id: str


class MemoryImportItem(BaseSDKModel):
    category: str
    key: str
    content: str
    confidence: float = 0.8
    tags: str = ""

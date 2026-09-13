"""Memories resource client."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

from memory_passport.models.common import MemoryStatus, MemoryType, SyncPage
from memory_passport.models.memories import (
    Memory,
    MemoryExport,
    MemoryImportItem,
)
from memory_passport.pagination import Paginator
from memory_passport.transport import MemoryPassportTransport


class MemoriesResource:
    """Resource client for /api/memories endpoints."""

    def __init__(self, transport: MemoryPassportTransport) -> None:
        self._transport = transport

    def create(
        self,
        *,
        key: str,
        content: str,
        memory_type: str | MemoryType = MemoryType.PREFERENCE,
        confidence: float = 1.0,
        importance: float = 0.5,
        is_shared: bool = True,
        tags: str | list[str] = "",
        status: str | MemoryStatus = MemoryStatus.ACTIVE,
        source_conversation_id: str | None = None,
        source_message_id: str | None = None,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        superseded_by_memory_id: str | None = None,
    ) -> Memory:
        tag_str = tags if isinstance(tags, str) else ",".join(tags)
        m_type = memory_type.value if isinstance(memory_type, MemoryType) else memory_type
        m_status = status.value if isinstance(status, MemoryStatus) else status

        payload = {
            "key": key,
            "content": content,
            "memory_type": m_type,
            "category": m_type,
            "confidence": confidence,
            "importance": importance,
            "is_shared": is_shared,
            "tags": tag_str,
            "status": m_status,
            "source_conversation_id": source_conversation_id,
            "source_message_id": source_message_id,
            "valid_from": valid_from.isoformat() if valid_from else None,
            "valid_until": valid_until.isoformat() if valid_until else None,
            "superseded_by_memory_id": superseded_by_memory_id,
        }
        res = self._transport.request("POST", "/api/memories", json=payload)
        return Memory.model_validate(res)

    def get(self, memory_id: str) -> Memory:
        res = self._transport.request("GET", f"/api/memories/{memory_id}")
        return Memory.model_validate(res)

    def list(
        self,
        *,
        category: str | None = None,
        memory_type: str | None = None,
        source: str | None = None,
        status: str | MemoryStatus | None = "active",
        offset: int = 0,
        limit: int = 100,
    ) -> SyncPage[Memory]:
        m_status = status.value if isinstance(status, MemoryStatus) else status
        params = {
            "category": category,
            "memory_type": memory_type,
            "source": source,
            "status": m_status,
            "offset": offset,
            "limit": limit,
        }
        res = self._transport.request("GET", "/api/memories", params=params)
        items = [Memory.model_validate(m) for m in res]
        return SyncPage(items=items, offset=offset, limit=limit, total=None)

    def iter(
        self,
        *,
        category: str | None = None,
        memory_type: str | None = None,
        source: str | None = None,
        status: str | MemoryStatus | None = "active",
        page_size: int = 50,
        max_items: int | None = None,
    ) -> Iterator[Memory]:
        def fetcher(offset: int, limit: int) -> SyncPage[Memory]:
            return self.list(
                category=category,
                memory_type=memory_type,
                source=source,
                status=status,
                offset=offset,
                limit=limit,
            )

        return iter(Paginator(fetcher, page_size=page_size, max_items=max_items))

    def update(
        self,
        memory_id: str,
        *,
        key: str | None = None,
        content: str | None = None,
        memory_type: str | MemoryType | None = None,
        confidence: float | None = None,
        is_shared: bool | None = None,
        tags: str | list[str] | None = None,
        status: str | MemoryStatus | None = None,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        superseded_by_memory_id: str | None = None,
    ) -> Memory:
        tag_str = (
            (tags if isinstance(tags, str) else ",".join(tags))
            if tags is not None
            else None
        )
        m_type = (
            (memory_type.value if isinstance(memory_type, MemoryType) else memory_type)
            if memory_type is not None
            else None
        )
        m_status = (
            (status.value if isinstance(status, MemoryStatus) else status)
            if status is not None
            else None
        )

        payload: dict[str, Any] = {}
        if key is not None:
            payload["key"] = key
        if content is not None:
            payload["content"] = content
        if m_type is not None:
            payload["category"] = m_type
        if confidence is not None:
            payload["confidence"] = confidence
        if is_shared is not None:
            payload["is_shared"] = is_shared
        if tag_str is not None:
            payload["tags"] = tag_str
        if m_status is not None:
            payload["status"] = m_status
        if valid_from is not None:
            payload["valid_from"] = valid_from.isoformat()
        if valid_until is not None:
            payload["valid_until"] = valid_until.isoformat()
        if superseded_by_memory_id is not None:
            payload["superseded_by_memory_id"] = superseded_by_memory_id

        res = self._transport.request("PUT", f"/api/memories/{memory_id}", json=payload)
        return Memory.model_validate(res)

    def delete(self, memory_id: str) -> None:
        self._transport.request("DELETE", f"/api/memories/{memory_id}")

    def export(self) -> MemoryExport:
        res = self._transport.request("GET", "/api/memories/export/all")
        return MemoryExport.model_validate(res)

    def import_batch(self, items: list[MemoryImportItem | dict[str, Any]]) -> list[Memory]:
        clean_items = [
            item.model_dump() if isinstance(item, MemoryImportItem) else item
            for item in items
        ]
        res = self._transport.request("POST", "/api/memories/import/batch", json=clean_items)
        return [Memory.model_validate(m) for m in res]

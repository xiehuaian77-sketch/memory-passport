"""Tests for memories resource operations."""

import json
from memory_passport.models import MemoryStatus, MemoryType


def test_memory_create(mock_handler, mock_client):
    mock_handler.register("POST", "/api/memories", status_code=201, json_data={
        "id": "mem-123",
        "user_id": "usr-1",
        "key": "pref_theme",
        "content": "User prefers dark mode",
        "category": "preference",
        "source": "manual",
        "confidence": 0.95,
        "importance": 0.8,
        "is_shared": True,
        "tags": "ui,theme",
        "created_at": "2026-01-01T12:00:00Z",
        "updated_at": "2026-01-01T12:00:00Z",
        "status": "active",
        "unknown_server_extra_field": "ignore_safely",
    })

    mem = mock_client.memories.create(
        key="pref_theme",
        content="User prefers dark mode",
        memory_type=MemoryType.PREFERENCE,
        confidence=0.95,
        importance=0.8,
        tags=["ui", "theme"],
    )

    assert mem.id == "mem-123"
    assert mem.content == "User prefers dark mode"
    assert mem.memory_type == "preference"
    assert mem.tag_list == ["ui", "theme"]

    req = mock_handler.requests[0]
    body = json.loads(req.content)
    assert body["key"] == "pref_theme"
    assert body["tags"] == "ui,theme"


def test_memory_get(mock_handler, mock_client):
    mock_handler.register("GET", "/api/memories/mem-123", status_code=200, json_data={
        "id": "mem-123",
        "user_id": "usr-1",
        "key": "pref_theme",
        "content": "User prefers dark mode",
        "created_at": "2026-01-01T12:00:00Z",
        "updated_at": "2026-01-01T12:00:00Z",
    })
    mem = mock_client.memories.get("mem-123")
    assert mem.id == "mem-123"


def test_memory_list_filtering(mock_handler, mock_client):
    mock_handler.register("GET", "/api/memories", status_code=200, json_data=[
        {
            "id": "mem-1",
            "user_id": "usr-1",
            "key": "k1",
            "content": "c1",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    ])
    page = mock_client.memories.list(status=MemoryStatus.ACTIVE, offset=10, limit=25)
    assert len(page.items) == 1
    req = mock_handler.requests[0]
    assert "offset=10" in str(req.url)
    assert "limit=25" in str(req.url)
    assert "status=active" in str(req.url)


def test_memory_update(mock_handler, mock_client):
    mock_handler.register("PUT", "/api/memories/mem-123", status_code=200, json_data={
        "id": "mem-123",
        "user_id": "usr-1",
        "key": "k1",
        "content": "updated content",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T01:00:00Z",
    })
    updated = mock_client.memories.update("mem-123", content="updated content")
    assert updated.content == "updated content"


def test_memory_delete(mock_handler, mock_client):
    mock_handler.register("DELETE", "/api/memories/mem-123", status_code=204)
    mock_client.memories.delete("mem-123")
    assert mock_handler.requests[0].method == "DELETE"


def test_memory_export_and_import(mock_handler, mock_client):
    mock_handler.register("GET", "/api/memories/export/all", status_code=200, json_data={
        "memories": [
            {
                "id": "mem-1",
                "user_id": "u1",
                "key": "k1",
                "content": "c1",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ],
        "exported_at": "2026-01-01T00:00:00Z",
        "passport_id": "pass-123",
    })
    export_data = mock_client.memories.export()
    assert len(export_data.memories) == 1
    assert export_data.passport_id == "pass-123"

    mock_handler.register("POST", "/api/memories/import/batch", status_code=201, json_data=[
        {
            "id": "mem-new",
            "user_id": "u1",
            "key": "k2",
            "content": "c2",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    ])
    imported = mock_client.memories.import_batch([
        {"category": "task", "key": "k2", "content": "c2"}
    ])
    assert len(imported) == 1
    assert imported[0].id == "mem-new"

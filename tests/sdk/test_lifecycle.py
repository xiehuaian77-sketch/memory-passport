"""Tests for lifecycle resources."""

import json
from datetime import datetime, timezone

from memory_passport.models import MemoryStatus


def test_archive_and_restore(mock_handler, mock_client):
    mock_handler.register("POST", "/api/memories/mem-1/archive", status_code=200, json_data={
        "id": "mem-1",
        "user_id": "u1",
        "key": "k",
        "content": "c",
        "status": "archived",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    })
    archived = mock_client.lifecycle.archive("mem-1")
    assert archived.status == MemoryStatus.ARCHIVED.value

    mock_handler.register("POST", "/api/memories/mem-1/restore", status_code=200, json_data={
        "id": "mem-1",
        "user_id": "u1",
        "key": "k",
        "content": "c",
        "status": "active",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    })
    restored = mock_client.lifecycle.restore("mem-1")
    assert restored.status == MemoryStatus.ACTIVE.value


def test_supersede(mock_handler, mock_client):
    mock_handler.register("POST", "/api/memories/mem-old/supersede", status_code=200, json_data={
        "id": "mem-old",
        "user_id": "u1",
        "key": "k",
        "content": "c",
        "status": "superseded",
        "superseded_by_memory_id": "mem-new",
        "valid_until": "2026-05-01T00:00:00Z",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-05-01T00:00:00Z",
    })

    valid_until = datetime(2026, 5, 1, tzinfo=timezone.utc)
    res = mock_client.lifecycle.supersede(
        "mem-old",
        replacement_memory_id="mem-new",
        valid_until=valid_until,
    )
    assert res.status == MemoryStatus.SUPERSEDED.value
    assert res.superseded_by_memory_id == "mem-new"

    req = mock_handler.requests[0]
    body = json.loads(req.content)
    assert body["replacement_memory_id"] == "mem-new"
    assert "2026-05-01" in body["valid_until"]

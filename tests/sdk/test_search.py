"""Tests for search and retrieval resources, including graph-aware retrieval."""

import json
from datetime import datetime, timezone

from memory_passport.models import TemporalMode


def test_semantic_search(mock_handler, mock_client):
    mock_handler.register("POST", "/api/memories/search", status_code=200, json_data={
        "items": [
            {
                "id": "mem-1",
                "content": "Python is fast to write",
                "memory_type": "preference",
                "importance": 0.8,
                "confidence": 0.9,
                "similarity": 0.87,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ],
        "query": "python preference",
        "limit": 5,
        "search_mode": "semantic",
    })
    res = mock_client.search.semantic("python preference", limit=5)
    assert res.search_mode == "semantic"
    assert len(res.items) == 1
    assert res.items[0].similarity == 0.87


def test_keyword_search(mock_handler, mock_client):
    mock_handler.register("POST", "/api/memories/search", status_code=200, json_data={
        "items": [],
        "query": "test keyword",
        "limit": 10,
        "search_mode": "keyword",
    })
    res = mock_client.search.keyword("test keyword")
    assert res.search_mode == "keyword"


def test_hybrid_search(mock_handler, mock_client):
    mock_handler.register("POST", "/api/memories/hybrid-search", status_code=200, json_data={
        "items": [
            {
                "id": "mem-2",
                "content": "TypeScript for web frontends",
                "memory_type": "preference",
                "importance": 0.7,
                "confidence": 1.0,
                "hybrid_score": 0.92,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ],
        "query": "web framework",
        "limit": 5,
        "search_mode": "hybrid",
    })
    res = mock_client.search.hybrid("web framework", limit=5)
    assert res.items[0].hybrid_score == 0.92


def test_retrieve_with_graph_aware_parameters(mock_handler, mock_client):
    mock_handler.register("POST", "/api/memories/retrieve", status_code=200, json_data={
        "items": [
            {
                "id": "mem-1",
                "memory_type": "preference",
                "content": "User prefers FastAPI",
                "source": "manual",
                "importance": 0.8,
                "confidence": 1.0,
                "retrieval_score": 0.88,
                "hybrid_score": 0.85,
                "is_truncated": False,
                "original_char_count": 20,
            }
        ],
        "total_memories": 1,
        "total_chars": 20,
        "max_context_chars": 3000,
        "max_content_chars": 500,
    })

    ref_time = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    ctx = mock_client.search.retrieve(
        query="backend frameworks",
        graph_enabled=True,
        graph_seed_limit=4,
        graph_max_expanded=12,
        temporal_mode=TemporalMode.CURRENT,
        reference_time=ref_time,
    )

    assert ctx.total_memories == 1
    assert "FastAPI" in ctx.format_text()

    req = mock_handler.requests[0]
    body = json.loads(req.content)
    assert body["graph_enabled"] is True
    assert body["graph_seed_limit"] == 4
    assert body["graph_max_expanded"] == 12
    assert body["temporal_mode"] == "current"
    assert "2026-06-01T12:00:00" in body["reference_time"]

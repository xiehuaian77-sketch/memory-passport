"""Tests for graph relationship resources."""

from datetime import datetime, timezone
from memory_passport.models import DirectionType, RelationshipType, TemporalMode


def test_create_relationship(mock_handler, mock_client):
    mock_handler.register("POST", "/api/memories/mem-1/relationships", status_code=201, json_data={
        "id": "rel-1",
        "user_id": "usr-1",
        "source_memory_id": "mem-1",
        "target_memory_id": "mem-2",
        "relationship_type": "RELEVANT_TO",
        "confidence": 0.9,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    })

    rel = mock_client.graph.create_relationship(
        source_memory_id="mem-1",
        target_memory_id="mem-2",
        relationship_type=RelationshipType.RELEVANT_TO,
        confidence=0.9,
    )

    assert rel.id == "rel-1"
    assert rel.relationship_type == RelationshipType.RELEVANT_TO


def test_list_relationships(mock_handler, mock_client):
    mock_handler.register("GET", "/api/memories/mem-1/relationships", status_code=200, json_data=[
        {
            "id": "rel-1",
            "user_id": "usr-1",
            "source_memory_id": "mem-1",
            "target_memory_id": "mem-2",
            "relationship_type": "UPDATES",
            "confidence": 1.0,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    ])
    rels = mock_client.graph.list_relationships("mem-1", offset=0, limit=50)
    assert len(rels) == 1
    assert rels[0].source_memory_id == "mem-1"


def test_related_memories(mock_handler, mock_client):
    mock_handler.register("GET", "/api/memories/mem-1/related", status_code=200, json_data=[
        {
            "id": "rel-1",
            "memory_id": "mem-2",
            "user_id": "usr-1",
            "content": "Target related content",
            "relationship_type": "RELEVANT_TO",
            "relationship_confidence": 0.85,
            "relationship_id": "rel-1",
            "direction": "outgoing",
            "created_at": "2026-01-01T00:00:00Z",
        }
    ])

    ref_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    related = mock_client.graph.related(
        "mem-1",
        direction=DirectionType.OUTGOING,
        temporal_mode=TemporalMode.CURRENT,
        reference_time=ref_time,
    )
    assert len(related) == 1
    assert related[0].memory_id == "mem-2"


def test_delete_relationship(mock_handler, mock_client):
    mock_handler.register("DELETE", "/api/memories/mem-1/relationships/rel-1", status_code=204)
    mock_client.graph.delete_relationship("mem-1", "rel-1")
    assert mock_handler.requests[0].method == "DELETE"

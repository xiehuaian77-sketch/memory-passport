"""Tests for conflicts, governance, and audit resources."""

def test_detect_conflicts(mock_handler, mock_client):
    mock_handler.register("POST", "/api/memories/detect-conflicts", status_code=200, json_data={
        "has_conflict": True,
        "conflicts": [
            {
                "existing_memory_id": "mem-old",
                "existing_key": "lang",
                "existing_content": "User prefers Java",
                "conflict_type": "semantic_conflict",
                "recommendation": "supersede",
                "classification": "CONTRADICTION",
                "conflict_score": 0.9,
                "confidence": 0.95,
                "user_reason": "Java contradicts Python preference",
            }
        ],
    })

    res = mock_client.conflicts.detect(key="lang", content="User prefers Python")
    assert res.has_conflict is True
    assert len(res.conflicts) == 1
    assert res.conflicts[0].recommendation == "supersede"


def test_governance_policy(mock_handler, mock_client):
    mock_handler.register("GET", "/api/memories/policy", status_code=200, json_data={
        "user_id": "usr-1",
        "memory_enabled": True,
        "require_confirmation": True,
        "allow_memory_retrieval": True,
        "allow_ai_extraction": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    })
    pol = mock_client.governance.get_policy()
    assert pol.require_confirmation is True

    mock_handler.register("PUT", "/api/memories/policy", status_code=200, json_data={
        "user_id": "usr-1",
        "memory_enabled": False,
        "require_confirmation": False,
        "allow_memory_retrieval": False,
        "allow_ai_extraction": False,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T01:00:00Z",
    })
    updated = mock_client.governance.update_policy(memory_enabled=False)
    assert updated.memory_enabled is False


def test_audit_explain_and_history(mock_handler, mock_client):
    mock_handler.register("GET", "/api/memories/mem-1/explain", status_code=200, json_data={
        "memory_id": "mem-1",
        "key": "test_k",
        "memory_type": "preference",
        "content": "test_c",
        "status": "active",
        "version": 2,
        "source": "manual",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "is_active": True,
        "has_conflicts": False,
        "active_conflicts_count": 0,
        "total_revisions": 2,
    })
    exp = mock_client.audit.explain("mem-1")
    assert exp.memory_id == "mem-1"
    assert exp.version == 2

    mock_handler.register("GET", "/api/memories/mem-1/history", status_code=200, json_data={
        "history": [
            {
                "id": "log-1",
                "memory_id": "mem-1",
                "user_id": "u1",
                "actor_type": "user",
                "actor_id": "u1",
                "action": "create",
                "from_version": None,
                "to_version": 1,
                "created_at": "2026-01-01T00:00:00Z",
            }
        ]
    })
    history = mock_client.audit.history("mem-1")
    assert len(history) == 1
    assert history[0].action == "create"

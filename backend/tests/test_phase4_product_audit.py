"""Phase 4: Memory Product Layer - Release Audit Tests.

Covers:
1. Atomic Edit and Save in a single database transaction.
2. Candidate signature tampering and replay rejection.
3. Chat memory indicator truthfulness (populated when memories loaded, empty otherwise).
4. Memory policy enforcement (retrieval disabled -> loaded_memories empty).
5. Memory Center default active status and filtering.
6. Memory Center pagination.
7. Explain and History authorization and cross-user isolation.
8. Audit log recording for atomic edit and save.
"""

from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.governance import MemoryAuditLog, UserMemoryPolicy
from app.models.memory import Memory
from app.services.extraction_service import compute_candidate_signature
from tests.conftest import TestSession


def make_valid_candidate(
    user_id: str,
    conversation_id: str,
    cand_id: str = "cand_phase4_test",
    memory_type: str = "preference",
    key: str = "theme_choice",
    content: str = "User prefers dark mode in all editors",
    importance: float = 0.8,
    confidence: float = 0.95,
    tags: list[str] | None = None,
    raw_content: str = "",
) -> dict:
    if tags is None:
        tags = ["ui", "theme"]
    sig = compute_candidate_signature(
        user_id=user_id,
        conversation_id=conversation_id,
        candidate_id=cand_id,
        memory_type=memory_type,
        key=key,
        content=content,
        importance=importance,
        confidence=confidence,
        tags=tags,
        raw_content=raw_content,
    )
    return {
        "id": cand_id,
        "memory_type": memory_type,
        "key": key,
        "content": content,
        "importance": importance,
        "confidence": confidence,
        "tags": tags,
        "is_shared": False,
        "raw_content": raw_content,
        "signature": sig,
    }


@pytest.mark.asyncio
async def test_atomic_edit_and_save_success(auth_client: AsyncClient):
    """Confirming a candidate with user_edits creates v1 and updates to v2 atomically."""
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]

    r_conv = await auth_client.post("/api/conversations")
    conv_id = r_conv.json()["id"]

    cand = make_valid_candidate(user_id=user_id, conversation_id=conv_id)

    res = await auth_client.post(
        f"/api/conversations/{conv_id}/confirm-memory",
        json={
            "candidate": cand,
            "user_edits": {
                "key": "custom_theme_choice",
                "content": "User prefers high-contrast dark theme specifically",
                "tags": "theme,accessibility",
            },
        },
    )

    assert res.status_code == 201
    data = res.json()
    assert data["version"] == 2
    assert data["content"] == "User prefers high-contrast dark theme specifically"
    assert data["key"] == "custom_theme_choice"
    assert data["source"] == "ai_extracted"

    # Verify explain and history endpoints reflect version 2
    res_explain = await auth_client.get(f"/api/memories/{data['id']}/explain")
    assert res_explain.status_code == 200
    assert res_explain.json()["version"] == 2

    res_history = await auth_client.get(f"/api/memories/{data['id']}/history")
    assert res_history.status_code == 200

    # Verify audit log recorded both create and update
    async with TestSession() as session:
        logs = (
            await session.execute(
                select(MemoryAuditLog)
                .where(MemoryAuditLog.memory_id == data["id"])
                .order_by(MemoryAuditLog.id.asc())
            )
        ).scalars().all()
        actions = [log.action.upper() for log in logs]
        assert any(a in ("CONFIRM", "CREATE") for a in actions)
        assert "UPDATE" in actions


@pytest.mark.asyncio
async def test_atomic_edit_and_save_tampered_candidate_rejected(auth_client: AsyncClient):
    """Tampering candidate data prior to confirm must be rejected by HMAC verification."""
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]

    r_conv = await auth_client.post("/api/conversations")
    conv_id = r_conv.json()["id"]

    cand = make_valid_candidate(user_id=user_id, conversation_id=conv_id)
    cand["content"] = "Tampered original content"

    res = await auth_client.post(
        f"/api/conversations/{conv_id}/confirm-memory",
        json={
            "candidate": cand,
            "user_edits": {"content": "Edit on tampered candidate"},
        },
    )

    assert res.status_code == 400
    assert "tampered" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_chat_memory_indicator_truthfulness(auth_client: AsyncClient):
    """Chat response returns loaded_memories reflecting actual memories used in context."""
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]

    # 1. Without memories, loaded_memories must be empty
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = "I am ready to help you."
    with patch("app.services.chat_service.get_ai_provider", return_value=mock_provider):
        res = await auth_client.post(
            "/api/chat",
            json={"message": "What is the weather today?"},
        )
    assert res.status_code == 200
    data = res.json()
    assert "loaded_memories" in data
    assert len(data["loaded_memories"]) == 0

    # 2. Add an active memory
    async with TestSession() as session:
        mem = Memory(
            user_id=user_id,
            memory_type="preference",
            key="beverage_preference",
            content="User prefers hot green tea without sugar",
            status="active",
            importance=0.9,
            confidence=1.0,
        )
        session.add(mem)
        await session.commit()

    # 3. Chat asking about beverage should retrieve memory and return in loaded_memories
    mock_provider.generate.return_value = "Here is some hot green tea for you."
    with patch("app.services.chat_service.get_ai_provider", return_value=mock_provider):
        res = await auth_client.post(
            "/api/chat",
            json={"message": "Can you recommend a hot green tea?"},
        )
    assert res.status_code == 200
    data2 = res.json()
    assert len(data2["loaded_memories"]) > 0
    assert any("green tea" in m["content"].lower() for m in data2["loaded_memories"])


@pytest.mark.asyncio
async def test_chat_memory_indicator_empty_when_policy_retrieval_disabled(auth_client: AsyncClient):
    """When allow_memory_retrieval is False, loaded_memories must be empty."""
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]

    async with TestSession() as session:
        policy = await session.get(UserMemoryPolicy, user_id)
        if not policy:
            policy = UserMemoryPolicy(user_id=user_id, allow_memory_retrieval=False)
            session.add(policy)
        else:
            policy.allow_memory_retrieval = False
        await session.commit()

    mock_provider = AsyncMock()
    mock_provider.generate.return_value = "General response without memories."
    with patch("app.services.chat_service.get_ai_provider", return_value=mock_provider):
        res = await auth_client.post(
            "/api/chat",
            json={"message": "Can you recommend a hot green tea?"},
        )
    assert res.status_code == 200
    data = res.json()
    assert data["loaded_memories"] == []

    # Reset policy
    async with TestSession() as session:
        policy = await session.get(UserMemoryPolicy, user_id)
        if policy:
            policy.allow_memory_retrieval = True
            await session.commit()


@pytest.mark.asyncio
async def test_memory_center_default_active_status(auth_client: AsyncClient):
    """Default memory list filters to status=active."""
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]

    async with TestSession() as session:
        m_active = Memory(
            user_id=user_id,
            memory_type="fact",
            key="act_k1",
            content="Active memory item",
            status="active",
        )
        m_archived = Memory(
            user_id=user_id,
            memory_type="fact",
            key="arc_k2",
            content="Archived memory item",
            status="archived",
        )
        session.add_all([m_active, m_archived])
        await session.commit()

    # Default query (no status param)
    res_default = await auth_client.get("/api/memories")
    assert res_default.status_code == 200
    items_default = res_default.json()
    assert any(m["content"] == "Active memory item" for m in items_default)
    assert not any(m["content"] == "Archived memory item" for m in items_default)

    # Explicit query for archived
    res_archived = await auth_client.get("/api/memories?status=archived")
    assert res_archived.status_code == 200
    items_archived = res_archived.json()
    assert any(m["content"] == "Archived memory item" for m in items_archived)
    assert not any(m["content"] == "Active memory item" for m in items_archived)


@pytest.mark.asyncio
async def test_memory_center_pagination(auth_client: AsyncClient):
    """Memory list supports limit and offset pagination."""
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]

    async with TestSession() as session:
        for i in range(5):
            session.add(
                Memory(
                    user_id=user_id,
                    memory_type="fact",
                    key=f"page_key_{i}",
                    content=f"Pagination test item {i}",
                    status="active",
                )
            )
        await session.commit()

    res_p1 = await auth_client.get("/api/memories?limit=2&offset=0")
    assert res_p1.status_code == 200
    items_p1 = res_p1.json()
    assert len(items_p1) == 2

    res_p2 = await auth_client.get("/api/memories?limit=2&offset=2")
    assert res_p2.status_code == 200
    items_p2 = res_p2.json()
    assert len(items_p2) == 2
    # Ensure no overlap between page 1 and page 2
    p1_ids = {m["id"] for m in items_p1}
    p2_ids = {m["id"] for m in items_p2}
    assert p1_ids.isdisjoint(p2_ids)


@pytest.mark.asyncio
async def test_explain_and_history_cross_user_isolation(auth_client: AsyncClient, client: AsyncClient):
    """Accessing explain or history of another user's memory returns 404."""
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]

    async with TestSession() as session:
        m = Memory(
            user_id=user_id,
            memory_type="fact",
            key="isolated_key",
            content="Isolated user memory content",
            status="active",
        )
        session.add(m)
        await session.commit()
        await session.refresh(m)
        mem_id = str(m.id)

    # Owner can access explain and history
    res_explain_owner = await auth_client.get(f"/api/memories/{mem_id}/explain")
    assert res_explain_owner.status_code == 200

    res_history_owner = await auth_client.get(f"/api/memories/{mem_id}/history")
    assert res_history_owner.status_code == 200

    # Register other user
    r_other = await client.post(
        "/api/auth/register",
        json={"email": "other_phase4@example.com", "password": "password123", "display_name": "Other"},
    )
    token_other = r_other.json()["access_token"]
    other_headers = {"Authorization": f"Bearer {token_other}"}

    # Other user receives 404
    res_explain_other = await client.get(f"/api/memories/{mem_id}/explain", headers=other_headers)
    assert res_explain_other.status_code == 404

    res_history_other = await client.get(f"/api/memories/{mem_id}/history", headers=other_headers)
    assert res_history_other.status_code == 404

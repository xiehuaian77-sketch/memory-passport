"""Phase 3.0C: Conversation management, ordering, and user isolation tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.repositories import conversation_repo


@pytest.mark.asyncio
async def test_create_conversation(auth_client: AsyncClient):
    """Authenticated user can create a conversation and receive initial metadata."""
    resp = await auth_client.post("/api/conversations")
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert "user_id" in data
    assert "created_at" in data
    assert "updated_at" in data
    assert data["messages"] == []


@pytest.mark.asyncio
async def test_conversation_user_isolation(auth_client: AsyncClient):
    """User A cannot list or see User B's conversations."""
    # User A creates a conversation
    r1 = await auth_client.post("/api/conversations")
    conv_a_id = r1.json()["id"]

    # Register User B
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client_b:
        r_reg = await client_b.post(
            "/api/auth/register",
            json={
                "email": "user_b_conv@example.com",
                "password": "password123",
                "display_name": "User B",
            },
        )
        token_b = r_reg.json()["access_token"]
        client_b.headers["Authorization"] = f"Bearer {token_b}"

        # User B creates a conversation
        r2 = await client_b.post("/api/conversations")
        conv_b_id = r2.json()["id"]

        # User B lists conversations: must see conv_b, never conv_a
        list_b = await client_b.get("/api/conversations")
        assert list_b.status_code == 200
        b_ids = [c["id"] for c in list_b.json()]
        assert conv_b_id in b_ids
        assert conv_a_id not in b_ids

        # User A lists conversations: must see conv_a, never conv_b
        list_a = await auth_client.get("/api/conversations")
        assert list_a.status_code == 200
        a_ids = [c["id"] for c in list_a.json()]
        assert conv_a_id in a_ids
        assert conv_b_id not in a_ids


@pytest.mark.asyncio
async def test_cross_user_conversation_returns_404(auth_client: AsyncClient):
    """Accessing or modifying another user's conversation strictly returns 404."""
    # User A creates conversation
    r_a = await auth_client.post("/api/conversations")
    conv_a_id = r_a.json()["id"]

    # Register User B
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client_b:
        r_reg = await client_b.post(
            "/api/auth/register",
            json={
                "email": "user_b_attack@example.com",
                "password": "password123",
                "display_name": "Attacker",
            },
        )
        token_b = r_reg.json()["access_token"]
        client_b.headers["Authorization"] = f"Bearer {token_b}"

        # User B tries GET /api/conversations/{conv_a_id} -> 404
        r_get = await client_b.get(f"/api/conversations/{conv_a_id}")
        assert r_get.status_code == 404

        # User B tries GET /api/conversations/{conv_a_id}/messages -> 404
        r_msgs = await client_b.get(f"/api/conversations/{conv_a_id}/messages")
        assert r_msgs.status_code == 404

        # User B tries DELETE /api/conversations/{conv_a_id} -> 404
        r_del = await client_b.delete(f"/api/conversations/{conv_a_id}")
        assert r_del.status_code == 404


@pytest.mark.asyncio
async def test_history_order_is_deterministic(auth_client: AsyncClient):
    """Conversation messages are always retrieved in ascending chronological order."""
    r_create = await auth_client.post("/api/conversations")
    conv_id = r_create.json()["id"]

    # Directly insert ordered messages via repository
    from tests.conftest import TestSession

    async with TestSession() as session:
        for i in range(5):
            role = "user" if i % 2 == 0 else "assistant"
            await conversation_repo.add_message(
                session, conversation_id=conv_id, role=role, content=f"Message step {i}"
            )
        await session.commit()

    r_msgs = await auth_client.get(f"/api/conversations/{conv_id}/messages")
    assert r_msgs.status_code == 200
    msgs = r_msgs.json()
    assert len(msgs) == 5
    for i in range(5):
        assert msgs[i]["content"] == f"Message step {i}"


@pytest.mark.asyncio
async def test_history_limit_enforced(auth_client: AsyncClient):
    """get_recent_messages limits output to the requested limit parameter."""
    r_create = await auth_client.post("/api/conversations")
    conv_id = r_create.json()["id"]

    from tests.conftest import TestSession

    async with TestSession() as session:
        for i in range(30):
            await conversation_repo.add_message(
                session,
                conversation_id=conv_id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"Turn {i:02d}",
            )
        await session.commit()

    # Query with default limit=20 on repo
    async with TestSession() as session:
        recent = await conversation_repo.get_recent_messages(
            session, conversation_id=conv_id, limit=20
        )
        assert len(recent) == 20
        # Returned in chronological order, containing the last 20 messages (turns 10..29)
        assert recent[0].content == "Turn 10"
        assert recent[-1].content == "Turn 29"


@pytest.mark.asyncio
async def test_no_unbounded_history_loading():
    """Repository strictly caps limit so unbounded loading is prevented."""
    from tests.conftest import TestSession

    async with TestSession() as session:
        conv = await conversation_repo.create_conversation(session, user_id="test-uid")
        for i in range(120):
            await conversation_repo.add_message(
                session, conversation_id=conv.id, role="user", content=f"msg-{i}"
            )
        await session.commit()

        # Request with huge limit (e.g. 999999) must be bounded by bounded_limit (max 100)
        messages = await conversation_repo.get_recent_messages(
            session, conversation_id=conv.id, limit=999999
        )
        assert len(messages) <= 100

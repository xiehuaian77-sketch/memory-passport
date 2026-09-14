"""Comprehensive Security & Authorization Test Suite for Agent MCP Access (Phase 6.5 Step 2).

Covers:
A. Authentication (1 to 9)
B. Authorization (10 to 20)
C. Tenant Isolation (21 to 26)
D. High Risk (27 to 31)
E. Revoke (32 to 34)
F. Audit (35 to 37)
G. Concurrency & Replay (38 to 42)
"""

import asyncio
from datetime import datetime, timedelta, timezone
import json
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models.governance import MemoryAuditLog
from app.models.memory import Memory
from app.models.permission_grant import AgentPermission
from app.models.user import User
from app.services import agent_permission_service, agent_service
from tests.conftest import TestSession


async def post_mcp_agent(
    client: AsyncClient,
    body: dict,
    api_key: str | None = None,
    raw_auth_header: str | None = None,
    headers: dict | None = None,
) -> tuple[int, dict]:
    """Helper to send POST /mcp requests with agent headers."""
    req_headers = {
        "content-type": "application/json",
        "MCP-Protocol-Version": "2026-07-28",
    }
    if raw_auth_header is not None:
        req_headers["Authorization"] = raw_auth_header
    elif api_key is not None:
        req_headers["Authorization"] = f"Bearer {api_key}"

    if headers:
        req_headers.update(headers)

    resp = await client.post("/mcp", json=body, headers=req_headers)
    try:
        data = resp.json()
    except Exception:
        data = {"_raw": resp.text}
    return resp.status_code, data


# ==============================================================================
# A. Authentication (Tests 1 to 9)
# ==============================================================================

@pytest.mark.asyncio
async def test_01_missing_authorization():
    """1. Missing Authorization header returns 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover"},
            raw_auth_header=None,
        )
        assert status == 401


@pytest.mark.asyncio
async def test_02_invalid_auth_scheme():
    """2. Non-Bearer authorization scheme returns 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover"},
            raw_auth_header="Basic dXNlcjpwYXNz",
        )
        assert status == 401


@pytest.mark.asyncio
async def test_03_malformed_agent_key():
    """3. Malformed agent key returns 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover"},
            api_key="mp_ak_",
        )
        assert status == 401
        assert "Invalid agent credentials" in data.get("detail", "")


@pytest.mark.asyncio
async def test_04_unknown_agent_key():
    """4. Non-existent agent key returns 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover"},
            api_key="mp_ak_" + "0" * 64,
        )
        assert status == 401
        assert "Invalid agent credentials" in data.get("detail", "")


@pytest.mark.asyncio
async def test_05_wrong_agent_key():
    """5. Tampered/wrong agent key returns 401."""
    async with TestSession() as db:
        user = User(email="t05@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent05")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        tampered_key = api_key[:-4] + "ffff"
        status, data = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover"},
            api_key=tampered_key,
        )
        assert status == 401
        assert "Invalid agent credentials" in data.get("detail", "")


@pytest.mark.asyncio
async def test_06_revoked_agent_key():
    """6. Revoked agent key returns 401."""
    async with TestSession() as db:
        user = User(email="t06@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent06")
        await agent_service.revoke_agent(db, user_id=user.id, agent_id=agent.id)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover"},
            api_key=api_key,
        )
        assert status == 401
        assert "Invalid agent credentials" in data.get("detail", "")


@pytest.mark.asyncio
async def test_07_valid_agent_key():
    """7. Valid agent key successfully authenticates on server/discover."""
    async with TestSession() as db:
        user = User(email="t07@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent07")
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover"},
            api_key=api_key,
        )
        assert status == 200
        assert data.get("result", {}).get("protocolVersion") == "2026-07-28"


@pytest.mark.asyncio
async def test_08_valid_agent_resolves_correct_user_id():
    """8. Valid agent key correctly binds to owner's user_id."""
    async with TestSession() as db:
        user = User(email="t08@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent08")

        caller = await agent_service.authenticate_agent_key(db, api_key)
        assert caller.is_agent is True
        assert caller.user_id == user.id
        assert caller.user is not None
        assert caller.user.email == "t08@example.com"


@pytest.mark.asyncio
async def test_09_valid_agent_resolves_correct_agent_id():
    """9. Valid agent key correctly binds to agent_id."""
    async with TestSession() as db:
        user = User(email="t09@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent09")

        caller = await agent_service.authenticate_agent_key(db, api_key)
        assert caller.agent_id == agent.id
        assert caller.agent is not None
        assert caller.agent.name == "Agent09"


# ==============================================================================
# B. Authorization (Tests 10 to 20)
# ==============================================================================

@pytest.mark.asyncio
async def test_10_read_memory_allowed():
    """10. Agent with READ_MEMORY can execute memory_search."""
    async with TestSession() as db:
        user = User(email="t10@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent10")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.READ_MEMORY
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_search",
                    "arguments": {"query": "python", "search_mode": "keyword"},
                },
            },
            api_key=api_key,
        )
        assert status == 200
        assert "result" in data


@pytest.mark.asyncio
async def test_11_read_memory_missing_denied_403():
    """11. Agent without READ_MEMORY calling memory_search returns 403."""
    async with TestSession() as db:
        user = User(email="t11@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent11")
        await db.commit()
        # No permission granted

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_search",
                    "arguments": {"query": "python", "search_mode": "keyword"},
                },
            },
            api_key=api_key,
        )
        assert status == 403
        assert "Permission denied" in data.get("detail", "")


@pytest.mark.asyncio
async def test_12_read_preferences_allowed_filters_to_preference_only():
    """12. Agent with only READ_PREFERENCES executes memory_search and receives only preference items."""
    async with TestSession() as db:
        user = User(email="t12@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        # Seed two memories: one preference, one task
        m1 = Memory(user_id=user.id, key="pref1", content="Likes dark mode", memory_type="preference", is_shared=True)
        m2 = Memory(user_id=user.id, key="task1", content="Submit tax return", memory_type="task", is_shared=True)
        db.add_all([m1, m2])
        await db.commit()

        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent12")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.READ_PREFERENCES
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Search for all items
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_search",
                    "arguments": {"query": "mode return", "search_mode": "keyword"},
                },
            },
            api_key=api_key,
        )
        assert status == 200
        content_text = data["result"]["content"][0]["text"]
        items = json.loads(content_text)
        # Must only contain preference items
        for it in items:
            assert it["type"] == "preference"
            assert "tax" not in it["content"]


@pytest.mark.asyncio
async def test_13_create_memory_allowed():
    """13. Agent with CREATE_MEMORY can call memory_create."""
    async with TestSession() as db:
        user = User(email="t13@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent13")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.CREATE_MEMORY
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_create",
                    "arguments": {"key": "test_pref", "content": "Prefers TypeScript"},
                },
            },
            api_key=api_key,
        )
        assert status == 200
        assert "result" in data


@pytest.mark.asyncio
async def test_14_create_memory_missing_denied_403():
    """14. Agent without CREATE_MEMORY calling memory_create returns 403."""
    async with TestSession() as db:
        user = User(email="t14@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent14")
        # Only grant READ_MEMORY
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.READ_MEMORY
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_create",
                    "arguments": {"key": "fail_key", "content": "Should be rejected"},
                },
            },
            api_key=api_key,
        )
        assert status == 403
        assert "Permission denied" in data.get("detail", "")


@pytest.mark.asyncio
async def test_15_update_memory_allowed():
    """15. Agent with UPDATE_MEMORY can call memory_update."""
    async with TestSession() as db:
        user = User(email="t15@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        mem = Memory(user_id=user.id, key="up1", content="Original content", memory_type="preference", is_shared=True)
        db.add(mem)
        await db.commit()

        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent15")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.UPDATE_MEMORY
        )
        await db.commit()
        mem_id = mem.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_update",
                    "arguments": {"memory_id": mem_id, "content": "Updated content"},
                },
            },
            api_key=api_key,
        )
        assert status == 200
        assert "result" in data


@pytest.mark.asyncio
async def test_16_update_memory_missing_denied_403():
    """16. Agent without UPDATE_MEMORY calling memory_update returns 403."""
    async with TestSession() as db:
        user = User(email="t16@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        mem = Memory(user_id=user.id, key="up2", content="Content", memory_type="preference", is_shared=True)
        db.add(mem)
        await db.commit()

        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent16")
        await db.commit()
        mem_id = mem.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_update",
                    "arguments": {"memory_id": mem_id, "content": "Denied update"},
                },
            },
            api_key=api_key,
        )
        assert status == 403
        assert "Permission denied" in data.get("detail", "")


@pytest.mark.asyncio
async def test_17_expired_grant_denied_403():
    """17. Expired grant returns 403."""
    async with TestSession() as db:
        user = User(email="t17@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent17")
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.READ_MEMORY, expires_at=past
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_search",
                    "arguments": {"query": "test", "search_mode": "keyword"},
                },
            },
            api_key=api_key,
        )
        assert status == 403
        assert "Permission denied" in data.get("detail", "")


@pytest.mark.asyncio
async def test_18_revoked_grant_denied_403():
    """18. Revoked grant returns 403."""
    async with TestSession() as db:
        user = User(email="t18@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent18")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.READ_MEMORY
        )
        await agent_permission_service.revoke_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.READ_MEMORY
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_search",
                    "arguments": {"query": "test", "search_mode": "keyword"},
                },
            },
            api_key=api_key,
        )
        assert status == 403
        assert "Permission denied" in data.get("detail", "")


@pytest.mark.asyncio
async def test_19_revoked_agent_denied_401():
    """19. Revoked agent attempting tool call returns 401."""
    async with TestSession() as db:
        user = User(email="t19@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent19")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.READ_MEMORY
        )
        await agent_service.revoke_agent(db, user_id=user.id, agent_id=agent.id)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_search",
                    "arguments": {"query": "test", "search_mode": "keyword"},
                },
            },
            api_key=api_key,
        )
        assert status == 401
        assert "Invalid agent credentials" in data.get("detail", "")


@pytest.mark.asyncio
async def test_20_fake_permission_denied_403():
    """20. Tool requiring unsupported or fake permission fails closed with 403."""
    async with TestSession() as db:
        user = User(email="t20@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent20")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.READ_MEMORY
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Call a tool not permitted for agents
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "chat",
                    "arguments": {"message": "hello"},
                },
            },
            api_key=api_key,
        )
        assert status == 403
        assert "Permission denied" in data.get("detail", "")


# ==============================================================================
# C. Tenant Isolation (Tests 21 to 26)
# ==============================================================================

@pytest.mark.asyncio
async def test_21_agent_a_cannot_read_user_b_memory():
    """21. Agent A (User A) cannot search or retrieve memories belonging to User B."""
    async with TestSession() as db:
        user_a = User(email="ua21@example.com", hashed_password="pw", display_name="User A")
        user_b = User(email="ub21@example.com", hashed_password="pw", display_name="User B")
        db.add_all([user_a, user_b])
        await db.commit()

        # Seed secret memory for User B
        mem_b = Memory(user_id=user_b.id, key="secret_b", content="SuperSecretUserBToken", memory_type="context", is_shared=True)
        db.add(mem_b)
        await db.commit()

        agent_a, api_key_a = await agent_service.create_agent(db, user_id=user_a.id, name="AgentA")
        await agent_permission_service.grant_permission(
            db, user_id=user_a.id, agent_id=agent_a.id, permission=AgentPermission.READ_MEMORY
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_search",
                    "arguments": {"query": "SuperSecretUserBToken", "search_mode": "keyword"},
                },
            },
            api_key=api_key_a,
        )
        assert status == 200
        items = json.loads(data["result"]["content"][0]["text"])
        assert len(items) == 0


@pytest.mark.asyncio
async def test_22_agent_a_cannot_write_user_b_memory():
    """22. Agent A creates memory strictly bound to User A, never User B."""
    async with TestSession() as db:
        user_a = User(email="ua22@example.com", hashed_password="pw", display_name="User A")
        user_b = User(email="ub22@example.com", hashed_password="pw", display_name="User B")
        db.add_all([user_a, user_b])
        await db.commit()

        agent_a, api_key_a = await agent_service.create_agent(db, user_id=user_a.id, name="AgentA")
        await agent_permission_service.grant_permission(
            db, user_id=user_a.id, agent_id=agent_a.id, permission=AgentPermission.CREATE_MEMORY
        )
        await db.commit()
        user_a_id = user_a.id
        user_b_id = user_b.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_create",
                    "arguments": {"key": "agent_written", "content": "Created by agent A"},
                },
            },
            api_key=api_key_a,
        )
        assert status == 200
        res = json.loads(data["result"]["content"][0]["text"])
        created_id = res["id"]

    async with TestSession() as db:
        stmt = select(Memory).where(Memory.id == created_id)
        created_mem = (await db.execute(stmt)).scalar_one_or_none()
        assert created_mem is not None
        assert created_mem.user_id == user_a_id
        assert created_mem.user_id != user_b_id


@pytest.mark.asyncio
async def test_23_forged_user_id_ignored():
    """23. Client passing forged user_id in arguments is ignored."""
    async with TestSession() as db:
        user_a = User(email="ua23@example.com", hashed_password="pw", display_name="User A")
        user_b = User(email="ub23@example.com", hashed_password="pw", display_name="User B")
        db.add_all([user_a, user_b])
        await db.commit()

        agent_a, api_key_a = await agent_service.create_agent(db, user_id=user_a.id, name="AgentA")
        await agent_permission_service.grant_permission(
            db, user_id=user_a.id, agent_id=agent_a.id, permission=AgentPermission.CREATE_MEMORY
        )
        await db.commit()
        user_a_id = user_a.id
        user_b_id = user_b.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_create",
                    "arguments": {
                        "key": "forged_attempt",
                        "content": "Trying to write to User B",
                        "user_id": user_b_id,  # Forged param
                    },
                },
            },
            api_key=api_key_a,
        )
        assert status == 200
        res = json.loads(data["result"]["content"][0]["text"])
        created_id = res["id"]

    async with TestSession() as db:
        stmt = select(Memory).where(Memory.id == created_id)
        mem = (await db.execute(stmt)).scalar_one_or_none()
        assert mem.user_id == user_a_id
        assert mem.user_id != user_b_id


@pytest.mark.asyncio
async def test_24_forged_agent_id_ignored():
    """24. Client passing forged agent_id in arguments is ignored."""
    async with TestSession() as db:
        user = User(email="t24@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent_a, api_key_a = await agent_service.create_agent(db, user_id=user.id, name="AgentA")
        agent_b, _ = await agent_service.create_agent(db, user_id=user.id, name="AgentB")

        # Grant to Agent A
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent_a.id, permission=AgentPermission.CREATE_MEMORY
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_create",
                    "arguments": {
                        "key": "forged_agent_key",
                        "content": "Hello",
                        "agent_id": agent_b.id,  # Forged param
                    },
                },
            },
            api_key=api_key_a,
        )
        assert status == 200


@pytest.mark.asyncio
async def test_25_memory_id_guessing_cannot_cross_tenant():
    """25. Guessing another user's memory ID returns not found."""
    async with TestSession() as db:
        user_a = User(email="ua25@example.com", hashed_password="pw", display_name="User A")
        user_b = User(email="ub25@example.com", hashed_password="pw", display_name="User B")
        db.add_all([user_a, user_b])
        await db.commit()

        mem_b = Memory(user_id=user_b.id, key="b_key", content="User B data", memory_type="preference", is_shared=True)
        db.add(mem_b)
        await db.commit()

        agent_a, api_key_a = await agent_service.create_agent(db, user_id=user_a.id, name="AgentA")
        await agent_permission_service.grant_permission(
            db, user_id=user_a.id, agent_id=agent_a.id, permission=AgentPermission.READ_MEMORY
        )
        await db.commit()
        mem_b_id = mem_b.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_get",
                    "arguments": {"memory_id": mem_b_id},
                },
            },
            api_key=api_key_a,
        )
        assert status == 200
        # In MCP JSON-RPC, not found is returned as isError: true
        assert data.get("result", {}).get("isError") is True
        assert "not found" in data["result"]["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_26_agent_a_cannot_use_agent_b_permission():
    """26. Agent A cannot leverage permissions granted exclusively to Agent B."""
    async with TestSession() as db:
        user = User(email="t26@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent_a, api_key_a = await agent_service.create_agent(db, user_id=user.id, name="AgentA")
        agent_b, api_key_b = await agent_service.create_agent(db, user_id=user.id, name="AgentB")

        # Grant CREATE_MEMORY ONLY to Agent B
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent_b.id, permission=AgentPermission.CREATE_MEMORY
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_create",
                    "arguments": {"key": "test_borrow", "content": "Borrow permission"},
                },
            },
            api_key=api_key_a,
        )
        assert status == 403
        assert "Permission denied" in data.get("detail", "")


# ==============================================================================
# D. High Risk & Forbidden Tools (Tests 27 to 31)
# ==============================================================================

@pytest.mark.asyncio
async def test_27_archive_denied_403():
    """27. memory_archive is forbidden for AI Agents."""
    async with TestSession() as db:
        user = User(email="t27@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent27")
        # Grant all 4 permissions
        for p in [AgentPermission.READ_MEMORY, AgentPermission.CREATE_MEMORY, AgentPermission.UPDATE_MEMORY]:
            await agent_permission_service.grant_permission(db, user_id=user.id, agent_id=agent.id, permission=p)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_archive",
                    "arguments": {"memory_id": "dummy_id"},
                },
            },
            api_key=api_key,
        )
        assert status == 403
        assert "forbidden for AI Agents" in data.get("detail", "")


@pytest.mark.asyncio
async def test_28_restore_denied_403():
    """28. memory_restore is forbidden for AI Agents."""
    async with TestSession() as db:
        user = User(email="t28@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent28")
        for p in [AgentPermission.READ_MEMORY, AgentPermission.CREATE_MEMORY, AgentPermission.UPDATE_MEMORY]:
            await agent_permission_service.grant_permission(db, user_id=user.id, agent_id=agent.id, permission=p)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_restore",
                    "arguments": {"memory_id": "dummy_id"},
                },
            },
            api_key=api_key,
        )
        assert status == 403
        assert "forbidden for AI Agents" in data.get("detail", "")


@pytest.mark.asyncio
async def test_29_supersede_denied_403():
    """29. memory_supersede is forbidden for AI Agents."""
    async with TestSession() as db:
        user = User(email="t29@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent29")
        for p in [AgentPermission.READ_MEMORY, AgentPermission.CREATE_MEMORY, AgentPermission.UPDATE_MEMORY]:
            await agent_permission_service.grant_permission(db, user_id=user.id, agent_id=agent.id, permission=p)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_supersede",
                    "arguments": {"memory_id": "m1", "replacement_memory_id": "m2"},
                },
            },
            api_key=api_key,
        )
        assert status == 403
        assert "forbidden for AI Agents" in data.get("detail", "")


@pytest.mark.asyncio
async def test_30_hard_delete_denied_403():
    """30. hard delete / delete tools are forbidden for AI Agents."""
    async with TestSession() as db:
        user = User(email="t30@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent30")
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "hard_delete",
                    "arguments": {"memory_id": "dummy_id"},
                },
            },
            api_key=api_key,
        )
        assert status == 403
        assert "forbidden for AI Agents" in data.get("detail", "")


@pytest.mark.asyncio
async def test_31_conversation_tools_denied_403():
    """31. conversation_memory_extract and chat tools are denied for AI Agents in Phase 6.5."""
    async with TestSession() as db:
        user = User(email="t31@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent31")
        for p in [AgentPermission.READ_MEMORY, AgentPermission.CREATE_MEMORY]:
            await agent_permission_service.grant_permission(db, user_id=user.id, agent_id=agent.id, permission=p)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await post_mcp_agent(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "conversation_memory_extract",
                    "arguments": {"conversation_id": "c1"},
                },
            },
            api_key=api_key,
        )
        assert status == 403
        assert "not permitted for AI Agents" in data.get("detail", "")


# ==============================================================================
# E. Revocation Immediacy (Tests 32 to 34)
# ==============================================================================

@pytest.mark.asyncio
async def test_32_revoke_agent_immediate_401():
    """32. Revoking an agent causes next request to immediately 401."""
    async with TestSession() as db:
        user = User(email="t32@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent32")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.READ_MEMORY
        )
        await db.commit()
        agent_id = agent.id
        user_id = user.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Request succeeds
        s1, d1 = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "memory_search", "arguments": {"query": "test"}}},
            api_key=api_key,
        )
        assert s1 == 200

        # 2. Revoke agent in DB
        async with TestSession() as db:
            await agent_service.revoke_agent(db, user_id=user_id, agent_id=agent_id)
            await db.commit()

        # 3. Next request immediately fails with 401
        s2, d2 = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "memory_search", "arguments": {"query": "test"}}},
            api_key=api_key,
        )
        assert s2 == 401
        assert "Invalid agent credentials" in d2.get("detail", "")


@pytest.mark.asyncio
async def test_33_revoke_permission_immediate_403():
    """33. Revoking a permission causes next request to immediately 403."""
    async with TestSession() as db:
        user = User(email="t33@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent33")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.READ_MEMORY
        )
        await db.commit()
        agent_id = agent.id
        user_id = user.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Request succeeds
        s1, d1 = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "memory_search", "arguments": {"query": "test"}}},
            api_key=api_key,
        )
        assert s1 == 200

        # 2. Revoke permission in DB
        async with TestSession() as db:
            await agent_permission_service.revoke_permission(
                db, user_id=user_id, agent_id=agent_id, permission=AgentPermission.READ_MEMORY
            )
            await db.commit()

        # 3. Next request immediately fails with 403
        s2, d2 = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "memory_search", "arguments": {"query": "test"}}},
            api_key=api_key,
        )
        assert s2 == 403
        assert "Permission denied" in d2.get("detail", "")


@pytest.mark.asyncio
async def test_34_expire_permission_immediate_403():
    """34. Setting expires_at to past causes next request to immediately 403."""
    async with TestSession() as db:
        user = User(email="t34@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent34")
        # Grant with 10s lifetime
        future = datetime.now(timezone.utc) + timedelta(seconds=10)
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.READ_MEMORY, expires_at=future
        )
        await db.commit()
        agent_id = agent.id
        user_id = user.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Request succeeds
        s1, _ = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "memory_search", "arguments": {"query": "test"}}},
            api_key=api_key,
        )
        assert s1 == 200

        # 2. Expire in DB
        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        async with TestSession() as db:
            await agent_permission_service.grant_permission(
                db, user_id=user_id, agent_id=agent_id, permission=AgentPermission.READ_MEMORY, expires_at=past
            )
            await db.commit()

        # 3. Next request fails with 403
        s2, d2 = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "memory_search", "arguments": {"query": "test"}}},
            api_key=api_key,
        )
        assert s2 == 403


# ==============================================================================
# F. Audit Trail (Tests 35 to 37)
# ==============================================================================

@pytest.mark.asyncio
async def test_35_allowed_agent_operation_audit():
    """35. Successful Agent MCP invocation creates AGENT_ACCESS audit record with decision=ALLOW."""
    async with TestSession() as db:
        user = User(email="t35@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent35")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.READ_MEMORY
        )
        await db.commit()
        user_id = user.id
        agent_id = agent.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, _ = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "memory_search", "arguments": {"query": "test"}}},
            api_key=api_key,
        )
        assert status == 200

    async with TestSession() as db:
        stmt = select(MemoryAuditLog).where(
            MemoryAuditLog.user_id == user_id,
            MemoryAuditLog.action == "AGENT_ACCESS",
        )
        logs = list((await db.execute(stmt)).scalars().all())
        assert len(logs) >= 1
        found = False
        for log in logs:
            if log.actor_id == agent_id:
                meta = json.loads(log.metadata_json) if isinstance(log.metadata_json, str) else (log.metadata_json or {})
                assert meta.get("decision") == "ALLOW"
                assert meta.get("tool") == "memory_search"
                found = True
        assert found is True


@pytest.mark.asyncio
async def test_36_denied_agent_operation_audit():
    """36. Denied Agent MCP invocation creates AGENT_ACCESS audit record with decision=DENY."""
    async with TestSession() as db:
        user = User(email="t36@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent36")
        # No permission granted
        await db.commit()
        user_id = user.id
        agent_id = agent.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, _ = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "memory_create", "arguments": {"key": "k", "content": "c"}}},
            api_key=api_key,
        )
        assert status == 403

    async with TestSession() as db:
        stmt = select(MemoryAuditLog).where(
            MemoryAuditLog.user_id == user_id,
            MemoryAuditLog.action == "AGENT_ACCESS",
        )
        logs = list((await db.execute(stmt)).scalars().all())
        found = False
        for log in logs:
            if log.actor_id == agent_id:
                meta = json.loads(log.metadata_json) if isinstance(log.metadata_json, str) else (log.metadata_json or {})
                assert meta.get("decision") == "DENY"
                assert meta.get("tool") == "memory_create"
                found = True
        assert found is True


@pytest.mark.asyncio
async def test_37_no_plaintext_api_key_in_audit():
    """37. Audit logs strictly omit plaintext API key and token fragments."""
    async with TestSession() as db:
        user = User(email="t37@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent37")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.READ_MEMORY
        )
        await db.commit()
        user_id = user.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "memory_search", "arguments": {"query": "test"}}},
            api_key=api_key,
        )

    async with TestSession() as db:
        stmt = select(MemoryAuditLog).where(MemoryAuditLog.user_id == user_id)
        logs = list((await db.execute(stmt)).scalars().all())
        for log in logs:
            meta_str = log.metadata_json if isinstance(log.metadata_json, str) else json.dumps(log.metadata_json or {})
            assert api_key not in meta_str
            raw_token = api_key.removeprefix("mp_ak_")
            assert raw_token not in meta_str


# ==============================================================================
# G. Concurrency, Replay & Consistency (Tests 38 to 42)
# ==============================================================================

@pytest.mark.asyncio
async def test_38_concurrent_agent_authentication():
    """38. Concurrent MCP requests with the same Agent Key authenticate deterministically."""
    async with TestSession() as db:
        user = User(email="t38@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent38")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.READ_MEMORY
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        tasks = [
            post_mcp_agent(
                client,
                {"jsonrpc": "2.0", "id": i, "method": "server/discover"},
                api_key=api_key,
            )
            for i in range(5)
        ]
        results = await asyncio.gather(*tasks)
        for status, data in results:
            assert status == 200
            assert data["result"]["protocolVersion"] == "2026-07-28"


@pytest.mark.asyncio
async def test_39_revoke_agent_race_resilience():
    """39. Agent status check is evaluated in real-time per request without session caching."""
    async with TestSession() as db:
        user = User(email="t39@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent39")
        await db.commit()
        user_id = user.id
        agent_id = agent.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        s1, _ = await post_mcp_agent(client, {"jsonrpc": "2.0", "id": 1, "method": "server/discover"}, api_key=api_key)
        assert s1 == 200

        async with TestSession() as db:
            await agent_service.revoke_agent(db, user_id=user_id, agent_id=agent_id)
            await db.commit()

        s2, _ = await post_mcp_agent(client, {"jsonrpc": "2.0", "id": 2, "method": "server/discover"}, api_key=api_key)
        assert s2 == 401


@pytest.mark.asyncio
async def test_40_revoke_permission_race_resilience():
    """40. Permission status check is evaluated in real-time per request without permission caching."""
    async with TestSession() as db:
        user = User(email="t40@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent40")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.READ_MEMORY
        )
        await db.commit()
        user_id = user.id
        agent_id = agent.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        s1, _ = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "memory_search", "arguments": {"query": "x"}}},
            api_key=api_key,
        )
        assert s1 == 200

        async with TestSession() as db:
            await agent_permission_service.revoke_permission(
                db, user_id=user_id, agent_id=agent_id, permission=AgentPermission.READ_MEMORY
            )
            await db.commit()

        s2, _ = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "memory_search", "arguments": {"query": "x"}}},
            api_key=api_key,
        )
        assert s2 == 403


@pytest.mark.asyncio
async def test_41_human_jwt_mcp_regression():
    """41. Existing Human JWT calling MCP continues to have full access without regression."""
    from jose import jwt
    from app.config import settings

    async with TestSession() as db:
        user = User(email="t41_human@example.com", hashed_password="pw", display_name="Human")
        db.add(user)
        await db.commit()
        user_id = user.id

    token = jwt.encode(
        {"sub": user_id, "exp": (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Human can call memory_search
        s1, d1 = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "memory_search", "arguments": {"query": "test"}}},
            raw_auth_header=f"Bearer {token}",
        )
        assert s1 == 200
        assert "result" in d1

        # Human can call server/discover
        s2, d2 = await post_mcp_agent(
            client,
            {"jsonrpc": "2.0", "id": 2, "method": "server/discover"},
            raw_auth_header=f"Bearer {token}",
        )
        assert s2 == 200


@pytest.mark.asyncio
async def test_42_authorization_remains_deterministic():
    """42. Multiple successive authorized tool calls maintain deterministic behavior."""
    async with TestSession() as db:
        user = User(email="t42@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="Agent42")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.CREATE_MEMORY
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for i in range(3):
            status, data = await post_mcp_agent(
                client,
                {
                    "jsonrpc": "2.0",
                    "id": i,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_create",
                        "arguments": {"key": f"det_key_{i}", "content": f"Deterministic content {i}"},
                    },
                },
                api_key=api_key,
            )
            assert status == 200
            assert "result" in data

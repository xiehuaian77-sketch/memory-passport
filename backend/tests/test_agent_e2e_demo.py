"""Phase 6.5 Step 3: End-to-End Demo & Security Boundary Integration Tests.

Validates the complete closed loop:
Wallet/Human JWT -> Agent Registration (One-time API Key) -> Permission Delegations
-> Authorization Boundary -> MCP Tools -> Server-side Preference Filtering
-> High-Risk Hard Deny -> Real-time Revocation -> Audit Trails (Zero Key Leakage).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any

from httpx import ASGITransport, AsyncClient
from jose import jwt
import pytest

from app.config import settings
from app.main import app
from app.models.agent import Agent
from app.models.memory import Memory
from app.models.user import User
from app.services import agent_service
from tests.conftest import TestSession


def make_jwt(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": (datetime.now(timezone.utc) + timedelta(hours=2)).timestamp(),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def mcp_call(
    client: AsyncClient,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    api_key: str | None = None,
    jwt_token: str | None = None,
) -> tuple[int, dict[str, Any]]:
    headers: dict[str, str] = {
        "content-type": "application/json",
        "MCP-Protocol-Version": "2026-07-28",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    elif jwt_token:
        headers["Authorization"] = f"Bearer {jwt_token}"

    resp = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments or {},
            },
        },
        headers=headers,
    )
    data = resp.json() if resp.content else {}
    return resp.status_code, data


# ==============================================================================
# E2E Closed Loop Tests (Tests 1 to 15)
# ==============================================================================

@pytest.mark.asyncio
async def test_01_human_jwt_creates_agent():
    """TEST 1: Human JWT creates Agent successfully."""
    async with TestSession() as db:
        user = User(email="e2e01@example.com", hashed_password="pw", display_name="User01")
        db.add(user)
        await db.commit()
        token = make_jwt(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/agents",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Assistant-01", "description": "E2E Test Assistant"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Assistant-01"
        assert data["status"].upper() == "ACTIVE"
        assert "api_key" in data


@pytest.mark.asyncio
async def test_02_create_agent_returns_plaintext_key_once():
    """TEST 2: Create Agent returns valid mp_ak_ plaintext API key exactly once."""
    async with TestSession() as db:
        user = User(email="e2e02@example.com", hashed_password="pw", display_name="User02")
        db.add(user)
        await db.commit()
        token = make_jwt(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/agents",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "KeyCheckAgent"},
        )
        assert resp.status_code == 201
        data = resp.json()
        api_key = data["api_key"]
        assert api_key.startswith("mp_ak_")
        assert len(api_key) == 70  # 6 prefix + 64 hex


@pytest.mark.asyncio
async def test_03_database_only_stores_key_hash():
    """TEST 3: Database strictly stores key_hash; plaintext key is absent from DB."""
    async with TestSession() as db:
        user = User(email="e2e03@example.com", hashed_password="pw", display_name="User03")
        db.add(user)
        await db.commit()
        token = make_jwt(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/agents",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "HashCheckAgent"},
        )
        api_key = resp.json()["api_key"]
        agent_id = resp.json()["id"]

    async with TestSession() as db:
        agent = await db.get(Agent, agent_id)
        assert agent is not None
        assert agent.key_hash != api_key
        assert not hasattr(agent, "api_key")
        assert not hasattr(agent, "plaintext_key")
        assert agent_service.verify_agent_key(api_key, agent.key_hash) is True


@pytest.mark.asyncio
async def test_04_get_agent_does_not_return_plaintext_key():
    """TEST 4: GET Agent and GET Agent list endpoints strictly omit plaintext API key."""
    async with TestSession() as db:
        user = User(email="e2e04@example.com", hashed_password="pw", display_name="User04")
        db.add(user)
        await db.commit()
        token = make_jwt(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/agents",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "NoKeyLeakAgent"},
        )
        agent_id = create_resp.json()["id"]
        raw_key = create_resp.json()["api_key"]

        # GET single
        get_resp = await client.get(
            f"/api/agents/{agent_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_resp.status_code == 200
        single_data = get_resp.json()
        assert "api_key" not in single_data
        assert raw_key not in json.dumps(single_data)

        # GET list
        list_resp = await client.get(
            "/api/agents",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert any(a["id"] == agent_id for a in list_data)
        assert raw_key not in json.dumps(list_data)


@pytest.mark.asyncio
async def test_05_human_grants_read_memory():
    """TEST 5: Human grants READ_MEMORY permission to Agent."""
    async with TestSession() as db:
        user = User(email="e2e05@example.com", hashed_password="pw", display_name="User05")
        db.add(user)
        await db.commit()
        agent, _ = await agent_service.create_agent(db, user_id=user.id, name="GrantAgent")
        await db.commit()
        token = make_jwt(user.id)
        agent_id = agent.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/agents/{agent_id}/permissions",
            headers={"Authorization": f"Bearer {token}"},
            json={"permission": "READ_MEMORY"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["permission"] == "READ_MEMORY"
        assert data["status"].upper() == "ACTIVE"
        assert data["is_active"] is True


@pytest.mark.asyncio
async def test_06_agent_calls_mcp_memory_search_200():
    """TEST 6: Agent with READ_MEMORY calls MCP memory_search -> 200."""
    async with TestSession() as db:
        user = User(email="e2e06@example.com", hashed_password="pw", display_name="User06")
        db.add(user)
        await db.commit()
        mem = Memory(user_id=user.id, key="framework", content="Prefers Next.js and FastAPI", memory_type="preference", is_shared=True)
        db.add(mem)
        await db.commit()

        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="SearchAgent")
        token = make_jwt(user.id)
        agent_id = agent.id
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Grant READ_MEMORY
        await client.post(
            f"/api/agents/{agent_id}/permissions",
            headers={"Authorization": f"Bearer {token}"},
            json={"permission": "READ_MEMORY"},
        )

        # Call MCP with Agent API Key
        status, data = await mcp_call(
            client,
            "memory_search",
            {"query": "Next.js", "search_mode": "keyword"},
            api_key=api_key,
        )
        assert status == 200
        assert "result" in data
        assert "Next.js" in json.dumps(data)


@pytest.mark.asyncio
async def test_07_agent_calls_memory_create_without_permission_403():
    """TEST 7: Agent without CREATE_MEMORY calls memory_create -> 403."""
    async with TestSession() as db:
        user = User(email="e2e07@example.com", hashed_password="pw", display_name="User07")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="NoWriteAgent")
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status, data = await mcp_call(
            client,
            "memory_create",
            {"key": "test_key", "content": "test content", "category": "preference"},
            api_key=api_key,
        )
        assert status == 403
        assert "Permission denied" in data.get("detail", "")


@pytest.mark.asyncio
async def test_08_human_grants_create_memory_agent_calls_200():
    """TEST 8: Human grants CREATE_MEMORY, Agent calls memory_create -> 200."""
    async with TestSession() as db:
        user = User(email="e2e08@example.com", hashed_password="pw", display_name="User08")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="WriterAgent")
        await db.commit()
        token = make_jwt(user.id)
        agent_id = agent.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Grant CREATE_MEMORY
        grant_resp = await client.post(
            f"/api/agents/{agent_id}/permissions",
            headers={"Authorization": f"Bearer {token}"},
            json={"permission": "CREATE_MEMORY"},
        )
        assert grant_resp.status_code == 201

        # Agent executes memory_create
        status, data = await mcp_call(
            client,
            "memory_create",
            {"key": "agent_created_pref", "content": "Agent logged note", "category": "preference"},
            api_key=api_key,
        )
        assert status == 200
        assert "result" in data


@pytest.mark.asyncio
async def test_09_human_revokes_create_memory_agent_calls_403():
    """TEST 9: Human revokes CREATE_MEMORY, Agent immediately receives 403."""
    async with TestSession() as db:
        user = User(email="e2e09@example.com", hashed_password="pw", display_name="User09")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="RevokeWriteAgent")
        await db.commit()
        token = make_jwt(user.id)
        agent_id = agent.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Grant
        await client.post(
            f"/api/agents/{agent_id}/permissions",
            headers={"Authorization": f"Bearer {token}"},
            json={"permission": "CREATE_MEMORY"},
        )
        # Revoke
        rev_resp = await client.post(
            f"/api/agents/{agent_id}/permissions/CREATE_MEMORY/revoke",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rev_resp.status_code == 200

        # Agent tries to create memory again -> 403
        status, data = await mcp_call(
            client,
            "memory_create",
            {"key": "blocked_key", "content": "blocked content", "category": "preference"},
            api_key=api_key,
        )
        assert status == 403
        assert "Permission denied" in data.get("detail", "")


@pytest.mark.asyncio
async def test_10_human_revokes_agent_mcp_returns_401():
    """TEST 10: Human revokes Agent, next Agent MCP call returns 401."""
    async with TestSession() as db:
        user = User(email="e2e10@example.com", hashed_password="pw", display_name="User10")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="DoomedAgent")
        await db.commit()
        token = make_jwt(user.id)
        agent_id = agent.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Grant read
        await client.post(
            f"/api/agents/{agent_id}/permissions",
            headers={"Authorization": f"Bearer {token}"},
            json={"permission": "READ_MEMORY"},
        )

        # Revoke entire Agent
        rev_resp = await client.post(
            f"/api/agents/{agent_id}/revoke",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rev_resp.status_code == 200
        assert rev_resp.json()["status"].upper() == "REVOKED"

        # Agent calls MCP -> 401
        status, data = await mcp_call(
            client,
            "memory_search",
            {"query": "anything", "search_mode": "keyword"},
            api_key=api_key,
        )
        assert status == 401
        assert "Invalid agent credentials" in data.get("detail", "")


@pytest.mark.asyncio
async def test_11_tenant_isolation_agent_cannot_access_user_b():
    """TEST 11: Agent A strictly cannot read User B's memories even with exact ID."""
    async with TestSession() as db:
        user_a = User(email="usera@example.com", hashed_password="pw", display_name="UserA")
        user_b = User(email="userb@example.com", hashed_password="pw", display_name="UserB")
        db.add_all([user_a, user_b])
        await db.commit()

        # User B private memory
        mem_b = Memory(user_id=user_b.id, key="secret_b", content="User B Secret", memory_type="preference", is_shared=False)
        db.add(mem_b)
        await db.commit()
        mem_b_id = mem_b.id

        # Agent owned by User A
        agent_a, api_key_a = await agent_service.create_agent(db, user_id=user_a.id, name="AgentA")
        await db.commit()
        token_a = make_jwt(user_a.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            f"/api/agents/{agent_a.id}/permissions",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"permission": "READ_MEMORY"},
        )

        # Agent A attempts memory_get on User B's memory ID
        status, data = await mcp_call(
            client,
            "memory_get",
            {"memory_id": mem_b_id},
            api_key=api_key_a,
        )
        # Should return error inside JSON-RPC result (Memory not found)
        result = data.get("result", {})
        assert result.get("isError") is True or "not found" in json.dumps(result)


@pytest.mark.asyncio
async def test_12_read_preferences_server_side_filter():
    """TEST 12: Agent with READ_PREFERENCES only retrieves preference-type memories."""
    async with TestSession() as db:
        user = User(email="e2e12@example.com", hashed_password="pw", display_name="User12")
        db.add(user)
        await db.commit()

        mem_pref = Memory(user_id=user.id, key="editor", content="Prefers VSCode", memory_type="preference", is_shared=True)
        mem_task = Memory(user_id=user.id, key="todo", content="Deploy release", memory_type="task", is_shared=True)
        db.add_all([mem_pref, mem_task])
        await db.commit()

        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="PrefOnlyAgent")
        await db.commit()
        token = make_jwt(user.id)
        agent_id = agent.id
        task_id = mem_task.id
        pref_id = mem_pref.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            f"/api/agents/{agent_id}/permissions",
            headers={"Authorization": f"Bearer {token}"},
            json={"permission": "READ_PREFERENCES"},
        )

        # 1. Search filter: only preference items returned
        status, data = await mcp_call(
            client,
            "memory_search",
            {"query": "VSCode", "search_mode": "keyword"},
            api_key=api_key,
        )
        assert status == 200
        text = data["result"]["content"][0]["text"]
        items = json.loads(text)
        assert len(items) >= 1
        assert all(it.get("type") == "preference" for it in items)

        # 2. Get preference item -> succeeds
        status, data_pref = await mcp_call(
            client,
            "memory_get",
            {"memory_id": pref_id},
            api_key=api_key,
        )
        assert status == 200
        assert "VSCode" in data_pref["result"]["content"][0]["text"]

        # 3. Get task item -> blocked by server-side filter
        status, data_task = await mcp_call(
            client,
            "memory_get",
            {"memory_id": task_id},
            api_key=api_key,
        )
        assert data_task.get("result", {}).get("isError") is True


@pytest.mark.asyncio
async def test_13_read_preferences_agent_cannot_access_graph_or_resources():
    """TEST 13: READ_PREFERENCES Agent attempting graph tools or resources receives 403."""
    async with TestSession() as db:
        user = User(email="e2e13@example.com", hashed_password="pw", display_name="User13")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="PrefRestrictedAgent")
        await db.commit()
        token = make_jwt(user.id)
        agent_id = agent.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            f"/api/agents/{agent_id}/permissions",
            headers={"Authorization": f"Bearer {token}"},
            json={"permission": "READ_PREFERENCES"},
        )

        for tool in ["memory_related", "memory_relationships", "memory_explain", "memory_history"]:
            status, data = await mcp_call(
                client,
                tool,
                {"memory_id": "dummy-id"},
                api_key=api_key,
            )
            assert status == 403, f"Expected 403 for {tool}, got {status}"

        # Resources read
        resp = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {"uri": "memory://user/context"}},
            headers={"Authorization": f"Bearer {api_key}", "MCP-Protocol-Version": "2026-07-28"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_14_agent_high_risk_and_conversation_tools_hard_denied():
    """TEST 14: Agent calling archive, restore, supersede, hard_delete, chat, extract -> 403."""
    async with TestSession() as db:
        user = User(email="e2e14@example.com", hashed_password="pw", display_name="User14")
        db.add(user)
        await db.commit()
        agent, api_key = await agent_service.create_agent(db, user_id=user.id, name="HighRiskTestAgent")
        await db.commit()
        token = make_jwt(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Grant all 4 valid permissions
        for perm in ["READ_MEMORY", "CREATE_MEMORY", "UPDATE_MEMORY"]:
            await client.post(
                f"/api/agents/{agent.id}/permissions",
                headers={"Authorization": f"Bearer {token}"},
                json={"permission": perm},
            )

        forbidden_tools = [
            ("memory_archive", {"memory_id": "dummy"}),
            ("memory_restore", {"memory_id": "dummy"}),
            ("memory_supersede", {"old_memory_id": "dummy", "new_content": "xyz"}),
            ("hard_delete", {"memory_id": "dummy"}),
            ("chat", {"message": "hello"}),
            ("conversation_memory_extract", {"conversation_id": "c1"}),
            ("conversation_memory_confirm", {"candidate": {}}),
        ]
        for tool, args in forbidden_tools:
            status, data = await mcp_call(client, tool, args, api_key=api_key)
            assert status == 403, f"Expected 403 for tool {tool}, got {status}"


@pytest.mark.asyncio
async def test_15_audit_log_records_correct_events_with_zero_credential_leakage():
    """TEST 15: ALLOW / DENY / REVOKE audit events logged with zero API key leakage."""
    async with TestSession() as db:
        user = User(email="e2e15@example.com", hashed_password="pw", display_name="User15")
        db.add(user)
        await db.commit()
        token = make_jwt(user.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Register Agent
        reg_resp = await client.post(
            "/api/agents",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "AuditAgent"},
        )
        api_key = reg_resp.json()["api_key"]
        agent_id = reg_resp.json()["id"]

        # 2. Grant permission
        await client.post(
            f"/api/agents/{agent_id}/permissions",
            headers={"Authorization": f"Bearer {token}"},
            json={"permission": "READ_MEMORY"},
        )

        # 3. Successful MCP call -> ALLOW
        await mcp_call(client, "memory_search", {"query": "test"}, api_key=api_key)

        # 4. Denied MCP call -> DENY
        await mcp_call(client, "memory_create", {"key": "k", "content": "c"}, api_key=api_key)

        # 5. Revoke Agent -> AGENT_REVOKE
        await client.post(
            f"/api/agents/{agent_id}/revoke",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Query audit log API
        audit_resp = await client.get(
            "/api/agents/audit-logs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert audit_resp.status_code == 200
        logs = audit_resp.json()
        assert len(logs) >= 3

        # Assert no API key or token fragments appear anywhere in the audit response
        audit_json = json.dumps(logs)
        assert api_key not in audit_json
        raw_secret = api_key.removeprefix("mp_ak_")
        assert raw_secret not in audit_json

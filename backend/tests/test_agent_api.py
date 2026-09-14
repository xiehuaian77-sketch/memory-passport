"""Tests for Agent and Permission REST API (Phase 6.5)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_agent_api_crud_flow(auth_client: AsyncClient):
    # 1. Create Agent
    create_resp = await auth_client.post(
        "/api/agents",
        json={"name": "API Code Assistant", "description": "Helps write code"},
    )
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    agent_id = created_data["id"]
    assert agent_id.startswith("ag_")
    assert created_data["name"] == "API Code Assistant"
    assert created_data["status"] == "ACTIVE"

    # One-time API key is present in creation response
    api_key = created_data["api_key"]
    assert api_key.startswith("mp_ak_")

    # 2. List Agents
    list_resp = await auth_client.get("/api/agents")
    assert list_resp.status_code == 200
    agents = list_resp.json()
    assert len(agents) >= 1
    found = next((a for a in agents if a["id"] == agent_id), None)
    assert found is not None
    assert found["has_api_key"] is True

    # Critical security assertion: api_key and key_hash are NEVER returned in list!
    assert "api_key" not in found
    assert "key_hash" not in found

    # 3. Get Agent Details
    get_resp = await auth_client.get(f"/api/agents/{agent_id}")
    assert get_resp.status_code == 200
    agent_detail = get_resp.json()
    assert agent_detail["id"] == agent_id
    assert "api_key" not in agent_detail
    assert "key_hash" not in agent_detail

    # 4. Grant Permission
    grant_resp = await auth_client.post(
        f"/api/agents/{agent_id}/permissions",
        json={"permission": "READ_MEMORY"},
    )
    assert grant_resp.status_code == 201
    grant_data = grant_resp.json()
    assert grant_data["agent_id"] == agent_id
    assert grant_data["permission"] == "READ_MEMORY"
    assert grant_data["status"] == "ACTIVE"
    assert grant_data["is_active"] is True

    # 5. Check Permission endpoint
    check_resp = await auth_client.get(f"/api/agents/{agent_id}/check-permission/READ_MEMORY")
    assert check_resp.status_code == 200
    assert check_resp.json()["allowed"] is True

    check_unearned = await auth_client.get(f"/api/agents/{agent_id}/check-permission/CREATE_MEMORY")
    assert check_unearned.status_code == 200
    assert check_unearned.json()["allowed"] is False

    # 6. List Permissions
    list_perms_resp = await auth_client.get(f"/api/agents/{agent_id}/permissions")
    assert list_perms_resp.status_code == 200
    perms = list_perms_resp.json()
    assert len(perms) == 1
    assert perms[0]["permission"] == "READ_MEMORY"

    # 7. Revoke Permission
    rev_perm_resp = await auth_client.post(f"/api/agents/{agent_id}/permissions/READ_MEMORY/revoke")
    assert rev_perm_resp.status_code == 200
    assert rev_perm_resp.json()["status"] == "REVOKED"

    # Verify check now returns False
    check_after_rev = await auth_client.get(f"/api/agents/{agent_id}/check-permission/READ_MEMORY")
    assert check_after_rev.status_code == 200
    assert check_after_rev.json()["allowed"] is False

    # 8. Revoke Agent
    rev_agent_resp = await auth_client.post(f"/api/agents/{agent_id}/revoke")
    assert rev_agent_resp.status_code == 200
    assert rev_agent_resp.json()["status"] == "REVOKED"


@pytest.mark.asyncio
async def test_agent_api_cross_user_isolation(client: AsyncClient):
    # Register User 1
    r1 = await client.post("/api/auth/register", json={
        "email": "user1_agent@example.com", "password": "password123", "display_name": "U1"
    })
    token1 = r1.json()["access_token"]

    # Register User 2
    r2 = await client.post("/api/auth/register", json={
        "email": "user2_agent@example.com", "password": "password123", "display_name": "U2"
    })
    token2 = r2.json()["access_token"]

    # User 1 creates an agent
    client.headers["Authorization"] = f"Bearer {token1}"
    resp = await client.post("/api/agents", json={"name": "U1 Private Agent"})
    assert resp.status_code == 201
    agent_id = resp.json()["id"]

    # User 2 tries to read User 1's agent -> 404
    client.headers["Authorization"] = f"Bearer {token2}"
    get_res = await client.get(f"/api/agents/{agent_id}")
    assert get_res.status_code == 404

    # User 2 tries to revoke User 1's agent -> 404
    rev_res = await client.post(f"/api/agents/{agent_id}/revoke")
    assert rev_res.status_code == 404

    # User 2 tries to grant permission to User 1's agent -> 404
    grant_res = await client.post(
        f"/api/agents/{agent_id}/permissions",
        json={"permission": "READ_MEMORY"},
    )
    assert grant_res.status_code == 404

    # User 2 lists agents -> 0
    list_res = await client.get("/api/agents")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 0


@pytest.mark.asyncio
async def test_agent_api_unauthenticated_rejected(client: AsyncClient):
    client.headers.pop("Authorization", None)

    assert (await client.get("/api/agents")).status_code == 401
    assert (await client.post("/api/agents", json={"name": "NoAuth"})).status_code == 401
    assert (await client.get("/api/agents/ag_test123")).status_code == 401
    assert (await client.post("/api/agents/ag_test123/revoke")).status_code == 401

"""API integration tests for Memory Passport backend."""

import pytest
from httpx import AsyncClient


# ──────────────────────────── Health ────────────────────────────

@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "Memory Passport API"


# ──────────────────────────── Auth ──────────────────────────────

@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    resp = await client.post("/api/auth/register", json={
        "email": "user1@test.com",
        "password": "pass1234",
        "display_name": "User One",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "dup@test.com",
        "password": "pass1234",
    })
    resp = await client.post("/api/auth/register", json={
        "email": "dup@test.com",
        "password": "pass1234",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "login@test.com",
        "password": "pass1234",
    })
    resp = await client.post("/api/auth/login", json={
        "email": "login@test.com",
        "password": "pass1234",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "wrong@test.com",
        "password": "pass1234",
    })
    resp = await client.post("/api/auth/login", json={
        "email": "wrong@test.com",
        "password": "wrongpassword",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me(auth_client: AsyncClient):
    resp = await auth_client.get("/api/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "test@example.com"
    assert data["display_name"] == "Test User"
    assert "passport_id" in data
    assert data["passport_id"].startswith("mp_")


@pytest.mark.asyncio
async def test_update_me(auth_client: AsyncClient):
    resp = await auth_client.patch("/api/auth/me", json={
        "display_name": "New Name",
    })
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "New Name"


# ──────────────────────── Memory CRUD ───────────────────────────

@pytest.mark.asyncio
async def test_create_memory(auth_client: AsyncClient):
    resp = await auth_client.post("/api/memories", json={
        "category": "preference",
        "key": "language",
        "content": "我主要用中文",
        "confidence": 0.95,
        "is_shared": True,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["key"] == "language"
    assert data["content"] == "我主要用中文"
    assert data["source"] == "manual"
    assert data["confidence"] == 0.95


@pytest.mark.asyncio
async def test_list_memories(auth_client: AsyncClient):
    # Create 2 memories
    await auth_client.post("/api/memories", json={
        "category": "preference", "key": "lang", "content": "中文",
    })
    await auth_client.post("/api/memories", json={
        "category": "identity", "key": "name", "content": "张三",
    })
    resp = await auth_client.get("/api/memories")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # Filter by category
    resp = await auth_client.get("/api/memories?category=preference")
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_update_memory(auth_client: AsyncClient):
    create_resp = await auth_client.post("/api/memories", json={
        "category": "preference", "key": "style", "content": "简洁",
    })
    mem_id = create_resp.json()["id"]

    resp = await auth_client.put(f"/api/memories/{mem_id}", json={
        "content": "详细风格",
    })
    assert resp.status_code == 200
    assert resp.json()["content"] == "详细风格"


@pytest.mark.asyncio
async def test_delete_memory(auth_client: AsyncClient):
    create_resp = await auth_client.post("/api/memories", json={
        "category": "task", "key": "project", "content": "Web3",
    })
    mem_id = create_resp.json()["id"]

    resp = await auth_client.delete(f"/api/memories/{mem_id}")
    assert resp.status_code == 204

    resp = await auth_client.get(f"/api/memories/{mem_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_memories(auth_client: AsyncClient):
    await auth_client.post("/api/memories", json={
        "category": "preference", "key": "test", "content": "value",
    })
    resp = await auth_client.get("/api/memories/export/all")
    assert resp.status_code == 200
    data = resp.json()
    assert "memories" in data
    assert "passport_id" in data
    assert len(data["memories"]) == 1


@pytest.mark.asyncio
async def test_import_memories(auth_client: AsyncClient):
    resp = await auth_client.post("/api/memories/import/batch", json=[
        {"category": "preference", "key": "a", "content": "1"},
        {"category": "identity", "key": "b", "content": "2"},
    ])
    assert resp.status_code == 201
    assert len(resp.json()) == 2


# ──────────────────────── Unauthorized ──────────────────────────

@pytest.mark.asyncio
async def test_memories_unauthorized(client: AsyncClient):
    resp = await client.get("/api/memories", headers={"Authorization": "Bearer invalid"})
    assert resp.status_code == 401


# ──────────────────────── MCP ───────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_get_passport(auth_client: AsyncClient):
    # Get user's passport_id
    me_resp = await auth_client.get("/api/auth/me")
    passport_id = me_resp.json()["passport_id"]

    # Add a shared memory
    await auth_client.post("/api/memories", json={
        "category": "preference", "key": "test", "content": "data", "is_shared": True,
    })

    # MCP request
    resp = await auth_client.get(
        f"/api/mcp/passport/{passport_id}",
        headers={"Authorization": "Bearer test-mcp-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["passport_id"] == passport_id
    assert len(data["memories"]) >= 1


@pytest.mark.asyncio
async def test_mcp_invalid_key(auth_client: AsyncClient):
    resp = await auth_client.get(
        "/api/mcp/passport/mp_fake",
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert resp.status_code == 403

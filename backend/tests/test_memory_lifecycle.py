"""Phase 3.1: Memory Lifecycle tests (Status, Version, Provenance, Conflict Detection, Retrieval Filter, Authorization)."""

from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.main import app
from app.models.memory import Memory
from app.services.extraction_service import compute_candidate_signature
from tests.conftest import TestSession


@pytest.mark.asyncio
async def test_memory_default_status_and_version(auth_client: AsyncClient):
    resp = await auth_client.post(
        "/api/memories",
        json={
            "key": "editor_choice",
            "content": "User uses Neovim",
            "category": "preference",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "active"
    assert data["version"] == 1
    assert data["source_conversation_id"] is None


@pytest.mark.asyncio
async def test_memory_archive_and_restore(auth_client: AsyncClient):
    r_create = await auth_client.post(
        "/api/memories",
        json={"key": "theme", "content": "User likes solarized light", "category": "preference"},
    )
    mem_id = r_create.json()["id"]

    # 1. Archive
    r_arch = await auth_client.post(f"/api/memories/{mem_id}/archive")
    assert r_arch.status_code == 200
    assert r_arch.json()["status"] == "archived"

    async with TestSession() as session:
        mem = await session.get(Memory, mem_id)
        assert mem.status == "archived"

    # 2. Restore
    r_rest = await auth_client.post(f"/api/memories/{mem_id}/restore")
    assert r_rest.status_code == 200
    assert r_rest.json()["status"] == "active"

    async with TestSession() as session:
        mem = await session.get(Memory, mem_id)
        assert mem.status == "active"


@pytest.mark.asyncio
async def test_archive_authorization_and_cross_user_isolation(auth_client: AsyncClient):
    r_create = await auth_client.post(
        "/api/memories",
        json={"key": "secret_pref", "content": "User A secret", "category": "preference"},
    )
    mem_a_id = r_create.json()["id"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client_b:
        r_reg = await client_b.post(
            "/api/auth/register",
            json={
                "email": "user_b_lifecycle@example.com",
                "password": "password123",
                "display_name": "User B",
            },
        )
        token_b = r_reg.json()["access_token"]
        client_b.headers["Authorization"] = f"Bearer {token_b}"

        # User B attempts to archive User A memory -> 404
        r_arch = await client_b.post(f"/api/memories/{mem_a_id}/archive")
        assert r_arch.status_code == 404

        # User B attempts to restore User A memory -> 404
        r_rest = await client_b.post(f"/api/memories/{mem_a_id}/restore")
        assert r_rest.status_code == 404


@pytest.mark.asyncio
async def test_memory_version_increments_on_update(auth_client: AsyncClient):
    r_create = await auth_client.post(
        "/api/memories",
        json={"key": "framework", "content": "User uses FastAPI 0.100", "category": "preference"},
    )
    mem_id = r_create.json()["id"]
    assert r_create.json()["version"] == 1

    r_up1 = await auth_client.put(
        f"/api/memories/{mem_id}",
        json={"content": "User uses FastAPI 0.115"},
    )
    assert r_up1.status_code == 200
    assert r_up1.json()["version"] == 2
    assert r_up1.json()["content"] == "User uses FastAPI 0.115"

    r_up2 = await auth_client.put(
        f"/api/memories/{mem_id}",
        json={"content": "User uses FastAPI 0.120"},
    )
    assert r_up2.status_code == 200
    assert r_up2.json()["version"] == 3


@pytest.mark.asyncio
async def test_memory_provenance_from_conversation(auth_client: AsyncClient):
    r_conv = await auth_client.post("/api/conversations")
    conv_id = r_conv.json()["id"]

    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]

    cand_id = "cand_prov_123"
    sig = compute_candidate_signature(
        user_id=user_id,
        conversation_id=conv_id,
        candidate_id=cand_id,
        memory_type="preference",
        key="font_family",
        content="User codes using JetBrains Mono",
        importance=0.8,
        confidence=0.95,
        tags=["font", "ide"],
        raw_content="I code using JetBrains Mono font.",
    )

    resp = await auth_client.post(
        f"/api/conversations/{conv_id}/confirm-memory",
        json={
            "candidate": {
                "id": cand_id,
                "signature": sig,
                "memory_type": "preference",
                "key": "font_family",
                "content": "User codes using JetBrains Mono",
                "importance": 0.8,
                "confidence": 0.95,
                "tags": ["font", "ide"],
                "raw_content": "I code using JetBrains Mono font.",
            }
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_conversation_id"] == conv_id
    assert data["source"] == "ai_extracted"
    assert data["status"] == "active"
    assert data["version"] == 1

    async with TestSession() as session:
        mem = await session.get(Memory, data["id"])
        assert mem.source_conversation_id == conv_id


@pytest.mark.asyncio
async def test_conflict_detection_exact_key_conflict(auth_client: AsyncClient):
    await auth_client.post(
        "/api/memories",
        json={"key": "db_choice", "content": "User prefers PostgreSQL", "category": "preference"},
    )

    resp = await auth_client.post(
        "/api/memories/detect-conflicts",
        json={
            "key": "db_choice",
            "content": "User prefers MySQL 8",
            "memory_type": "preference",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_conflict"] is True
    assert len(data["conflicts"]) == 1
    c = data["conflicts"][0]
    assert c["conflict_type"] == "key_conflict"
    assert c["existing_key"] == "db_choice"
    assert c["existing_content"] == "User prefers PostgreSQL"
    assert c["recommendation"] == "archive_old"


@pytest.mark.asyncio
async def test_conflict_detection_semantic_conflict(auth_client: AsyncClient):
    mock_embed = AsyncMock()
    mock_embed.embed.side_effect = lambda text: [0.99] * 1024 if "Vim" in text else [0.98] * 1024

    with patch("app.services.memory_service.get_embedding_provider", return_value=mock_embed):
        await auth_client.post(
            "/api/memories",
            json={"key": "primary_editor", "content": "User exclusively uses Vim", "category": "preference"},
        )

        resp = await auth_client.post(
            "/api/memories/detect-conflicts",
            json={
                "key": "different_key_editor",
                "content": "User uses NeoVim for development",
                "memory_type": "preference",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_conflict"] is True
        assert any(c["conflict_type"] == "semantic_conflict" for c in data["conflicts"])


@pytest.mark.asyncio
async def test_conflict_detection_is_strictly_read_only(auth_client: AsyncClient):
    await auth_client.post(
        "/api/memories",
        json={"key": "os", "content": "User uses Debian Linux", "category": "preference"},
    )

    async with TestSession() as session:
        count_before = await session.scalar(select(func.count()).select_from(Memory))

    resp = await auth_client.post(
        "/api/memories/detect-conflicts",
        json={"key": "os", "content": "User uses Arch Linux", "memory_type": "preference"},
    )
    assert resp.status_code == 200

    async with TestSession() as session:
        count_after = await session.scalar(select(func.count()).select_from(Memory))
        mems = (await session.scalars(select(Memory))).all()

    assert count_before == count_after
    assert len(mems) == 1
    assert mems[0].content == "User uses Debian Linux"


@pytest.mark.asyncio
async def test_conflict_detection_ignores_archived_memories(auth_client: AsyncClient):
    r_create = await auth_client.post(
        "/api/memories",
        json={"key": "cloud", "content": "User uses AWS", "category": "preference"},
    )
    mem_id = r_create.json()["id"]

    await auth_client.post(f"/api/memories/{mem_id}/archive")

    resp = await auth_client.post(
        "/api/memories/detect-conflicts",
        json={"key": "cloud", "content": "User uses GCP", "memory_type": "preference"},
    )
    assert resp.status_code == 200
    assert resp.json()["has_conflict"] is False


@pytest.mark.asyncio
async def test_retrieval_filtering_excludes_archived_memories(auth_client: AsyncClient):
    mock_embed = AsyncMock()
    mock_embed.embed.return_value = [0.1] * 1024

    with patch("app.services.memory_service.get_embedding_provider", return_value=mock_embed):
        # 1. Active memory A
        await auth_client.post(
            "/api/memories",
            json={"key": "coffee", "content": "Active preference: likes espresso", "category": "preference"},
        )
        # 2. Memory B archived
        r_b = await auth_client.post(
            "/api/memories",
            json={"key": "coffee_old", "content": "Old preference: likes instant coffee", "category": "preference"},
        )
        mem_b_id = r_b.json()["id"]
        await auth_client.post(f"/api/memories/{mem_b_id}/archive")

        # 3. Retrieve context
        r_ret = await auth_client.post(
            "/api/memories/retrieve",
            json={"query": "coffee", "min_relevance": 0.0},
        )
        assert r_ret.status_code == 200
        memories_in_context = r_ret.json()["items"]
        contents = [m["content"] for m in memories_in_context]

        assert any("espresso" in c for c in contents)
        assert not any("instant coffee" in c for c in contents)


@pytest.mark.asyncio
async def test_candidate_integrity_regression(auth_client: AsyncClient):
    r_conv = await auth_client.post("/api/conversations")
    conv_id = r_conv.json()["id"]

    resp = await auth_client.post(
        f"/api/conversations/{conv_id}/confirm-memory",
        json={
            "candidate": {
                "id": "cand_tampered",
                "signature": "invalidsig" * 4,
                "memory_type": "preference",
                "key": "test",
                "content": "Tampered content",
            }
        },
    )
    assert resp.status_code == 400
    assert "tampered" in resp.json()["detail"].lower()

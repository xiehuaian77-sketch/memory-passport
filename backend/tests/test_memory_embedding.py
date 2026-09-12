"""Phase 2.3C: Memory automatic embedding persistence and lifecycle tests."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.memory import Memory
from app.models.user import User
from app.providers.embedding_provider import (
    DashScopeEmbeddingProvider,
    EmbeddingCommunicationError,
)
from app.schemas.memory import MemoryCreate
from app.services import memory_service
from tests.conftest import TestSession

DUMMY_1024_VEC = [float(i % 100) / 100.0 for i in range(1024)]
DUMMY_1024_VEC_UPDATED = [float((i + 50) % 100) / 100.0 for i in range(1024)]


# ────────────────────── 1 & 2: Creation & Vector Validation ──────────────────────

@pytest.mark.asyncio
async def test_create_memory_generates_embedding(auth_client: AsyncClient):
    """Creating memory automatically calls EmbeddingProvider and persists 1024-dim embedding."""
    with patch(
        "app.services.memory_service.get_embedding_provider"
    ) as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=list(DUMMY_1024_VEC))
        mock_get_provider.return_value = mock_provider

        resp = await auth_client.post(
            "/api/memories",
            json={
                "category": "preference",
                "key": "editor",
                "content": "I prefer dark mode and vim keybindings in VS Code.",
            },
        )
        assert resp.status_code == 201
        created = resp.json()
        mem_id = created["id"]

        # Verify mock called exactly once with canonical memory content
        mock_provider.embed.assert_awaited_once_with(
            "I prefer dark mode and vim keybindings in VS Code."
        )

        # Check DB directly
        async with TestSession() as session:
            db_mem = await session.scalar(select(Memory).where(Memory.id == mem_id))
            assert db_mem is not None
            assert db_mem.embedding is not None
            assert len(db_mem.embedding) == 1024


@pytest.mark.asyncio
async def test_create_memory_embedding_values(auth_client: AsyncClient):
    """Verify embedding elements are valid floating point numbers."""
    with patch(
        "app.services.memory_service.get_embedding_provider"
    ) as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=list(DUMMY_1024_VEC))
        mock_get_provider.return_value = mock_provider

        resp = await auth_client.post(
            "/api/memories",
            json={
                "category": "identity",
                "key": "role",
                "content": "Senior Software Architect",
            },
        )
        assert resp.status_code == 201
        mem_id = resp.json()["id"]

        async with TestSession() as session:
            db_mem = await session.scalar(select(Memory).where(Memory.id == mem_id))
            assert db_mem is not None
            assert isinstance(db_mem.embedding, list)
            assert all(isinstance(val, float) for val in db_mem.embedding)
            assert len(db_mem.embedding) == 1024


# ────────────────────── 3: Failure Preserves Memory ──────────────────────

@pytest.mark.asyncio
async def test_create_memory_embedding_failure_preserves_memory(auth_client: AsyncClient):
    """When EmbeddingProvider fails, Memory record is preserved and embedding is NULL."""
    with patch(
        "app.services.memory_service.get_embedding_provider"
    ) as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(
            side_effect=EmbeddingCommunicationError("DashScope upstream timeout")
        )
        mock_get_provider.return_value = mock_provider

        resp = await auth_client.post(
            "/api/memories",
            json={
                "category": "task",
                "key": "backup_db",
                "content": "Perform cold database backup at 2am.",
            },
        )
        # HTTP response should still succeed (201 Created)
        assert resp.status_code == 201
        mem_id = resp.json()["id"]

        # Verify Memory exists in DB and embedding is NULL
        async with TestSession() as session:
            db_mem = await session.scalar(select(Memory).where(Memory.id == mem_id))
            assert db_mem is not None
            assert db_mem.content == "Perform cold database backup at 2am."
            assert db_mem.embedding is None


# ────────────────────── 4: Client Embedding Override Protection ──────────────────────

@pytest.mark.asyncio
async def test_create_memory_does_not_accept_client_embedding(auth_client: AsyncClient):
    """Client cannot supply or override embedding vector; server generates or ignores it."""
    client_fake_vector = [999.99] * 1024

    with patch(
        "app.services.memory_service.get_embedding_provider"
    ) as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=list(DUMMY_1024_VEC))
        mock_get_provider.return_value = mock_provider

        resp = await auth_client.post(
            "/api/memories",
            json={
                "category": "preference",
                "key": "ai_model",
                "content": "Prefers Claude and Qwen for coding tasks",
                "embedding": client_fake_vector,
            },
        )
        # Request succeeds, but client_fake_vector must NOT be saved
        assert resp.status_code == 201
        mem_id = resp.json()["id"]

        async with TestSession() as session:
            db_mem = await session.scalar(select(Memory).where(Memory.id == mem_id))
            assert db_mem is not None
            # Server generated vector must be used, NOT the client's 999.99
            assert db_mem.embedding != client_fake_vector
            assert db_mem.embedding[0] == pytest.approx(DUMMY_1024_VEC[0])


# ────────────────────── 5 & 6: Update Re-embedding Triggers ──────────────────────

@pytest.mark.asyncio
async def test_update_memory_content_regenerates_embedding(auth_client: AsyncClient):
    """Updating memory content triggers re-embedding with new content."""
    with patch(
        "app.services.memory_service.get_embedding_provider"
    ) as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=list(DUMMY_1024_VEC))
        mock_get_provider.return_value = mock_provider

        # 1. Create
        create_resp = await auth_client.post(
            "/api/memories",
            json={
                "category": "preference",
                "key": "framework",
                "content": "Learning FastAPI with Python",
            },
        )
        assert create_resp.status_code == 201
        mem_id = create_resp.json()["id"]
        assert mock_provider.embed.await_count == 1

        # 2. Update content
        mock_provider.embed.reset_mock()
        mock_provider.embed.return_value = list(DUMMY_1024_VEC_UPDATED)

        update_resp = await auth_client.put(
            f"/api/memories/{mem_id}",
            json={"content": "Learning Next.js and FastAPI together"},
        )
        assert update_resp.status_code == 200

        # Must re-embed once with updated content
        mock_provider.embed.assert_awaited_once_with(
            "Learning Next.js and FastAPI together"
        )

        async with TestSession() as session:
            db_mem = await session.scalar(select(Memory).where(Memory.id == mem_id))
            assert db_mem is not None
            assert db_mem.content == "Learning Next.js and FastAPI together"
            assert db_mem.embedding[0] == pytest.approx(DUMMY_1024_VEC_UPDATED[0])


@pytest.mark.asyncio
async def test_update_memory_non_content_does_not_regenerate_embedding(
    auth_client: AsyncClient,
):
    """Updating non-content fields (importance, confidence, tags) does NOT call Embedding API."""
    with patch(
        "app.services.memory_service.get_embedding_provider"
    ) as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=list(DUMMY_1024_VEC))
        mock_get_provider.return_value = mock_provider

        # 1. Create
        create_resp = await auth_client.post(
            "/api/memories",
            json={
                "category": "task",
                "key": "review_pr",
                "content": "Review pull request for pgvector support",
            },
        )
        assert create_resp.status_code == 201
        mem_id = create_resp.json()["id"]
        assert mock_provider.embed.await_count == 1

        # 2. Update only non-content fields
        mock_provider.embed.reset_mock()

        update_resp = await auth_client.put(
            f"/api/memories/{mem_id}",
            json={
                "importance": 0.95,
                "confidence": 0.99,
                "tags": "pgvector,database,critical",
            },
        )
        assert update_resp.status_code == 200

        # Embedding API must NOT be called
        assert mock_provider.embed.await_count == 0


# ────────────────────── 7: Deletion Cleanup ──────────────────────

@pytest.mark.asyncio
async def test_delete_memory_removes_embedding(auth_client: AsyncClient):
    """Deleting memory cleans up both memory and its vector without orphan records."""
    with patch(
        "app.services.memory_service.get_embedding_provider"
    ) as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=list(DUMMY_1024_VEC))
        mock_get_provider.return_value = mock_provider

        # Create
        create_resp = await auth_client.post(
            "/api/memories",
            json={
                "category": "context",
                "key": "temp_note",
                "content": "Temporary note to be deleted",
            },
        )
        assert create_resp.status_code == 201
        mem_id = create_resp.json()["id"]

        # Verify exists in DB
        async with TestSession() as session:
            mem = await session.scalar(select(Memory).where(Memory.id == mem_id))
            assert mem is not None
            assert mem.embedding is not None

        # Delete
        del_resp = await auth_client.delete(f"/api/memories/{mem_id}")
        assert del_resp.status_code == 204

        # Confirm gone from DB
        async with TestSession() as session:
            mem = await session.scalar(select(Memory).where(Memory.id == mem_id))
            assert mem is None


# ────────────────────── 8: Existing CRUD Regression ──────────────────────

@pytest.mark.asyncio
async def test_existing_memory_crud_regression(auth_client: AsyncClient):
    """Ensure standard CRUD, filtering, and export work without regressions."""
    # Create
    c_resp = await auth_client.post(
        "/api/memories",
        json={
            "category": "task",
            "key": "regression_test",
            "content": "Standard regression test content",
        },
    )
    assert c_resp.status_code == 201
    mem_id = c_resp.json()["id"]

    # Get
    g_resp = await auth_client.get(f"/api/memories/{mem_id}")
    assert g_resp.status_code == 200
    assert g_resp.json()["key"] == "regression_test"

    # List
    l_resp = await auth_client.get("/api/memories?category=task")
    assert l_resp.status_code == 200
    assert any(m["id"] == mem_id for m in l_resp.json())


# ────────────────────── 9: User Isolation ──────────────────────

@pytest.mark.asyncio
async def test_user_isolation_embedding_protection(
    client: AsyncClient, auth_client: AsyncClient
):
    """Verify User B cannot access, update, or delete User A's memory."""
    with patch(
        "app.services.memory_service.get_embedding_provider"
    ) as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=list(DUMMY_1024_VEC))
        mock_get_provider.return_value = mock_provider

        # User A creates memory
        resp_a = await auth_client.post(
            "/api/memories",
            json={
                "category": "preference",
                "key": "private_pref",
                "content": "User A secret preference",
            },
        )
        assert resp_a.status_code == 201
        mem_a_id = resp_a.json()["id"]

    # Register and login User B
    resp_b_reg = await client.post(
        "/api/auth/register",
        json={
            "email": "user_b@example.com",
            "password": "passwordB123!",
            "display_name": "User B",
        },
    )
    assert resp_b_reg.status_code == 201
    token_b = resp_b_reg.json()["access_token"]
    user_b_headers = {"Authorization": f"Bearer {token_b}"}

    # User B cannot read User A's memory
    get_b = await client.get(f"/api/memories/{mem_a_id}", headers=user_b_headers)
    assert get_b.status_code == 404

    # User B cannot update User A's memory
    put_b = await client.put(
        f"/api/memories/{mem_a_id}",
        json={"content": "Tampered by User B"},
        headers=user_b_headers,
    )
    assert put_b.status_code == 404

    # User B cannot delete User A's memory
    del_b = await client.delete(f"/api/memories/{mem_a_id}", headers=user_b_headers)
    assert del_b.status_code == 404


# ────────────────────── 10: Real DashScope E2E Integration ──────────────────────

@pytest.mark.asyncio
async def test_real_create_memory_with_dashscope_embedding_if_key_available():
    """Live E2E test against PostgreSQL container and real DashScope embedding API."""
    api_key = settings.get_embedding_api_key()
    if not api_key:
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("LLM_API_KEY=") or line.strip().startswith(
                    "DASHSCOPE_API_KEY="
                ):
                    api_key = line.split("=", 1)[1].strip()
                    break

    if not api_key:
        pytest.skip("No DashScope API key available; skipping real embedding E2E test")

    pg_url = "postgresql+asyncpg://memory_passport:dev_pg_password_123@127.0.0.1:5432/memory_passport"
    pg_engine = create_async_engine(pg_url)
    PgSession = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

    provider = DashScopeEmbeddingProvider(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen3.7-text-embedding-flash",
        dimensions=1024,
    )

    test_user_id = None
    test_mem_id = None

    try:
        async with PgSession() as session:
            # 1. Create a test user in PostgreSQL container
            test_user = User(
                email="e2e_test_user@example.com",
                hashed_password="hashed_test_password",
                passport_id="mp_e2etest0001",
                display_name="E2E Test User",
            )
            session.add(test_user)
            await session.commit()
            await session.refresh(test_user)
            test_user_id = test_user.id

            # 2. Create memory with real DashScope embedding
            memory_data = MemoryCreate(
                category="preference",
                key="ai_focus",
                content="我正在学习 AI Agent、RAG 和自动化工作流。",
            )
            mem = await memory_service.create_memory(
                session,
                test_user_id,
                memory_data,
                embedding_provider=provider,
            )
            await session.commit()
            test_mem_id = mem.id

            # 3. Direct SQL query on PostgreSQL
            result = await session.execute(
                text("SELECT id, content, embedding FROM memories WHERE id = :id"),
                {"id": test_mem_id},
            )
            row = result.fetchone()
            assert row is not None, "Memory must exist in PostgreSQL"
            assert row.content == "我正在学习 AI Agent、RAG 和自动化工作流。"

            # Verify embedding from PostgreSQL raw SQL
            embedding_val = row.embedding
            assert embedding_val is not None, "Embedding column in PostgreSQL must not be NULL"
            if isinstance(embedding_val, str):
                vec_list = [float(x.strip()) for x in embedding_val.strip("[]").split(",") if x.strip()]
            else:
                vec_list = [float(x) for x in embedding_val]
            assert len(vec_list) == 1024, f"Expected 1024 dimensions, got {len(vec_list)}"
            assert all(isinstance(x, float) for x in vec_list)

            # Check non-zero magnitude
            magnitude = sum(x * x for x in vec_list)
            assert magnitude > 0.0, "Vector magnitude must be greater than 0"

            # 4. Verify via SQLAlchemy ORM model query
            orm_mem = await session.scalar(select(Memory).where(Memory.id == test_mem_id))
            assert orm_mem is not None
            assert orm_mem.embedding is not None
            assert len(orm_mem.embedding) == 1024
            assert all(isinstance(x, float) for x in orm_mem.embedding)


    finally:
        # Cleanup test data to ensure clean state
        async with PgSession() as session:
            if test_mem_id:
                await session.execute(
                    text("DELETE FROM memories WHERE id = :id"), {"id": test_mem_id}
                )
            if test_user_id:
                await session.execute(
                    text("DELETE FROM users WHERE id = :id"), {"id": test_user_id}
                )
            await session.commit()

            # Confirm cleanup
            if test_mem_id:
                check = await session.execute(
                    text("SELECT count(*) FROM memories WHERE id = :id"),
                    {"id": test_mem_id},
                )
                assert check.scalar() == 0, "Test memory must be deleted"
            if test_user_id:
                check_u = await session.execute(
                    text("SELECT count(*) FROM users WHERE id = :id"),
                    {"id": test_user_id},
                )
                assert check_u.scalar() == 0, "Test user must be deleted"

        await pg_engine.dispose()

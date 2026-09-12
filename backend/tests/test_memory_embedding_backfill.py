"""Phase 2.3F: Historical Memory Embedding Backfill and Retry tests against PostgreSQL + pgvector."""

import logging
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.memory import Memory
from app.models.user import User
from app.providers.embedding_provider import (
    EmbeddingCommunicationError,
    EmbeddingProvider,
)
from app.services.backfill_service import MemoryEmbeddingBackfillService

PG_URL = "postgresql+asyncpg://memory_passport:dev_pg_password_123@127.0.0.1:5432/memory_passport"


def get_pg_engine():
    return create_async_engine(PG_URL)


def make_vector(val: float) -> list[float]:
    """Create a 1024-dim test vector."""
    return [float(val)] * 1024


@pytest_asyncio.fixture
async def pg_session():
    """Async PostgreSQL session fixture that cleans up created test users and memories."""
    engine = get_pg_engine()
    PgSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    created_user_ids = []

    async with PgSession() as session:
        yield session, created_user_ids

    # Cleanup after test
    async with PgSession() as cleanup_session:
        for uid in created_user_ids:
            await cleanup_session.execute(
                text("DELETE FROM memories WHERE user_id = :uid"), {"uid": uid}
            )
            await cleanup_session.execute(
                text("DELETE FROM users WHERE id = :uid"), {"uid": uid}
            )
        await cleanup_session.commit()

    await engine.dispose()


async def create_test_user(session: AsyncSession, prefix: str, user_ids: list[str]) -> User:
    import uuid

    u = User(
        email=f"{prefix}_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed_test_pw",
        passport_id=f"mp_{uuid.uuid4().hex[:12]}",
        display_name=f"User {prefix}",
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    user_ids.append(u.id)
    return u


# ────────────────────── 1 & 2: Process Only NULL & Don't Re-embed ──────────────────────

@pytest.mark.asyncio
async def test_backfill_only_processes_null_embeddings(pg_session):
    """Backfill only processes memories WHERE embedding IS NULL."""
    session, user_ids = pg_session
    user = await create_test_user(session, "null_only", user_ids)

    # 1 memory with existing vector, 2 memories with NULL vector
    existing_vec = make_vector(0.5)
    m1 = Memory(user_id=user.id, key="m1", content="Has vector", embedding=existing_vec)
    m2 = Memory(user_id=user.id, key="m2", content="Null vector 1", embedding=None)
    m3 = Memory(user_id=user.id, key="m3", content="Null vector 2", embedding=None)
    session.add_all([m1, m2, m3])
    await session.commit()

    mock_provider = AsyncMock(spec=EmbeddingProvider)
    mock_provider.embed = AsyncMock(return_value=make_vector(0.1))

    service = MemoryEmbeddingBackfillService(session, embedding_provider=mock_provider)
    stats = await service.backfill(user_id=user.id, batch_size=10)

    assert stats.total_candidates == 2
    assert stats.processed == 2
    assert stats.succeeded == 2
    assert stats.remaining == 0

    # Provider should have been called ONLY for m2 and m3 (not m1)
    called_contents = [call.args[0] for call in mock_provider.embed.call_args_list]
    assert "Has vector" not in called_contents
    assert "Null vector 1" in called_contents
    assert "Null vector 2" in called_contents


@pytest.mark.asyncio
async def test_backfill_does_not_reembed_existing_embeddings(pg_session):
    """Backfill never overwrites or re-calculates already embedded memories."""
    session, user_ids = pg_session
    user = await create_test_user(session, "no_reembed", user_ids)

    original_vec = make_vector(0.77)
    m = Memory(user_id=user.id, key="orig", content="Original content", embedding=original_vec)
    session.add(m)
    await session.commit()
    mem_id = m.id

    mock_provider = AsyncMock(spec=EmbeddingProvider)
    service = MemoryEmbeddingBackfillService(session, embedding_provider=mock_provider)
    stats = await service.backfill(user_id=user.id, batch_size=10)

    assert stats.total_candidates == 0
    assert stats.processed == 0
    assert mock_provider.embed.call_count == 0

    # Vector in DB must be exactly unchanged
    refetched = await session.scalar(select(Memory).where(Memory.id == mem_id))
    assert list(refetched.embedding) == pytest.approx(original_vec)


# ────────────────────── 3: Valid 1024-dim Embedding Written ──────────────────────

@pytest.mark.asyncio
async def test_backfill_writes_valid_1024_embedding(pg_session):
    """Backfill writes a verified 1024-dimension float vector to PostgreSQL pgvector."""
    session, user_ids = pg_session
    user = await create_test_user(session, "valid_dim", user_ids)

    m = Memory(user_id=user.id, key="unembedded", content="Needs 1024 vector", embedding=None)
    session.add(m)
    await session.commit()
    mem_id = m.id

    expected_vec = [float(i % 100) / 100.0 for i in range(1024)]
    mock_provider = AsyncMock(spec=EmbeddingProvider)
    mock_provider.embed = AsyncMock(return_value=expected_vec)

    service = MemoryEmbeddingBackfillService(session, embedding_provider=mock_provider)
    stats = await service.backfill(user_id=user.id, batch_size=10)

    assert stats.succeeded == 1
    assert stats.remaining == 0

    # Direct query to verify pgvector column
    refetched = await session.scalar(select(Memory).where(Memory.id == mem_id))
    assert refetched.embedding is not None
    vec = list(refetched.embedding)
    assert len(vec) == 1024
    assert all(isinstance(x, float) for x in vec)
    assert vec[0] == pytest.approx(expected_vec[0])


# ────────────────────── 4: Batch Limit Control ──────────────────────

@pytest.mark.asyncio
async def test_backfill_batch_limit(pg_session):
    """Backfill respects batch_size boundary and processes at most batch_size records."""
    session, user_ids = pg_session
    user = await create_test_user(session, "batch_limit", user_ids)

    # Create 5 memories with NULL embedding
    for i in range(5):
        session.add(Memory(user_id=user.id, key=f"k_{i}", content=f"Batch test item {i}", embedding=None))
    await session.commit()

    mock_provider = AsyncMock(spec=EmbeddingProvider)
    mock_provider.embed = AsyncMock(return_value=make_vector(0.2))

    service = MemoryEmbeddingBackfillService(session, embedding_provider=mock_provider)
    # Request batch_size=2
    stats = await service.backfill(user_id=user.id, batch_size=2)

    assert stats.total_candidates == 5
    assert stats.processed == 2
    assert stats.succeeded == 2
    assert stats.remaining == 3
    assert mock_provider.embed.call_count == 2


# ────────────────────── 5: Failure Preserves NULL Embedding ──────────────────────

@pytest.mark.asyncio
async def test_backfill_failure_preserves_null_embedding(pg_session):
    """On embedding provider failure, memory is preserved and embedding remains NULL."""
    session, user_ids = pg_session
    user = await create_test_user(session, "fail_preserve", user_ids)

    m = Memory(user_id=user.id, key="fail_mem", content="Critical user note", embedding=None)
    session.add(m)
    await session.commit()
    mem_id = m.id

    mock_provider = AsyncMock(spec=EmbeddingProvider)
    mock_provider.embed = AsyncMock(side_effect=EmbeddingCommunicationError("Network timeout"))

    service = MemoryEmbeddingBackfillService(session, embedding_provider=mock_provider)
    stats = await service.backfill(user_id=user.id, batch_size=10)

    assert stats.processed == 1
    assert stats.succeeded == 0
    assert stats.failed == 1
    assert stats.remaining == 1

    # Memory still exists, content intact, embedding is NULL
    refetched = await session.scalar(select(Memory).where(Memory.id == mem_id))
    assert refetched is not None
    assert refetched.content == "Critical user note"
    assert refetched.embedding is None


# ────────────────────── 6 & 7: Retry & Idempotency ──────────────────────

@pytest.mark.asyncio
async def test_backfill_retry_only_processes_failed_records(pg_session):
    """Failed records can be retried; successful records are not re-processed."""
    session, user_ids = pg_session
    user = await create_test_user(session, "retry_test", user_ids)

    m1 = Memory(user_id=user.id, key="m1", content="Content 1", embedding=None)
    m2 = Memory(user_id=user.id, key="m2", content="Content 2", embedding=None)
    session.add_all([m1, m2])
    await session.commit()

    # Pass 1: m1 succeeds, m2 fails
    mock_provider = AsyncMock(spec=EmbeddingProvider)
    mock_provider.embed = AsyncMock(side_effect=[make_vector(0.1), EmbeddingCommunicationError("Timeout")])

    service = MemoryEmbeddingBackfillService(session, embedding_provider=mock_provider)
    pass1 = await service.backfill(user_id=user.id, batch_size=10)

    assert pass1.processed == 2
    assert pass1.succeeded == 1
    assert pass1.failed == 1
    assert pass1.remaining == 1

    # Pass 2 (Retry): m2 now succeeds
    mock_provider.embed.reset_mock()
    mock_provider.embed.side_effect = [make_vector(0.2)]

    pass2 = await service.backfill(user_id=user.id, batch_size=10)

    assert pass2.total_candidates == 1
    assert pass2.processed == 1
    assert pass2.succeeded == 1
    assert pass2.failed == 0
    assert pass2.remaining == 0

    # Provider was called ONLY with Content 2 during retry
    mock_provider.embed.assert_awaited_once_with("Content 2")


@pytest.mark.asyncio
async def test_backfill_is_idempotent(pg_session):
    """Running backfill multiple times after completion has zero effect."""
    session, user_ids = pg_session
    user = await create_test_user(session, "idempotent", user_ids)

    m = Memory(user_id=user.id, key="idem", content="Idempotent content", embedding=None)
    session.add(m)
    await session.commit()

    mock_provider = AsyncMock(spec=EmbeddingProvider)
    mock_provider.embed = AsyncMock(return_value=make_vector(0.33))

    service = MemoryEmbeddingBackfillService(session, embedding_provider=mock_provider)
    # Run 1: backfills memory
    r1 = await service.backfill(user_id=user.id, batch_size=10)
    assert r1.succeeded == 1
    assert r1.remaining == 0

    # Run 2: already backfilled
    mock_provider.embed.reset_mock()
    r2 = await service.backfill(user_id=user.id, batch_size=10)
    assert r2.total_candidates == 0
    assert r2.processed == 0
    assert r2.remaining == 0
    assert mock_provider.embed.call_count == 0


# ────────────────────── 8: User Isolation ──────────────────────

@pytest.mark.asyncio
async def test_backfill_user_isolation(pg_session):
    """Backfilling User A's memories never touches or leaks User B's memories."""
    session, user_ids = pg_session
    user_a = await create_test_user(session, "user_a", user_ids)
    user_b = await create_test_user(session, "user_b", user_ids)

    mem_a = Memory(user_id=user_a.id, key="a_key", content="User A content", embedding=None)
    mem_b = Memory(user_id=user_b.id, key="b_key", content="User B secret content", embedding=None)
    session.add_all([mem_a, mem_b])
    await session.commit()

    mock_provider = AsyncMock(spec=EmbeddingProvider)
    mock_provider.embed = AsyncMock(return_value=make_vector(0.44))

    service = MemoryEmbeddingBackfillService(session, embedding_provider=mock_provider)
    stats_a = await service.backfill(user_id=user_a.id, batch_size=10)

    assert stats_a.total_candidates == 1
    assert stats_a.succeeded == 1
    assert stats_a.remaining == 0

    # Confirm only User A's content was embedded
    mock_provider.embed.assert_awaited_once_with("User A content")

    # User B's memory remains untouched and NULL
    refetched_b = await session.scalar(select(Memory).where(Memory.id == mem_b.id))
    assert refetched_b.embedding is None


# ────────────────────── 9: Memory Content Unchanged ──────────────────────

@pytest.mark.asyncio
async def test_backfill_does_not_modify_memory_content(pg_session):
    """Backfill only populates embedding; all other fields remain completely intact."""
    session, user_ids = pg_session
    user = await create_test_user(session, "content_intact", user_ids)

    mem = Memory(
        user_id=user.id,
        memory_type="identity",
        key="intact_key",
        content="Important immutable content",
        confidence=0.95,
        importance=0.88,
        tags="tag1,tag2",
        source="manual",
        embedding=None,
    )
    session.add(mem)
    await session.commit()
    mem_id = mem.id

    mock_provider = AsyncMock(spec=EmbeddingProvider)
    mock_provider.embed = AsyncMock(return_value=make_vector(0.12))

    service = MemoryEmbeddingBackfillService(session, embedding_provider=mock_provider)
    await service.backfill(user_id=user.id, batch_size=10)

    refetched = await session.scalar(select(Memory).where(Memory.id == mem_id))
    assert refetched.content == "Important immutable content"
    assert refetched.memory_type == "identity"
    assert refetched.key == "intact_key"
    assert refetched.confidence == 0.95
    assert refetched.importance == 0.88
    assert refetched.tags == "tag1,tag2"
    assert refetched.source == "manual"
    assert refetched.embedding is not None


# ────────────────────── 10: Statistics Accuracy ──────────────────────

@pytest.mark.asyncio
async def test_backfill_statistics_are_correct(pg_session):
    """Statistics accurately reflect candidates, processed, succeeded, failed, and remaining."""
    session, user_ids = pg_session
    user = await create_test_user(session, "stats_check", user_ids)

    # 5 memories total: 2 already embedded, 3 with NULL embedding
    session.add_all([
        Memory(user_id=user.id, key="e1", content="Embedded 1", embedding=make_vector(0.1)),
        Memory(user_id=user.id, key="e2", content="Embedded 2", embedding=make_vector(0.2)),
        Memory(user_id=user.id, key="n1", content="Null 1", embedding=None),
        Memory(user_id=user.id, key="n2", content="Null 2", embedding=None),
        Memory(user_id=user.id, key="n3", content="Null 3", embedding=None),
    ])
    await session.commit()

    # In batch of 2: first succeeds, second fails
    mock_provider = AsyncMock(spec=EmbeddingProvider)
    mock_provider.embed = AsyncMock(side_effect=[make_vector(0.3), EmbeddingCommunicationError("Fail")])

    service = MemoryEmbeddingBackfillService(session, embedding_provider=mock_provider)
    stats = await service.backfill(user_id=user.id, batch_size=2)

    assert stats.total_candidates == 3
    assert stats.processed == 2
    assert stats.succeeded == 1
    assert stats.failed == 1
    assert stats.remaining == 2


# ────────────────────── 11: Security & No Secret Logging ──────────────────────

@pytest.mark.asyncio
async def test_backfill_does_not_log_secrets(pg_session, caplog):
    """Exceptions containing API keys or secrets are never written to logs."""
    session, user_ids = pg_session
    user = await create_test_user(session, "no_secret_log", user_ids)

    session.add(Memory(user_id=user.id, key="sec", content="Secret test", embedding=None))
    await session.commit()

    secret_str = "sk-dashscope-super-secret-key-999888"
    mock_provider = AsyncMock(spec=EmbeddingProvider)
    mock_provider.embed = AsyncMock(
        side_effect=EmbeddingCommunicationError(f"Connection error with token {secret_str}")
    )

    service = MemoryEmbeddingBackfillService(session, embedding_provider=mock_provider)

    with caplog.at_level(logging.WARNING):
        await service.backfill(user_id=user.id, batch_size=10)

    # Verify secret string is NOT in any log record
    for record in caplog.records:
        assert secret_str not in record.message
        assert "Authorization" not in record.message


# ────────────────────── 12: Embedding Provider Boundary ──────────────────────

@pytest.mark.asyncio
async def test_backfill_respects_embedding_provider_boundary(pg_session):
    """Backfill strictly uses EmbeddingProvider.embed(content) and enforces dimension validation."""
    session, user_ids = pg_session
    user = await create_test_user(session, "boundary_check", user_ids)

    m = Memory(user_id=user.id, key="b1", content="Boundary content", embedding=None)
    session.add(m)
    await session.commit()

    # Provider returning wrong dimension (e.g. 512 instead of 1024)
    mock_provider = AsyncMock(spec=EmbeddingProvider)
    mock_provider.embed = AsyncMock(return_value=[0.1] * 512)

    service = MemoryEmbeddingBackfillService(session, embedding_provider=mock_provider)
    stats = await service.backfill(user_id=user.id, batch_size=10)

    assert stats.processed == 1
    assert stats.succeeded == 0
    assert stats.failed == 1
    assert stats.remaining == 1


# ────────────────────── 13 & 14: Protected API Endpoint & User Isolation ──────────────────────

@pytest.mark.asyncio
async def test_backfill_api_endpoint(auth_client: AsyncClient):
    """POST /api/memories/backfill endpoint works safely for authenticated user."""
    # 1. Create a memory (in test SQLite DB) with embedding=None
    c_resp = await auth_client.post(
        "/api/memories",
        json={"category": "preference", "key": "api_test", "content": "API backfill test memory"},
    )
    assert c_resp.status_code == 201
    mem_id = c_resp.json()["id"]
    assert mem_id is not None

    # 2. Call backfill API with mock provider
    with patch("app.services.backfill_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock(spec=EmbeddingProvider)
        mock_provider.embed = AsyncMock(return_value=[0.1] * 1024)
        mock_get_provider.return_value = mock_provider

        resp = await auth_client.post("/api/memories/backfill", json={"batch_size": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_candidates"] >= 1
        assert data["succeeded"] >= 1
        assert data["remaining"] == 0
        # Must NOT return embedding vector in API response
        assert "embedding" not in data


@pytest.mark.asyncio
async def test_backfill_api_user_isolation(client: AsyncClient, auth_client: AsyncClient):
    """User B cannot trigger backfill on User A's memories via API."""
    # User A creates a memory
    res_a = await auth_client.post(
        "/api/memories",
        json={"category": "context", "key": "ua_key", "content": "User A secret note"},
    )
    assert res_a.status_code == 201

    # Register User B
    reg_b = await client.post(
        "/api/auth/register",
        json={"email": "user_b_bk@example.com", "password": "PasswordB123!", "display_name": "User B"},
    )
    assert reg_b.status_code == 201
    headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}

    # User B calls backfill (User B has 0 memories)
    with patch("app.services.backfill_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock(spec=EmbeddingProvider)
        mock_provider.embed = AsyncMock(return_value=[0.1] * 1024)
        mock_get_provider.return_value = mock_provider

        resp_b = await client.post("/api/memories/backfill", json={"batch_size": 10}, headers=headers_b)
        assert resp_b.status_code == 200
        data_b = resp_b.json()
        assert data_b["total_candidates"] == 0
        assert data_b["processed"] == 0
        # Provider never called with User A's content
        assert mock_provider.embed.call_count == 0

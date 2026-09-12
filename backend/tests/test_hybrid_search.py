"""Phase 2.4: PostgreSQL FTS, GIN Index, and Hybrid Search tests."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from app.models.memory import Memory
from app.models.user import User
from app.providers.embedding_provider import EmbeddingCommunicationError
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.conftest import TestSession

PG_URL = "postgresql+asyncpg://memory_passport:dev_pg_password_123@127.0.0.1:5432/memory_passport"


def get_pg_engine():
    return create_async_engine(PG_URL)


def make_vector(base_val: float) -> list[float]:
    """Create a normalized 1024-dim test vector."""
    vec = [base_val] * 1024
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec] if norm > 0 else vec


# ────────────────────── 1: Keyword Search Exact Term ──────────────────────

@pytest.mark.asyncio
async def test_keyword_search_exact_term(auth_client: AsyncClient):
    """Keyword search matches exact term in Memory.content."""
    r1 = await auth_client.post(
        "/api/memories",
        json={"category": "preference", "key": "k1", "content": "我正在深入研究 FastAPI 异步框架"},
    )
    assert r1.status_code == 201

    r2 = await auth_client.post(
        "/api/memories",
        json={"category": "preference", "key": "k2", "content": "今天下午喝了一杯拿铁咖啡"},
    )
    assert r2.status_code == 201

    resp = await auth_client.post(
        "/api/memories/search",
        json={"query": "FastAPI", "search_mode": "keyword", "limit": 10},
    )
    assert resp.status_code == 200
    data = resp.json()
    items = data["items"]
    assert len(items) == 1
    assert items[0]["id"] == r1.json()["id"]
    assert items[0]["keyword_score"] == 1.0
    assert items[0]["similarity"] is None


# ────────────────────── 2: Keyword Search Partial Term ──────────────────────

@pytest.mark.asyncio
async def test_keyword_search_partial_term(auth_client: AsyncClient):
    """Keyword search matches partial term in Memory.content."""
    r = await auth_client.post(
        "/api/memories",
        json={"category": "preference", "key": "k1", "content": "我最近开始学习 Python 后端开发"},
    )
    assert r.status_code == 201

    resp = await auth_client.post(
        "/api/memories/search",
        json={"query": "后端", "search_mode": "keyword", "limit": 10},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == r.json()["id"]
    assert items[0]["keyword_score"] > 0.0


# ────────────────────── 3: Semantic Search Still Works ──────────────────────

@pytest.mark.asyncio
async def test_semantic_search_still_works(auth_client: AsyncClient):
    """Verify pure semantic search remains functional via search_mode='semantic'."""
    v1 = make_vector(1.0)
    v2 = [-x for x in v1]
    q_vec = list(v1)

    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(side_effect=[v1, v2, q_vec])
        mock_get_provider.return_value = mock_provider

        r1 = await auth_client.post(
            "/api/memories",
            json={"category": "preference", "key": "s1", "content": "Target semantic memory"},
        )
        await auth_client.post(
            "/api/memories",
            json={"category": "preference", "key": "s2", "content": "Unrelated text content"},
        )

        resp = await auth_client.post(
            "/api/memories/search",
            json={"query": "Semantic query", "search_mode": "semantic", "limit": 10},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["search_mode"] == "semantic"
        items = data["items"]
        assert len(items) == 2
        assert items[0]["id"] == r1.json()["id"]
        assert items[0]["similarity"] > items[1]["similarity"]
        assert items[0]["keyword_score"] is None


# ────────────────────── 4: Hybrid Search Combines Results ──────────────────────

@pytest.mark.asyncio
async def test_hybrid_search_combines_results(auth_client: AsyncClient):
    """Hybrid search fuses semantic similarity and keyword score."""
    vec_a = make_vector(1.0)
    vec_b = make_vector(0.7)
    q_vec = make_vector(1.0)

    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(side_effect=[vec_a, vec_b, q_vec])
        mock_get_provider.return_value = mock_provider

        r_a = await auth_client.post(
            "/api/memories",
            json={"category": "preference", "key": "a", "content": "我最近开始学习 Python 后端开发"},
        )
        await auth_client.post(
            "/api/memories",
            json={"category": "preference", "key": "b", "content": "我最近开始研究 Web 开发框架"},
        )

        resp = await auth_client.post(
            "/api/memories/search",
            json={"query": "Python 后端开发", "search_mode": "hybrid", "limit": 10},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["search_mode"] == "hybrid"
        items = data["items"]
        assert len(items) == 2
        top = items[0]
        assert top["id"] == r_a.json()["id"]
        assert top["similarity"] is not None
        assert top["keyword_score"] is not None
        assert top["hybrid_score"] is not None
        assert top["hybrid_score"] > items[1]["hybrid_score"]


# ────────────────────── 5: Hybrid Score Range ──────────────────────

@pytest.mark.asyncio
async def test_hybrid_score_range(auth_client: AsyncClient):
    """Verify all scores fall strictly within [0.0, 1.0]."""
    vec = make_vector(0.8)
    q_vec = make_vector(0.8)

    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(side_effect=[vec, q_vec])
        mock_get_provider.return_value = mock_provider

        await auth_client.post(
            "/api/memories",
            json={"category": "preference", "key": "k", "content": "Testing score bounds"},
        )

        resp = await auth_client.post(
            "/api/memories/hybrid-search",
            json={"query": "Testing score"},
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert 0.0 <= item["hybrid_score"] <= 1.0
            if item["similarity"] is not None:
                assert -1.0 <= item["similarity"] <= 1.0
            if item["keyword_score"] is not None:
                assert 0.0 <= item["keyword_score"] <= 1.0


# ────────────────────── 6: Hybrid Ordering ──────────────────────

@pytest.mark.asyncio
async def test_hybrid_ordering(auth_client: AsyncClient):
    """Results must strictly follow hybrid_score DESC with stable tie-breaking."""
    v1 = make_vector(0.9)
    v2 = make_vector(0.5)
    v3 = make_vector(0.2)
    q_vec = make_vector(1.0)

    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(side_effect=[v1, v2, v3, q_vec])
        mock_get_provider.return_value = mock_provider

        for i, text_c in enumerate(["Score alpha", "Score beta", "Score gamma"]):
            await auth_client.post(
                "/api/memories",
                json={"category": "preference", "key": f"k{i}", "content": text_c},
            )

        resp = await auth_client.post(
            "/api/memories/hybrid-search",
            json={"query": "Score alpha beta"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        scores = [item["hybrid_score"] for item in items]
        assert scores == sorted(scores, reverse=True), "Scores must be strictly descending"


# ────────────────────── 7: Semantic Only Match ──────────────────────

@pytest.mark.asyncio
async def test_semantic_only_match(auth_client: AsyncClient):
    """Memory with semantic match but zero keyword match is returned with keyword_score=None."""
    vec = make_vector(1.0)
    q_vec = make_vector(1.0)

    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(side_effect=[vec, q_vec])
        mock_get_provider.return_value = mock_provider

        r = await auth_client.post(
            "/api/memories",
            json={"category": "preference", "key": "k", "content": "The quick brown fox jumps over lazy dog"},
        )

        resp = await auth_client.post(
            "/api/memories/search",
            json={"query": "Completely different query words xyz", "search_mode": "hybrid"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == r.json()["id"]
        assert items[0]["similarity"] > 0.9
        assert items[0]["keyword_score"] is None
        assert items[0]["hybrid_score"] == pytest.approx(0.7 * items[0]["similarity"], abs=0.01)


# ────────────────────── 8: Keyword Only Match ──────────────────────

@pytest.mark.asyncio
async def test_keyword_only_match(auth_client: AsyncClient):
    """Memory without embedding (embedding IS NULL) matches keyword and is returned in hybrid search."""
    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(side_effect=EmbeddingCommunicationError("fail"))
        mock_get_provider.return_value = mock_provider

        r = await auth_client.post(
            "/api/memories",
            json={"category": "preference", "key": "k", "content": "Keyword target unique phrase"},
        )
        assert r.status_code == 201

    async with TestSession() as session:
        m = await session.get(Memory, r.json()["id"])
        assert m.embedding is None

    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=make_vector(1.0))
        mock_get_provider.return_value = mock_provider

        resp = await auth_client.post(
            "/api/memories/search",
            json={"query": "Keyword target unique phrase", "search_mode": "hybrid"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == r.json()["id"]
        assert items[0]["similarity"] is None
        assert items[0]["keyword_score"] == 1.0
        assert items[0]["hybrid_score"] == 0.3


# ────────────────────── 9: Zero Match ──────────────────────

@pytest.mark.asyncio
async def test_zero_match(auth_client: AsyncClient):
    """When neither keyword nor semantic match exists, return empty list."""
    vec = make_vector(1.0)
    q_vec = [-x for x in vec]

    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(side_effect=[vec, q_vec])
        mock_get_provider.return_value = mock_provider

        await auth_client.post(
            "/api/memories",
            json={"category": "preference", "key": "k", "content": "Totally unrelated content abc"},
        )

        resp = await auth_client.post(
            "/api/memories/hybrid-search",
            json={"query": "nonexistent term xyz"},
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == []


# ────────────────────── 10: Empty Query Rejected ──────────────────────

@pytest.mark.asyncio
async def test_empty_query_rejected(auth_client: AsyncClient):
    """Empty or whitespace-only query is rejected with 422."""
    r1 = await auth_client.post("/api/memories/search", json={"query": "", "search_mode": "hybrid"})
    assert r1.status_code == 422

    r2 = await auth_client.post("/api/memories/search", json={"query": "   ", "search_mode": "hybrid"})
    assert r2.status_code == 422

    r3 = await auth_client.post("/api/memories/hybrid-search", json={"query": ""})
    assert r3.status_code == 422


# ────────────────────── 11: User Isolation ──────────────────────

@pytest.mark.asyncio
async def test_user_isolation(auth_client: AsyncClient, client: AsyncClient):
    """User A cannot see User B memories via search."""
    r_a = await auth_client.post(
        "/api/memories",
        json={"category": "preference", "key": "k_a", "content": "User A secret content"},
    )

    reg_b = await client.post(
        "/api/auth/register",
        json={"email": "hybrid_iso_b@example.com", "password": "Pass123!", "display_name": "User B"},
    )
    assert reg_b.status_code == 201
    headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}

    r_b = await client.post(
        "/api/memories",
        json={"category": "preference", "key": "k_b", "content": "User B secret content"},
        headers=headers_b,
    )

    resp_a = await auth_client.post(
        "/api/memories/search",
        json={"query": "secret content", "search_mode": "keyword"},
    )
    assert resp_a.status_code == 200
    ids_a = [item["id"] for item in resp_a.json()["items"]]
    assert r_a.json()["id"] in ids_a
    assert r_b.json()["id"] not in ids_a


# ────────────────────── 12: Cross User Keyword Isolation ──────────────────────

@pytest.mark.asyncio
async def test_cross_user_keyword_isolation(auth_client: AsyncClient, client: AsyncClient):
    """User A: '我喜欢 Python', User B: 'Python 是我最喜欢的语言'. A searches Python -> only A returned."""
    r_a = await auth_client.post(
        "/api/memories",
        json={"category": "preference", "key": "k_a", "content": "我喜欢 Python"},
    )

    reg_b = await client.post(
        "/api/auth/register",
        json={"email": "kw_iso_b@example.com", "password": "Pass123!", "display_name": "User B"},
    )
    headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}

    r_b = await client.post(
        "/api/memories",
        json={"category": "preference", "key": "k_b", "content": "Python 是我最喜欢的语言"},
        headers=headers_b,
    )

    resp_a = await auth_client.post(
        "/api/memories/search",
        json={"query": "Python", "search_mode": "keyword"},
    )
    assert resp_a.status_code == 200
    items = resp_a.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == r_a.json()["id"]
    assert items[0]["id"] != r_b.json()["id"]


# ────────────────────── 13: Cross User Hybrid Isolation ──────────────────────

@pytest.mark.asyncio
async def test_cross_user_hybrid_isolation(auth_client: AsyncClient, client: AsyncClient):
    """Both users create 'Python 工程师', hybrid search never returns User B to User A."""
    vec = make_vector(1.0)
    q_vec = make_vector(1.0)

    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=vec)
        mock_get_provider.return_value = mock_provider

        r_a = await auth_client.post(
            "/api/memories",
            json={"category": "preference", "key": "eng_a", "content": "Python 工程师"},
        )

    reg_b = await client.post(
        "/api/auth/register",
        json={"email": "hybrid_cross_b@example.com", "password": "Pass123!", "display_name": "User B"},
    )
    headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}

    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=vec)
        mock_get_provider.return_value = mock_provider

        r_b = await client.post(
            "/api/memories",
            json={"category": "preference", "key": "eng_b", "content": "Python 工程师"},
            headers=headers_b,
        )

    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=q_vec)
        mock_get_provider.return_value = mock_provider

        resp_a = await auth_client.post(
            "/api/memories/hybrid-search",
            json={"query": "Python 工程师"},
        )
        assert resp_a.status_code == 200
        items = resp_a.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == r_a.json()["id"]
        assert items[0]["id"] != r_b.json()["id"]


# ────────────────────── 14: Existing Embedding Not Modified ──────────────────────

@pytest.mark.asyncio
async def test_existing_embedding_not_modified(auth_client: AsyncClient):
    """Searching must never alter or mutate memory embedding."""
    vec = make_vector(0.75)
    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=vec)
        mock_get_provider.return_value = mock_provider

        r = await auth_client.post(
            "/api/memories",
            json={"category": "preference", "key": "k", "content": "Immutable embedding test"},
        )
        mem_id = r.json()["id"]

    async with TestSession() as session:
        m_before = await session.get(Memory, mem_id)
        emb_before = list(m_before.embedding) if m_before.embedding else None

    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=vec)
        mock_get_provider.return_value = mock_provider

        await auth_client.post("/api/memories/search", json={"query": "Immutable", "search_mode": "hybrid"})
        await auth_client.post("/api/memories/search", json={"query": "embedding", "search_mode": "keyword"})
        await auth_client.post("/api/memories/hybrid-search", json={"query": "test"})

    async with TestSession() as session:
        m_after = await session.get(Memory, mem_id)
        emb_after = list(m_after.embedding) if m_after.embedding else None

    assert emb_before == emb_after


# ────────────────────── 15: Existing Semantic Search Regression ──────────────────────

@pytest.mark.asyncio
async def test_existing_semantic_search_regression(auth_client: AsyncClient):
    """POST /api/memories/search without search_mode defaults to semantic search."""
    vec = make_vector(1.0)
    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=vec)
        mock_get_provider.return_value = mock_provider

        await auth_client.post(
            "/api/memories",
            json={"category": "preference", "key": "k", "content": "Semantic regression test"},
        )

        resp = await auth_client.post(
            "/api/memories/search",
            json={"query": "Semantic regression", "limit": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["search_mode"] == "semantic"
        items = data["items"]
        assert len(items) == 1
        assert items[0]["similarity"] is not None
        assert items[0]["keyword_score"] is None


# ────────────────────── 16: FTS Index Exists ──────────────────────

@pytest.mark.asyncio
async def test_fts_index_exists():
    """Verify PostgreSQL GIN index on to_tsvector('simple', content) exists."""
    engine = get_pg_engine()
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE tablename = 'memories' AND indexname = 'ix_memories_content_fts';"
                )
            )
            row = result.fetchone()
            assert row is not None, "GIN index 'ix_memories_content_fts' must exist on memories table"
            assert "gin" in row.indexdef.lower(), "Index definition must specify USING gin"
            assert "to_tsvector" in row.indexdef.lower(), "Index must use to_tsvector"
    finally:
        await engine.dispose()


# ────────────────────── 17: FTS Migration Idempotent ──────────────────────

@pytest.mark.asyncio
async def test_fts_migration_idempotent():
    """Executing 003_add_memory_fts_index.sql multiple times must not raise errors."""
    migration_path = Path("migrations/003_add_memory_fts_index.sql")
    if not migration_path.exists():
        migration_path = Path("backend/migrations/003_add_memory_fts_index.sql")
    assert migration_path.exists(), "Migration file 003_add_memory_fts_index.sql must exist"

    sql_content = migration_path.read_text(encoding="utf-8-sig")
    engine = get_pg_engine()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(sql_content))
            await conn.execute(text(sql_content))
    finally:
        await engine.dispose()


# ────────────────────── 18: FTS Migration Does Not Modify Data ──────────────────────

@pytest.mark.asyncio
async def test_fts_migration_does_not_modify_data():
    """Applying FTS migration must preserve existing memory count, content, and embeddings."""
    engine = get_pg_engine()
    PgSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    test_user_id = None
    test_mem_id = None

    try:
        async with PgSession() as session:
            user = User(
                email="fts_data_integrity@example.com",
                hashed_password="dummy_password",
                passport_id="mp_fts_integrity_01",
                display_name="FTS Integrity User",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            test_user_id = user.id

            sample_vec = [0.02 * (i % 50) for i in range(1024)]
            mem = Memory(
                user_id=test_user_id,
                memory_type="context",
                key="fts_integrity_key",
                content="FTS data integrity preservation test.",
                embedding=sample_vec,
            )
            session.add(mem)
            await session.commit()
            test_mem_id = mem.id

        # Record before
        async with engine.connect() as conn:
            cnt_before = (await conn.execute(text("SELECT count(*) FROM memories"))).scalar()
            row_before = (
                await conn.execute(
                    text("SELECT content, embedding FROM memories WHERE id = :id"),
                    {"id": test_mem_id},
                )
            ).fetchone()

        # Re-run migration
        migration_path = Path("migrations/003_add_memory_fts_index.sql")
        if not migration_path.exists():
            migration_path = Path("backend/migrations/003_add_memory_fts_index.sql")
        sql_content = migration_path.read_text(encoding="utf-8-sig")
        async with engine.begin() as conn:
            await conn.execute(text(sql_content))

        # Record after
        async with engine.connect() as conn:
            cnt_after = (await conn.execute(text("SELECT count(*) FROM memories"))).scalar()
            row_after = (
                await conn.execute(
                    text("SELECT content, embedding FROM memories WHERE id = :id"),
                    {"id": test_mem_id},
                )
            ).fetchone()

        assert cnt_before == cnt_after, "Memory count must be unchanged"
        assert row_before.content == row_after.content, "Content must be unchanged"
        assert row_before.embedding == row_after.embedding, "Embedding must be unchanged"

    finally:
        async with PgSession() as session:
            if test_mem_id:
                await session.execute(text("DELETE FROM memories WHERE id = :id"), {"id": test_mem_id})
            if test_user_id:
                await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": test_user_id})
            await session.commit()
        await engine.dispose()

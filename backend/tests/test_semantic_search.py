"""Phase 2.3D: PostgreSQL + pgvector Semantic Search tests."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text
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


def make_vector(base_val: float) -> list[float]:
    """Helper to create a normalized 1024-dim test vector."""
    vec = [base_val] * 1024
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec] if norm > 0 else vec


# ────────────────────── 1: Similar Memory Ranking ──────────────────────

@pytest.mark.asyncio
async def test_semantic_search_returns_similar_memories(auth_client: AsyncClient):
    """Memory A (semantically aligned) ranks higher than Memory B (unrelated)."""
    # Vectors:
    # Query vector is aligned with Memory A
    vec_a = make_vector(1.0)
    vec_b = [-x for x in vec_a]  # opposite direction
    query_vec = list(vec_a)

    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(side_effect=[vec_a, vec_b, query_vec])
        mock_get_provider.return_value = mock_provider

        # Create Memory A
        res_a = await auth_client.post(
            "/api/memories",
            json={"category": "preference", "key": "k1", "content": "我正在学习 AI Agent 和 LangGraph。"},
        )
        assert res_a.status_code == 201

        # Create Memory B
        res_b = await auth_client.post(
            "/api/memories",
            json={"category": "preference", "key": "k2", "content": "今天买了苹果和牛奶。"},
        )
        assert res_b.status_code == 201

        # Search
        search_res = await auth_client.post(
            "/api/memories/search",
            json={"query": "我最近学习人工智能 Agent 的记录", "limit": 10},
        )
        assert search_res.status_code == 200
        data = search_res.json()
        items = data["items"]
        assert len(items) == 2
        assert items[0]["content"] == "我正在学习 AI Agent 和 LangGraph。"
        assert items[0]["similarity"] > items[1]["similarity"]


# ────────────────────── 2: Similarity Descending Order ──────────────────────

@pytest.mark.asyncio
async def test_semantic_search_similarity_order(auth_client: AsyncClient):
    """Results must strictly follow similarity DESC."""
    q_vec = make_vector(1.0)
    v1 = make_vector(0.9)
    v2 = make_vector(0.5)
    v3 = make_vector(0.1)

    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(side_effect=[v1, v2, v3, q_vec])
        mock_get_provider.return_value = mock_provider

        for i, text_content in enumerate(["High match", "Medium match", "Low match"]):
            await auth_client.post(
                "/api/memories",
                json={"category": "preference", "key": f"k_{i}", "content": text_content},
            )

        resp = await auth_client.post(
            "/api/memories/search",
            json={"query": "target query", "limit": 10},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 3

        scores = [item["similarity"] for item in items]
        assert scores == sorted(scores, reverse=True), "Scores must be descending"


# ────────────────────── 3: Limit Enforcement ──────────────────────

@pytest.mark.asyncio
async def test_semantic_search_limit(auth_client: AsyncClient):
    """Limit parameter restricts returned results count."""
    q_vec = make_vector(1.0)
    vectors = [make_vector(float(i + 1)) for i in range(12)]

    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(side_effect=vectors + [q_vec])
        mock_get_provider.return_value = mock_provider

        for i in range(12):
            await auth_client.post(
                "/api/memories",
                json={"category": "task", "key": f"task_{i}", "content": f"Task content number {i}"},
            )

        resp = await auth_client.post(
            "/api/memories/search",
            json={"query": "find tasks", "limit": 3},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 3
        assert data["limit"] == 3


# ────────────────────── 4 & 5: Empty & Whitespace Query Validation ──────────────────────

@pytest.mark.asyncio
async def test_semantic_search_empty_query(auth_client: AsyncClient):
    """Empty query string is rejected with 422 Unprocessable Entity."""
    resp = await auth_client.post(
        "/api/memories/search",
        json={"query": "", "limit": 10},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_semantic_search_whitespace_query(auth_client: AsyncClient):
    """Whitespace-only query string is rejected with 422 Unprocessable Entity."""
    resp = await auth_client.post(
        "/api/memories/search",
        json={"query": "      ", "limit": 10},
    )
    assert resp.status_code == 422


# ────────────────────── 6: Exclude NULL Embeddings ──────────────────────

@pytest.mark.asyncio
async def test_semantic_search_excludes_null_embeddings(auth_client: AsyncClient):
    """Memories without embedding (embedding IS NULL) must never be returned."""
    vec_valid = make_vector(1.0)
    q_vec = make_vector(1.0)

    # 1. Create Memory A with embedding
    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=vec_valid)
        mock_get_provider.return_value = mock_provider

        res_a = await auth_client.post(
            "/api/memories",
            json={"category": "preference", "key": "has_vec", "content": "Memory with embedding"},
        )
        assert res_a.status_code == 201

    # 2. Create Memory B without embedding (auto_embed=False or simulated failure)
    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(side_effect=EmbeddingCommunicationError("fail"))
        mock_get_provider.return_value = mock_provider

        res_b = await auth_client.post(
            "/api/memories",
            json={"category": "preference", "key": "no_vec", "content": "Memory without embedding"},
        )
        assert res_b.status_code == 201

    # Verify Memory B has NULL embedding in DB
    async with TestSession() as session:
        b_mem = await session.get(Memory, res_b.json()["id"])
        assert b_mem.embedding is None

    # 3. Search
    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=q_vec)
        mock_get_provider.return_value = mock_provider

        resp = await auth_client.post(
            "/api/memories/search",
            json={"query": "Memory", "limit": 10},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == res_a.json()["id"]


# ────────────────────── 7: Strict User Isolation ──────────────────────

@pytest.mark.asyncio
async def test_semantic_search_user_isolation(client: AsyncClient, auth_client: AsyncClient):
    """User A's search query NEVER returns User B's memories under any circumstances."""
    vec = make_vector(1.0)
    q_vec = make_vector(1.0)

    # User A creates memory
    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=vec)
        mock_get_provider.return_value = mock_provider

        res_a = await auth_client.post(
            "/api/memories",
            json={"category": "context", "key": "k_a", "content": "我的 AI Agent 学习记录"},
        )
        assert res_a.status_code == 201
        mem_a_id = res_a.json()["id"]

    # User B registers and creates identical memory
    reg_b = await client.post(
        "/api/auth/register",
        json={"email": "user_b_search@example.com", "password": "PassWord123!", "display_name": "User B"},
    )
    assert reg_b.status_code == 201
    headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}

    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=vec)
        mock_get_provider.return_value = mock_provider

        res_b = await client.post(
            "/api/memories",
            json={"category": "context", "key": "k_b", "content": "我的 AI Agent 学习记录"},
            headers=headers_b,
        )
        assert res_b.status_code == 201
        mem_b_id = res_b.json()["id"]

    # User A searches
    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=q_vec)
        mock_get_provider.return_value = mock_provider

        search_a = await auth_client.post(
            "/api/memories/search",
            json={"query": "AI Agent", "limit": 10},
        )
        assert search_a.status_code == 200
        items_a = search_a.json()["items"]
        assert len(items_a) == 1
        assert items_a[0]["id"] == mem_a_id
        assert items_a[0]["id"] != mem_b_id

    # User B searches
    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=q_vec)
        mock_get_provider.return_value = mock_provider

        search_b = await client.post(
            "/api/memories/search",
            json={"query": "AI Agent", "limit": 10},
            headers=headers_b,
        )
        assert search_b.status_code == 200
        items_b = search_b.json()["items"]
        assert len(items_b) == 1
        assert items_b[0]["id"] == mem_b_id
        assert items_b[0]["id"] != mem_a_id


# ────────────────────── 8: Client Vector Protection ──────────────────────

@pytest.mark.asyncio
async def test_semantic_search_does_not_accept_client_embedding(auth_client: AsyncClient):
    """Client cannot supply query vector; server always generates query embedding."""
    server_vec = make_vector(1.0)
    fake_client_vec = [999.99] * 1024

    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=server_vec)
        mock_get_provider.return_value = mock_provider

        # Create one memory
        await auth_client.post(
            "/api/memories",
            json={"category": "preference", "key": "k1", "content": "Valid target memory"},
        )

        # Search with client fake embedding in payload
        resp = await auth_client.post(
            "/api/memories/search",
            json={
                "query": "search query",
                "embedding": fake_client_vec,
                "limit": 5,
            },
        )
        assert resp.status_code == 200
        # Provider must be called with the text query, NOT client vector
        mock_provider.embed.assert_awaited_with("search query")


# ────────────────────── 9: Embedding Failure Safe Handling ──────────────────────

@pytest.mark.asyncio
async def test_semantic_search_embedding_failure(auth_client: AsyncClient):
    """Embedding failure returns clean error status without leaking secrets or traceback."""
    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(
            side_effect=EmbeddingCommunicationError("DashScope timeout sk-secret-key-12345")
        )
        mock_get_provider.return_value = mock_provider

        resp = await auth_client.post(
            "/api/memories/search",
            json={"query": "test query", "limit": 10},
        )
        # Must fail safely with 502/503
        assert resp.status_code in (502, 503)
        data = resp.json()
        detail = data.get("detail", "")
        # Must NOT leak secret key or full traceback
        assert "sk-secret-key-12345" not in detail
        assert "Traceback" not in detail


# ────────────────────── 10: Empty Results When No Memories ──────────────────────

@pytest.mark.asyncio
async def test_semantic_search_no_memory(auth_client: AsyncClient):
    """When user has no memories, returns empty list [] instead of error."""
    q_vec = make_vector(1.0)

    with patch("app.services.memory_service.get_embedding_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.embed = AsyncMock(return_value=q_vec)
        mock_get_provider.return_value = mock_provider

        resp = await auth_client.post(
            "/api/memories/search",
            json={"query": "anything", "limit": 10},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["query"] == "anything"


# ────────────────────── 11: Real DashScope E2E Integration ──────────────────────

@pytest.mark.asyncio
async def test_real_semantic_search_with_dashscope_if_key_available():
    """Live E2E test against PostgreSQL container with real DashScope Qwen embedding."""
    api_key = settings.get_embedding_api_key()
    if not api_key:
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("LLM_API_KEY=") or line.strip().startswith("DASHSCOPE_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break

    if not api_key:
        pytest.skip("No DashScope API key available; skipping real semantic search E2E test")

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
    created_mem_ids = []

    try:
        async with PgSession() as session:
            # 1. Create a test user
            test_user = User(
                email="semantic_e2e_user@example.com",
                hashed_password="hashed_pw_e2e",
                passport_id="mp_semantic0001",
                display_name="Semantic E2E User",
            )
            session.add(test_user)
            await session.commit()
            await session.refresh(test_user)
            test_user_id = test_user.id

            # 2. Create 3 test memories with real DashScope embeddings
            memories_data = [
                ("k1", "我最近在学习 AI Agent、LangGraph 和 RAG。"),
                ("k2", "周末去超市买了水果和牛奶。"),
                ("k3", "我正在研究 Python AsyncIO 和后端开发。"),
            ]
            for key, content in memories_data:
                m = await memory_service.create_memory(
                    session,
                    test_user_id,
                    MemoryCreate(category="context", key=key, content=content),
                    embedding_provider=provider,
                )
                created_mem_ids.append(m.id)
            await session.commit()

            # 3. Perform semantic search
            results = await memory_service.semantic_search(
                session,
                user_id=test_user_id,
                query="最近学习人工智能 Agent 的内容",
                limit=10,
                embedding_provider=provider,
            )

            # 4. Verify results
            assert len(results) == 3, f"Expected 3 results, got {len(results)}"
            top_mem, top_score = results[0]

            # Top memory should be the AI Agent memory
            assert top_mem.content == "我最近在学习 AI Agent、LangGraph 和 RAG。"
            assert top_score > results[1][1], "Top result must have higher similarity"
            assert top_score > results[2][1], "Top result must have higher similarity"
            assert top_score > 0.5, f"Expected high similarity for top match, got {top_score}"

    finally:
        # 5. Clean up all test data
        async with PgSession() as session:
            for m_id in created_mem_ids:
                await session.execute(text("DELETE FROM memories WHERE id = :id"), {"id": m_id})
            if test_user_id:
                await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": test_user_id})
            await session.commit()

            # Confirm 0 residue
            check_m = await session.execute(
                text("SELECT count(*) FROM memories WHERE user_id = :uid"), {"uid": test_user_id}
            )
            assert check_m.scalar() == 0, "No residual memories should remain"

        await pg_engine.dispose()

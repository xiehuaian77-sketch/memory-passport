"""Phase 2.5C: Retrieval API endpoint integration tests."""

from unittest.mock import patch
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.providers.embedding_provider import (
    EmbeddingCommunicationError,
    EmbeddingConfigError,
)


@pytest.mark.asyncio
async def test_unauthenticated_request(client: AsyncClient):
    """Unauthenticated requests to /api/memories/retrieve must return 401."""
    resp = await client.post("/api/memories/retrieve", json={"query": "test query"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_parameters_validation(auth_client: AsyncClient):
    """Invalid query, limits, or parameters must return 422 Unprocessable Entity."""
    # Empty query
    r1 = await auth_client.post("/api/memories/retrieve", json={"query": ""})
    assert r1.status_code == 422

    # Whitespace only query
    r2 = await auth_client.post("/api/memories/retrieve", json={"query": "   "})
    assert r2.status_code == 422

    # Invalid top_k (< 1)
    r3 = await auth_client.post(
        "/api/memories/retrieve", json={"query": "valid", "top_k": 0}
    )
    assert r3.status_code == 422

    # Invalid top_k (> 50)
    r4 = await auth_client.post(
        "/api/memories/retrieve", json={"query": "valid", "top_k": 51}
    )
    assert r4.status_code == 422

    # Invalid min_relevance (> 1.0)
    r5 = await auth_client.post(
        "/api/memories/retrieve", json={"query": "valid", "min_relevance": 1.5}
    )
    assert r5.status_code == 422

    # Invalid recency_half_life_days (<= 0)
    r6 = await auth_client.post(
        "/api/memories/retrieve", json={"query": "valid", "recency_half_life_days": 0}
    )
    assert r6.status_code == 422

    # Invalid max_memories (< 1)
    r7 = await auth_client.post(
        "/api/memories/retrieve", json={"query": "valid", "max_memories": 0}
    )
    assert r7.status_code == 422

    # Invalid max_content_chars (< 1)
    r8 = await auth_client.post(
        "/api/memories/retrieve", json={"query": "valid", "max_content_chars": 0}
    )
    assert r8.status_code == 422

    # Invalid max_context_chars (< 1)
    r9 = await auth_client.post(
        "/api/memories/retrieve", json={"query": "valid", "max_context_chars": 0}
    )
    assert r9.status_code == 422


@pytest.mark.asyncio
async def test_empty_results_returns_valid_context(auth_client: AsyncClient):
    """When no memories match, returns a valid empty AssembledContext without errors."""
    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={"query": "NonexistentTermXYZ12345"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total_memories"] == 0
    assert data["total_chars"] == 0
    assert data["max_context_chars"] == 4000
    assert data["max_content_chars"] == 500


@pytest.mark.asyncio
async def test_normal_retrieval_and_structure_completeness(auth_client: AsyncClient):
    """Verify normal retrieval flow and complete fields in returned AssembledContext."""
    # Create memory
    create_resp = await auth_client.post(
        "/api/memories",
        json={
            "category": "preference",
            "key": "editor_pref",
            "content": "User prefers Neovim for fast terminal editing",
            "importance": 0.8,
            "confidence": 0.95,
        },
    )
    assert create_resp.status_code == 201

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={"query": "Neovim editor", "min_relevance": 0.0},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_memories"] >= 1
    assert data["total_chars"] > 0
    assert len(data["items"]) == data["total_memories"]

    # Verify all expected item fields
    item = data["items"][0]
    assert "id" in item
    assert item["memory_type"] == "preference"
    assert "Neovim" in item["content"]
    assert item["source"] in ["manual", "ai_extracted", "imported"]
    assert isinstance(item["importance"], float)
    assert isinstance(item["confidence"], float)
    assert isinstance(item["retrieval_score"], float)
    assert isinstance(item["hybrid_score"], float)
    assert item["is_truncated"] is False
    assert item["original_char_count"] == len(item["content"])


@pytest.mark.asyncio
async def test_user_isolation_and_cross_user_invisibility(auth_client: AsyncClient):
    """Verify memories belonging to User A are completely invisible to User B."""
    # User A creates memory
    r_a = await auth_client.post(
        "/api/memories",
        json={
            "category": "identity",
            "key": "user_a_secret",
            "content": "User A unique top secret code 998877",
        },
    )
    assert r_a.status_code == 201

    # User B registers and uses an independent client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client_b:
        r_reg = await client_b.post(
            "/api/auth/register",
            json={
                "email": "user_b@example.com",
                "password": "password123",
                "display_name": "User B",
            },
        )
        assert r_reg.status_code == 201
        token_b = r_reg.json()["access_token"]
        client_b.headers["Authorization"] = f"Bearer {token_b}"

        # User B creates memory
        r_b = await client_b.post(
            "/api/memories",
            json={
                "category": "identity",
                "key": "user_b_secret",
                "content": "User B unique top secret code 112233",
            },
        )
        assert r_b.status_code == 201

        # User B queries "secret" -> must only see User B's memory
        resp_b = await client_b.post(
            "/api/memories/retrieve",
            json={"query": "secret code", "min_relevance": 0.0},
        )
        assert resp_b.status_code == 200
        b_items = resp_b.json()["items"]
        assert all("User A" not in item["content"] for item in b_items)
        assert any("User B" in item["content"] for item in b_items)

    # User A queries "secret" -> must only see User A's memory
    resp_a = await auth_client.post(
        "/api/memories/retrieve",
        json={"query": "secret code", "min_relevance": 0.0},
    )
    assert resp_a.status_code == 200
    a_items = resp_a.json()["items"]
    assert all("User B" not in item["content"] for item in a_items)
    assert any("User A" in item["content"] for item in a_items)


@pytest.mark.asyncio
async def test_top_k_parameter(auth_client: AsyncClient):
    """Verify top_k limits the number of candidates passed to policy and assembly."""
    for i in range(4):
        await auth_client.post(
            "/api/memories",
            json={
                "category": "preference",
                "key": f"docker_{i}",
                "content": f"User uses Docker container service variant {i}",
            },
        )

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={"query": "Docker container", "top_k": 2, "min_relevance": 0.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) <= 2


@pytest.mark.asyncio
async def test_relevance_filter(auth_client: AsyncClient):
    """Verify min_relevance filters out low scoring candidates."""
    await auth_client.post(
        "/api/memories",
        json={
            "category": "preference",
            "key": "vue_note",
            "content": "User casually looked at Vue.js once",
        },
    )

    # Strict relevance threshold 0.99
    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={"query": "Vue.js", "min_relevance": 0.99},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []


@pytest.mark.asyncio
async def test_importance_filter(auth_client: AsyncClient):
    """Verify min_importance filters out memories below importance threshold."""
    await auth_client.post(
        "/api/memories",
        json={
            "category": "task",
            "key": "low_task",
            "content": "Low importance task regarding Kubernetes",
            "importance": 0.2,
        },
    )
    await auth_client.post(
        "/api/memories",
        json={
            "category": "task",
            "key": "high_task",
            "content": "High importance task regarding Kubernetes",
            "importance": 0.9,
        },
    )

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={"query": "Kubernetes", "min_importance": 0.8, "min_relevance": 0.0},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["importance"] >= 0.8
    assert "High importance" in items[0]["content"]


@pytest.mark.asyncio
async def test_confidence_filter(auth_client: AsyncClient):
    """Verify min_confidence filters out memories below confidence threshold."""
    await auth_client.post(
        "/api/memories",
        json={
            "category": "preference",
            "key": "unconfirmed",
            "content": "Uncertain user preference about Coffee",
            "confidence": 0.3,
        },
    )
    await auth_client.post(
        "/api/memories",
        json={
            "category": "preference",
            "key": "confirmed",
            "content": "Certain user preference about Coffee",
            "confidence": 0.99,
        },
    )

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={"query": "Coffee", "min_confidence": 0.9, "min_relevance": 0.0},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["confidence"] >= 0.9
    assert "Certain user" in items[0]["content"]


@pytest.mark.asyncio
async def test_memory_types_filter(auth_client: AsyncClient):
    """Verify memory_types parameter strictly filters by category."""
    await auth_client.post(
        "/api/memories",
        json={
            "category": "identity",
            "key": "id_mem",
            "content": "User is a senior software architect",
        },
    )
    await auth_client.post(
        "/api/memories",
        json={
            "category": "task",
            "key": "task_mem",
            "content": "User needs to review software architect PRs",
        },
    )

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "software architect",
            "memory_types": ["identity"],
            "min_relevance": 0.0,
        },
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["memory_type"] == "identity"
    assert "senior software architect" in items[0]["content"]


@pytest.mark.asyncio
async def test_context_budget_and_truncation(auth_client: AsyncClient):
    """Verify max_content_chars and max_context_chars work properly via API."""
    long_content = "Z" * 120
    await auth_client.post(
        "/api/memories",
        json={
            "category": "preference",
            "key": "long_key",
            "content": long_content,
        },
    )

    resp = await auth_client.post(
        "/api/memories/retrieve",
        json={
            "query": "Z",
            "max_content_chars": 30,
            "max_context_chars": 50,
            "min_relevance": 0.0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_memories"] == 1
    item = data["items"][0]
    assert len(item["content"]) == 30
    assert item["is_truncated"] is True
    assert item["original_char_count"] == 120
    assert data["total_chars"] == 30
    assert data["total_chars"] <= 50


@pytest.mark.asyncio
async def test_embedding_exceptions_handled_safely(auth_client: AsyncClient):
    """Verify Embedding exceptions return clean 502/503 HTTP status without internal leaks."""
    # Test EmbeddingConfigError -> 503
    with patch(
        "app.services.memory_service.hybrid_search",
        side_effect=EmbeddingConfigError("Config missing"),
    ):
        r_503 = await auth_client.post(
            "/api/memories/retrieve", json={"query": "test query"}
        )
        assert r_503.status_code == 503
        assert "Embedding service is not configured" in r_503.json()["detail"]

    # Test EmbeddingCommunicationError -> 502
    with patch(
        "app.services.memory_service.hybrid_search",
        side_effect=EmbeddingCommunicationError("Connection timeout"),
    ):
        r_502 = await auth_client.post(
            "/api/memories/retrieve", json={"query": "test query"}
        )
        assert r_502.status_code == 502
        assert "Failed to communicate with embedding service" in r_502.json()["detail"]

"""Tests for Evaluation REST API endpoints."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest_asyncio.fixture
async def user2_client(client: AsyncClient) -> AsyncClient:
    """Register a second user and return authenticated client."""
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": "user2@example.com",
            "password": "password123",
            "display_name": "User Two",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    c.headers["Authorization"] = f"Bearer {token}"
    return c


@pytest.mark.asyncio
async def test_dataset_lifecycle(auth_client: AsyncClient):
    """Test creating, reading, and listing evaluation datasets."""
    # 1. Create dataset
    create_resp = await auth_client.post(
        "/api/evaluation/datasets",
        json={"name": "Eval Dataset 1", "description": "Benchmark v1", "is_system": False},
    )
    assert create_resp.status_code == 201
    data = create_resp.json()
    dataset_id = data["id"]
    assert data["name"] == "Eval Dataset 1"
    assert data["description"] == "Benchmark v1"
    assert data["is_system"] is False
    assert "user_id" in data

    # 2. Get dataset by ID
    get_resp = await auth_client.get(f"/api/evaluation/datasets/{dataset_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == dataset_id

    # 3. List datasets
    list_resp = await auth_client.get("/api/evaluation/datasets")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) >= 1
    assert any(d["id"] == dataset_id for d in items)


@pytest.mark.asyncio
async def test_dataset_pagination(auth_client: AsyncClient):
    """Test pagination of evaluation datasets."""
    for i in range(5):
        await auth_client.post(
            "/api/evaluation/datasets",
            json={"name": f"Page Dataset {i}"},
        )

    resp = await auth_client.get("/api/evaluation/datasets?offset=1&limit=2")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2


@pytest.mark.asyncio
async def test_dataset_not_found(auth_client: AsyncClient):
    """Test getting non-existent dataset returns 404."""
    resp = await auth_client.get("/api/evaluation/datasets/non-existent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_dataset_unauthenticated(client: AsyncClient):
    """Test unauthenticated request to dataset endpoint returns 401."""
    resp = await client.get("/api/evaluation/datasets")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_dataset_validation_error(auth_client: AsyncClient):
    """Test invalid payload returns 422."""
    resp = await auth_client.post("/api/evaluation/datasets", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_case_lifecycle(auth_client: AsyncClient):
    """Test creating, reading, and listing evaluation cases."""
    # Setup dataset
    d_resp = await auth_client.post(
        "/api/evaluation/datasets",
        json={"name": "Case Dataset"},
    )
    dataset_id = d_resp.json()["id"]

    # Setup memories for ground truth
    m1 = (await auth_client.post("/api/memories", json={"key": "k1", "content": "Memory 1 Python"})).json()["id"]
    m2 = (await auth_client.post("/api/memories", json={"key": "k2", "content": "Memory 2 Python"})).json()["id"]

    # 1. Create case
    case_resp = await auth_client.post(
        f"/api/evaluation/datasets/{dataset_id}/cases",
        json={
            "query": "Find Python preferences",
            "expected_memory_ids": [m1, m2],
            "expected_relevance": {m1: 1.0, m2: 0.5},
            "tags": "python,preference",
        },
    )
    assert case_resp.status_code == 201
    case_data = case_resp.json()
    case_id = case_data["id"]
    assert case_data["query"] == "Find Python preferences"
    assert case_data["expected_memory_ids"] == [m1, m2]
    assert case_data["expected_relevance"] == {m1: 1.0, m2: 0.5}

    # 2. Get case by ID
    get_resp = await auth_client.get(f"/api/evaluation/cases/{case_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == case_id

    # 3. List cases for dataset
    list_resp = await auth_client.get(f"/api/evaluation/datasets/{dataset_id}/cases")
    assert list_resp.status_code == 200
    cases = list_resp.json()
    assert len(cases) == 1
    assert cases[0]["id"] == case_id


@pytest.mark.asyncio
async def test_case_not_found(auth_client: AsyncClient):
    """Test getting non-existent case returns 404."""
    resp = await auth_client.get("/api/evaluation/cases/non-existent-case-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_case_nonexistent_dataset(auth_client: AsyncClient):
    """Test creating a case under a non-existent dataset returns 404."""
    resp = await auth_client.post(
        "/api/evaluation/datasets/non-existent-dataset/cases",
        json={"query": "test query"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_case_validation_error(auth_client: AsyncClient):
    """Test creating case with missing query returns 422."""
    d_resp = await auth_client.post(
        "/api/evaluation/datasets",
        json={"name": "Case Val Dataset"},
    )
    dataset_id = d_resp.json()["id"]
    resp = await auth_client.post(f"/api/evaluation/datasets/{dataset_id}/cases", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_case_foreign_memory_validation(auth_client: AsyncClient):
    """Test creating case with non-existent or foreign expected_memory_id returns 422."""
    d_resp = await auth_client.post(
        "/api/evaluation/datasets",
        json={"name": "Case Foreign Dataset"},
    )
    dataset_id = d_resp.json()["id"]
    resp = await auth_client.post(
        f"/api/evaluation/datasets/{dataset_id}/cases",
        json={"query": "valid query", "expected_memory_ids": ["invalid-mem-id"]},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_run_lifecycle_and_execution(auth_client: AsyncClient):
    """Test run creation, execution, results, and metrics."""
    # 1. Create a memory to retrieve
    mem_resp = await auth_client.post(
        "/api/memories",
        json={
            "key": "eval_pref",
            "content": "User prefers FastAPI and PostgreSQL for backend development",
            "category": "preference",
        },
    )
    assert mem_resp.status_code == 201
    mem_id = mem_resp.json()["id"]

    # 2. Create dataset & case
    d_resp = await auth_client.post(
        "/api/evaluation/datasets",
        json={"name": "Run Lifecycle Dataset"},
    )
    dataset_id = d_resp.json()["id"]

    c_resp = await auth_client.post(
        f"/api/evaluation/datasets/{dataset_id}/cases",
        json={
            "query": "FastAPI PostgreSQL backend preference",
            "expected_memory_ids": [mem_id],
            "expected_relevance": {mem_id: 1.0},
        },
    )
    assert c_resp.status_code == 201

    # 3. Create run
    run_resp = await auth_client.post(
        f"/api/evaluation/datasets/{dataset_id}/runs",
        json={
            "name": "Keyword Benchmark Run",
            "retrieval_config": {"search_mode": "keyword", "limit": 5},
        },
    )
    assert run_resp.status_code == 201
    run_data = run_resp.json()
    run_id = run_data["id"]
    assert run_data["status"] == "pending"
    assert run_data["name"] == "Keyword Benchmark Run"

    # 4. Get run
    get_run_resp = await auth_client.get(f"/api/evaluation/runs/{run_id}")
    assert get_run_resp.status_code == 200
    assert get_run_resp.json()["id"] == run_id

    # 5. List runs
    list_runs_resp = await auth_client.get(f"/api/evaluation/datasets/{dataset_id}/runs")
    assert list_runs_resp.status_code == 200
    assert len(list_runs_resp.json()) >= 1

    # 6. Execute run
    exec_resp = await auth_client.post(f"/api/evaluation/runs/{run_id}/execute")
    assert exec_resp.status_code == 200
    completed_run = exec_resp.json()
    assert completed_run["status"] == "completed"
    assert "summary_metrics" in completed_run
    assert "mrr" in completed_run["summary_metrics"]
    assert "precision_at_k" in completed_run["summary_metrics"]

    # 7. Get run results
    results_resp = await auth_client.get(f"/api/evaluation/runs/{run_id}/results")
    assert results_resp.status_code == 200
    results = results_resp.json()
    assert len(results) == 1
    assert "latency_ms" in results[0]
    assert "metrics" in results[0]

    # 8. Get run metrics
    metrics_resp = await auth_client.get(f"/api/evaluation/runs/{run_id}/metrics")
    assert metrics_resp.status_code == 200
    metrics_data = metrics_resp.json()
    assert "mrr" in metrics_data
    assert "precision_at_k" in metrics_data

    # 9. Idempotency: re-executing completed run returns 409 Conflict
    re_exec_resp = await auth_client.post(f"/api/evaluation/runs/{run_id}/execute")
    assert re_exec_resp.status_code == 409


@pytest.mark.asyncio
async def test_run_not_found(auth_client: AsyncClient):
    """Test getting/executing non-existent run returns 404."""
    resp = await auth_client.get("/api/evaluation/runs/non-existent-run")
    assert resp.status_code == 404

    resp_exec = await auth_client.post("/api/evaluation/runs/non-existent-run/execute")
    assert resp_exec.status_code == 404

    resp_metrics = await auth_client.get("/api/evaluation/runs/non-existent-run/metrics")
    assert resp_metrics.status_code == 404

    resp_results = await auth_client.get("/api/evaluation/runs/non-existent-run/results")
    assert resp_results.status_code == 404


@pytest.mark.asyncio
async def test_memory_quality_endpoint_and_read_only(auth_client: AsyncClient):
    """Test memory quality evaluation and strictly read-only guarantee."""
    # 1. Create a memory
    mem_resp = await auth_client.post(
        "/api/memories",
        json={
            "key": "user_ide_pref",
            "content": "User strictly prefers VS Code with vim keybindings",
            "category": "preference",
            "importance": 0.8,
            "confidence": 0.9,
            "tags": "ide,editor",
        },
    )
    assert mem_resp.status_code == 201
    mem_data = mem_resp.json()
    mem_id = mem_data["id"]

    # 2. Call memory quality endpoint
    q_resp = await auth_client.get(f"/api/evaluation/memories/{mem_id}/quality")
    assert q_resp.status_code == 200
    q_data = q_resp.json()
    assert q_data["memory_id"] == mem_id
    assert 0.0 <= q_data["overall_score"] <= 1.0
    assert "dimensions" in q_data
    assert "confidence" in q_data["dimensions"]
    assert "freshness" in q_data["dimensions"]
    assert isinstance(q_data["warnings"], list)
    assert "summary_reason" in q_data

    # 3. VERIFY READ-ONLY INVARIANT
    after_mem_resp = await auth_client.get(f"/api/memories/{mem_id}")
    assert after_mem_resp.status_code == 200
    after_mem = after_mem_resp.json()
    assert after_mem["content"] == mem_data["content"]
    assert after_mem["status"] == mem_data["status"]
    assert after_mem["version"] == mem_data["version"]
    assert after_mem["updated_at"] == mem_data["updated_at"]


@pytest.mark.asyncio
async def test_memory_quality_not_found(auth_client: AsyncClient):
    """Test getting quality for non-existent memory returns 404."""
    resp = await auth_client.get("/api/evaluation/memories/non-existent-memory-id/quality")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_tenant_isolation(auth_client: AsyncClient, user2_client: AsyncClient):
    """Test strict tenant isolation across all evaluation endpoints."""
    # User 1 creates dataset, case, run, and memory
    d_resp = await auth_client.post(
        "/api/evaluation/datasets",
        json={"name": "User 1 Dataset"},
    )
    dataset_id = d_resp.json()["id"]

    c_resp = await auth_client.post(
        f"/api/evaluation/datasets/{dataset_id}/cases",
        json={"query": "User 1 Query"},
    )
    case_id = c_resp.json()["id"]

    r_resp = await auth_client.post(
        f"/api/evaluation/datasets/{dataset_id}/runs",
        json={"name": "User 1 Run", "retrieval_config": {"search_mode": "keyword"}},
    )
    assert r_resp.status_code == 201
    run_id = r_resp.json()["id"]

    m_resp = await auth_client.post(
        "/api/memories",
        json={"key": "user1_key", "content": "User 1 memory content"},
    )
    mem_id = m_resp.json()["id"]

    # User 2 attempts cross-tenant access -> MUST all be 404 without leaking info
    # 1. Dataset access
    assert (await user2_client.get(f"/api/evaluation/datasets/{dataset_id}")).status_code == 404

    # 2. Case access
    assert (await user2_client.get(f"/api/evaluation/cases/{case_id}")).status_code == 404
    assert (await user2_client.get(f"/api/evaluation/datasets/{dataset_id}/cases")).status_code == 404
    assert (
        await user2_client.post(
            f"/api/evaluation/datasets/{dataset_id}/cases",
            json={"query": "Hacker query"},
        )
    ).status_code == 404

    # 3. Run access & execution
    assert (await user2_client.get(f"/api/evaluation/runs/{run_id}")).status_code == 404
    assert (await user2_client.get(f"/api/evaluation/datasets/{dataset_id}/runs")).status_code == 404
    assert (
        await user2_client.post(
            f"/api/evaluation/datasets/{dataset_id}/runs",
            json={"name": "Hacker Run", "retrieval_config": {"search_mode": "keyword"}},
        )
    ).status_code == 404
    assert (await user2_client.post(f"/api/evaluation/runs/{run_id}/execute")).status_code == 404
    assert (await user2_client.get(f"/api/evaluation/runs/{run_id}/metrics")).status_code == 404
    assert (await user2_client.get(f"/api/evaluation/runs/{run_id}/results")).status_code == 404

    # 4. Memory quality access
    assert (await user2_client.get(f"/api/evaluation/memories/{mem_id}/quality")).status_code == 404

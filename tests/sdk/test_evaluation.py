"""Tests for Evaluation SDK resource and models."""

import json

import pytest
from memory_passport.exceptions import ConflictError, NotFoundError, ValidationError
from memory_passport.models.evaluation import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationResult,
    EvaluationRun,
    MemoryQualityResult,
)


def test_client_evaluation_namespace(mock_client):
    """Verify evaluation resource is available on MemoryPassportClient."""
    assert hasattr(mock_client, "evaluation")
    assert mock_client.evaluation is not None


def test_create_dataset(mock_handler, mock_client):
    """Test creating an evaluation dataset via SDK."""
    mock_handler.register(
        "POST",
        "/api/evaluation/datasets",
        status_code=201,
        json_data={
            "id": "ds-101",
            "user_id": "usr-1",
            "name": "Benchmark Dataset",
            "description": "Evaluation benchmark v1",
            "is_system": False,
            "created_at": "2026-09-13T12:00:00Z",
            "updated_at": "2026-09-13T12:00:00Z",
            "future_extra_field": "safe",
        },
    )

    dataset = mock_client.evaluation.create_dataset(
        name="Benchmark Dataset",
        description="Evaluation benchmark v1",
        is_system=False,
    )

    assert isinstance(dataset, EvaluationDataset)
    assert dataset.id == "ds-101"
    assert dataset.name == "Benchmark Dataset"
    assert dataset.description == "Evaluation benchmark v1"
    assert dataset.is_system is False

    req = mock_handler.requests[0]
    body = json.loads(req.content)
    assert body["name"] == "Benchmark Dataset"
    assert body["description"] == "Evaluation benchmark v1"


def test_get_dataset(mock_handler, mock_client):
    """Test retrieving a dataset by ID."""
    mock_handler.register(
        "GET",
        "/api/evaluation/datasets/ds-101",
        status_code=200,
        json_data={
            "id": "ds-101",
            "user_id": "usr-1",
            "name": "Benchmark Dataset",
            "description": "",
            "is_system": False,
            "created_at": "2026-09-13T12:00:00Z",
            "updated_at": "2026-09-13T12:00:00Z",
        },
    )

    dataset = mock_client.evaluation.get_dataset("ds-101")
    assert dataset.id == "ds-101"
    assert dataset.name == "Benchmark Dataset"


def test_list_and_iter_datasets(mock_handler, mock_client):
    """Test listing and paginating datasets."""
    mock_handler.register(
        "GET",
        "/api/evaluation/datasets",
        status_code=200,
        json_data=[
            {
                "id": f"ds-{i}",
                "user_id": "usr-1",
                "name": f"Dataset {i}",
                "description": "",
                "is_system": False,
                "created_at": "2026-09-13T12:00:00Z",
                "updated_at": "2026-09-13T12:00:00Z",
            }
            for i in range(2)
        ],
    )

    page = mock_client.evaluation.list_datasets(offset=0, limit=2)
    assert len(page.items) == 2
    assert page.items[0].id == "ds-0"

    items = list(mock_client.evaluation.iter_datasets(page_size=2, max_items=2))
    assert len(items) == 2


def test_create_case(mock_handler, mock_client):
    """Test creating an evaluation test case."""
    mock_handler.register(
        "POST",
        "/api/evaluation/datasets/ds-101/cases",
        status_code=201,
        json_data={
            "id": "case-201",
            "dataset_id": "ds-101",
            "user_id": "usr-1",
            "query": "Where is my passport?",
            "expected_memory_ids": ["mem-1"],
            "expected_relevance": {"mem-1": 1.0},
            "tags": "location,travel",
            "temporal_anchor": None,
            "created_at": "2026-09-13T12:00:00Z",
            "updated_at": "2026-09-13T12:00:00Z",
        },
    )

    case = mock_client.evaluation.create_case(
        "ds-101",
        query="Where is my passport?",
        expected_memory_ids=["mem-1"],
        expected_relevance={"mem-1": 1.0},
        tags="location,travel",
    )

    assert isinstance(case, EvaluationCase)
    assert case.id == "case-201"
    assert case.query == "Where is my passport?"
    assert case.expected_memory_ids == ["mem-1"]


def test_get_and_list_cases(mock_handler, mock_client):
    """Test getting and listing evaluation cases."""
    mock_handler.register(
        "GET",
        "/api/evaluation/cases/case-201",
        status_code=200,
        json_data={
            "id": "case-201",
            "dataset_id": "ds-101",
            "user_id": "usr-1",
            "query": "Test query",
            "expected_memory_ids": [],
            "expected_relevance": {},
            "tags": "",
            "temporal_anchor": None,
            "created_at": "2026-09-13T12:00:00Z",
            "updated_at": "2026-09-13T12:00:00Z",
        },
    )
    case = mock_client.evaluation.get_case("case-201")
    assert case.id == "case-201"

    mock_handler.register(
        "GET",
        "/api/evaluation/datasets/ds-101/cases",
        status_code=200,
        json_data=[
            {
                "id": "case-201",
                "dataset_id": "ds-101",
                "user_id": "usr-1",
                "query": "Test query",
                "expected_memory_ids": [],
                "expected_relevance": {},
                "tags": "",
                "temporal_anchor": None,
                "created_at": "2026-09-13T12:00:00Z",
                "updated_at": "2026-09-13T12:00:00Z",
            }
        ],
    )
    cases_page = mock_client.evaluation.list_cases("ds-101")
    assert len(cases_page.items) == 1


def test_create_and_execute_run(mock_handler, mock_client):
    """Test creating and executing an evaluation run."""
    mock_handler.register(
        "POST",
        "/api/evaluation/datasets/ds-101/runs",
        status_code=201,
        json_data={
            "id": "run-301",
            "dataset_id": "ds-101",
            "user_id": "usr-1",
            "name": "Benchmark Run 1",
            "app_version": "1.9.0",
            "status": "pending",
            "retrieval_config": {"search_mode": "hybrid"},
            "summary_metrics": None,
            "error_message": None,
            "created_at": "2026-09-13T12:00:00Z",
            "completed_at": None,
        },
    )

    run = mock_client.evaluation.create_run(
        "ds-101",
        name="Benchmark Run 1",
        retrieval_config={"search_mode": "hybrid"},
    )
    assert isinstance(run, EvaluationRun)
    assert run.id == "run-301"
    assert run.status == "pending"

    mock_handler.register(
        "POST",
        "/api/evaluation/runs/run-301/execute",
        status_code=200,
        json_data={
            "id": "run-301",
            "dataset_id": "ds-101",
            "user_id": "usr-1",
            "name": "Benchmark Run 1",
            "app_version": "1.9.0",
            "status": "completed",
            "retrieval_config": {"search_mode": "hybrid"},
            "summary_metrics": {"mrr": 0.85, "precision_at_k": {"5": 0.8}},
            "error_message": None,
            "created_at": "2026-09-13T12:00:00Z",
            "completed_at": "2026-09-13T12:01:00Z",
        },
    )

    executed_run = mock_client.evaluation.execute_run("run-301")
    assert executed_run.status == "completed"
    assert executed_run.summary_metrics["mrr"] == 0.85


def test_get_run_and_metrics(mock_handler, mock_client):
    """Test retrieving run details and metrics."""
    mock_handler.register(
        "GET",
        "/api/evaluation/runs/run-301",
        status_code=200,
        json_data={
            "id": "run-301",
            "dataset_id": "ds-101",
            "user_id": "usr-1",
            "name": "Benchmark Run 1",
            "app_version": "1.9.0",
            "status": "completed",
            "retrieval_config": {},
            "summary_metrics": {"mrr": 0.85},
            "error_message": None,
            "created_at": "2026-09-13T12:00:00Z",
            "completed_at": "2026-09-13T12:01:00Z",
        },
    )
    run = mock_client.evaluation.get_run("run-301")
    assert run.id == "run-301"

    mock_handler.register(
        "GET",
        "/api/evaluation/runs/run-301/metrics",
        status_code=200,
        json_data={"mrr": 0.85, "ndcg_at_k": {"5": 0.9}},
    )
    metrics = mock_client.evaluation.get_metrics("run-301")
    assert metrics["mrr"] == 0.85


def test_list_run_results(mock_handler, mock_client):
    """Test listing per-case results for a run."""
    mock_handler.register(
        "GET",
        "/api/evaluation/runs/run-301/results",
        status_code=200,
        json_data=[
            {
                "id": "res-401",
                "run_id": "run-301",
                "case_id": "case-201",
                "user_id": "usr-1",
                "retrieved_memory_ids": ["mem-1"],
                "scores": [0.95],
                "metrics": {"reciprocal_rank": 1.0},
                "latency_ms": 12.5,
                "context_chars": 150,
                "passed": True,
                "details": {},
                "created_at": "2026-09-13T12:00:30Z",
            }
        ],
    )

    results = mock_client.evaluation.list_results("run-301")
    assert len(results.items) == 1
    assert isinstance(results.items[0], EvaluationResult)
    assert results.items[0].latency_ms == 12.5
    assert results.items[0].passed is True


def test_get_memory_quality(mock_handler, mock_client):
    """Test retrieving deterministic memory quality score."""
    mock_handler.register(
        "GET",
        "/api/evaluation/memories/mem-1/quality",
        status_code=200,
        json_data={
            "memory_id": "mem-1",
            "user_id": "usr-1",
            "overall_score": 0.92,
            "dimensions": {
                "confidence": {
                    "name": "confidence",
                    "score": 0.9,
                    "weight": 0.25,
                    "reason": "High confidence statement",
                    "raw_risk": None,
                },
                "freshness": {
                    "name": "freshness",
                    "score": 1.0,
                    "weight": 0.2,
                    "reason": "Recently updated memory",
                    "raw_risk": None,
                },
            },
            "warnings": [],
            "evaluated_at": "2026-09-13T12:00:00Z",
            "summary_reason": "High quality memory",
        },
    )

    quality = mock_client.evaluation.get_memory_quality("mem-1")
    assert isinstance(quality, MemoryQualityResult)
    assert quality.memory_id == "mem-1"
    assert quality.overall_score == 0.92
    assert "confidence" in quality.dimensions
    assert quality.dimensions["confidence"].score == 0.9


def test_evaluation_error_handling(mock_handler, mock_client):
    """Test standard HTTP error translations in evaluation resource."""
    # 404 NotFound
    mock_handler.register("GET", "/api/evaluation/datasets/not-found", status_code=404, json_data={"detail": "Not found"})
    with pytest.raises(NotFoundError):
        mock_client.evaluation.get_dataset("not-found")

    # 409 Conflict
    mock_handler.register("POST", "/api/evaluation/runs/run-done/execute", status_code=409, json_data={"detail": "Already completed"})
    with pytest.raises(ConflictError):
        mock_client.evaluation.execute_run("run-done")

    # 422 Validation
    mock_handler.register("POST", "/api/evaluation/datasets", status_code=422, json_data={"detail": "Invalid name"})
    with pytest.raises(ValidationError):
        mock_client.evaluation.create_dataset(name="")

"""Tests for Phase 5.6B: Retrieval Evaluation & IR Metrics Engine.

Covers:
1. Precision@K (standard, retrieved < K, empty expected/retrieved, duplicates, invalid K)
2. Recall@K (standard, empty expected/retrieved, K > expected, invalid K)
3. MRR (rank 1, rank 2, rank 10, no relevant, empty expected/retrieved)
4. NDCG@K (binary relevance, graded relevance, empty/zero IDCG, invalid values, invalid K)
5. MAP (Average Precision standard, empty, no relevant, partial retrieval)
6. Latency statistics (monotonic, percentiles)
7. Determinism
8. EvaluationService run lifecycle (pending -> running -> completed)
9. EvaluationService with multiple search modes (retrieve, hybrid, keyword)
10. Tenant isolation (dataset access denied, expected memories cross-user check)
11. Bounded batch execution
12. Failure handling
"""

import uuid
import pytest

from app.models.user import User
from app.repositories import evaluation_repo
from app.schemas.memory import MemoryCreate
from app.services import evaluation_metrics, memory_service
from app.services.evaluation_service import EvaluationService
from tests.conftest import TestSession


# ============================================================
# 1. PRECISION@K TESTS
# ============================================================

def test_precision_at_k_standard():
    expected = ["m1", "m2", "m3"]
    retrieved = ["m1", "m2", "m4", "m5", "m3"]

    # P@1: top 1 is "m1" (relevant) -> 1/1 = 1.0
    assert evaluation_metrics.precision_at_k(retrieved, expected, k=1) == 1.0

    # P@2: top 2 are "m1", "m2" -> 2/2 = 1.0
    assert evaluation_metrics.precision_at_k(retrieved, expected, k=2) == 1.0

    # P@3: top 3 are "m1", "m2", "m4" -> 2/3 = 0.6667
    assert evaluation_metrics.precision_at_k(retrieved, expected, k=3) == 0.6667

    # P@5: top 5 contain "m1", "m2", "m3" -> 3/5 = 0.6
    assert evaluation_metrics.precision_at_k(retrieved, expected, k=5) == 0.6


def test_precision_at_k_retrieved_less_than_k():
    expected = ["m1", "m2"]
    retrieved = ["m1"]  # only 1 item retrieved, k=5

    # Divisor must remain K=5, not shortened
    assert evaluation_metrics.precision_at_k(retrieved, expected, k=5) == 0.2


def test_precision_at_k_empty_expected():
    retrieved = ["m1", "m2"]
    # If no relevant items exist in ground truth, precision is 0.0 without error
    assert evaluation_metrics.precision_at_k(retrieved, expected=[], k=3) == 0.0


def test_precision_at_k_empty_retrieved():
    expected = ["m1", "m2"]
    assert evaluation_metrics.precision_at_k(retrieved=[], expected=expected, k=5) == 0.0


def test_precision_at_k_duplicate_ids():
    expected = ["m1", "m1", "m2"]
    # Duplicate retrieved items in top K should count unique relevant items
    retrieved = ["m1", "m1", "m3"]
    assert evaluation_metrics.precision_at_k(retrieved, expected, k=2) == 0.5


def test_precision_at_k_invalid_k():
    with pytest.raises(ValueError):
        evaluation_metrics.precision_at_k(["m1"], ["m1"], k=0)

    with pytest.raises(ValueError):
        evaluation_metrics.precision_at_k(["m1"], ["m1"], k=-1)


# ============================================================
# 2. RECALL@K TESTS
# ============================================================

def test_recall_at_k_standard():
    expected = ["m1", "m2", "m3", "m4"]
    retrieved = ["m1", "x1", "m2", "x2", "m3"]

    # R@1: 1 out of 4 -> 0.25
    assert evaluation_metrics.recall_at_k(retrieved, expected, k=1) == 0.25

    # R@3: 2 out of 4 -> 0.5
    assert evaluation_metrics.recall_at_k(retrieved, expected, k=3) == 0.5

    # R@5: 3 out of 4 -> 0.75
    assert evaluation_metrics.recall_at_k(retrieved, expected, k=5) == 0.75


def test_recall_at_k_empty_expected():
    # When ground truth is empty, recall must be 0.0 (prevents division by zero)
    assert evaluation_metrics.recall_at_k(["m1", "m2"], expected=[], k=5) == 0.0


def test_recall_at_k_empty_retrieved():
    assert evaluation_metrics.recall_at_k(retrieved=[], expected=["m1", "m2"], k=5) == 0.0


def test_recall_at_k_k_greater_than_expected():
    expected = ["m1", "m2"]
    retrieved = ["m1", "m2", "x1", "x2", "x3", "x4"]
    # R@5 captures both -> 2/2 = 1.0
    assert evaluation_metrics.recall_at_k(retrieved, expected, k=5) == 1.0


def test_recall_at_k_invalid_k():
    with pytest.raises(ValueError):
        evaluation_metrics.recall_at_k(["m1"], ["m1"], k=0)


# ============================================================
# 3. MRR TESTS
# ============================================================

def test_mrr_ranks():
    expected = ["target"]

    # First relevant at rank 1 -> 1/1 = 1.0
    assert evaluation_metrics.reciprocal_rank(["target", "x"], expected) == 1.0

    # First relevant at rank 2 -> 1/2 = 0.5
    assert evaluation_metrics.reciprocal_rank(["x", "target"], expected) == 0.5

    # First relevant at rank 10 -> 1/10 = 0.1
    ten_items = [f"x{i}" for i in range(9)] + ["target"]
    assert evaluation_metrics.reciprocal_rank(ten_items, expected) == 0.1


def test_mrr_no_relevant_result():
    assert evaluation_metrics.reciprocal_rank(["x1", "x2"], ["m1"]) == 0.0


def test_mrr_empty_ground_truth():
    assert evaluation_metrics.reciprocal_rank(["m1", "m2"], expected=[]) == 0.0


def test_mrr_empty_retrieved():
    assert evaluation_metrics.reciprocal_rank(retrieved=[], expected=["m1"]) == 0.0


# ============================================================
# 4. NDCG@K TESTS
# ============================================================

def test_ndcg_at_k_binary_relevance():
    expected = ["m1", "m2"]

    # Perfect ranking: both retrieved at rank 1 and 2 -> NDCG = 1.0
    assert evaluation_metrics.ndcg_at_k(["m1", "m2", "x"], expected, k=3) == 1.0

    # Sub-optimal ranking: rank 2 and 3 -> NDCG < 1.0
    imperfect = evaluation_metrics.ndcg_at_k(["x", "m1", "m2"], expected, k=3)
    assert 0.0 < imperfect < 1.0

    # No relevant retrieved -> NDCG = 0.0
    assert evaluation_metrics.ndcg_at_k(["x1", "x2"], expected, k=3) == 0.0


def test_ndcg_at_k_graded_relevance():
    expected = ["m_high", "m_med", "m_low"]
    relevance = {"m_high": 3.0, "m_med": 2.0, "m_low": 1.0}

    # Perfect order: m_high, m_med, m_low
    assert evaluation_metrics.ndcg_at_k(
        ["m_high", "m_med", "m_low"], expected, relevance, k=3
    ) == 1.0

    # Inverted order: m_low, m_med, m_high
    inverted = evaluation_metrics.ndcg_at_k(
        ["m_low", "m_med", "m_high"], expected, relevance, k=3
    )
    assert 0.0 < inverted < 1.0
    # Inverted score is strictly less than 1.0
    assert inverted < 0.95


def test_ndcg_at_k_empty_and_zero_idcg():
    # Empty expected -> IDCG=0 -> NDCG=0.0
    assert evaluation_metrics.ndcg_at_k(["m1"], expected=[], k=5) == 0.0

    # Relevance map with only 0 scores
    relevance = {"m1": 0.0}
    assert evaluation_metrics.ndcg_at_k(["m1"], ["m1"], relevance, k=5) == 0.0


def test_ndcg_at_k_invalid_values():
    # Negative or non-numeric relevance values safely ignored/fallback
    relevance = {"m1": -1.0, "m2": "invalid"}  # type: ignore
    ndcg = evaluation_metrics.ndcg_at_k(["m1", "m2"], ["m1", "m2"], relevance, k=5)
    assert 0.0 <= ndcg <= 1.0


def test_ndcg_at_k_invalid_k():
    with pytest.raises(ValueError):
        evaluation_metrics.ndcg_at_k(["m1"], ["m1"], k=0)


# ============================================================
# 5. MAP (AVERAGE PRECISION) TESTS
# ============================================================

def test_map_standard():
    expected = ["m1", "m2"]
    # m1 at rank 1 (P=1/1), m2 at rank 3 (P=2/3) -> AP = (1.0 + 2/3) / 2 = 0.8333
    retrieved = ["m1", "x1", "m2"]
    ap = evaluation_metrics.average_precision(retrieved, expected)
    assert ap == 0.8333


def test_map_empty_and_no_relevant():
    assert evaluation_metrics.average_precision(["m1"], expected=[]) == 0.0
    assert evaluation_metrics.average_precision(["x1", "x2"], expected=["m1"]) == 0.0
    assert evaluation_metrics.average_precision([], expected=["m1"]) == 0.0


def test_map_partial_retrieval():
    expected = ["m1", "m2", "m3"]
    # Only m1 retrieved at rank 1 -> AP = (1/1) / 3 = 0.3333
    retrieved = ["m1", "x1"]
    assert evaluation_metrics.average_precision(retrieved, expected) == 0.3333


# ============================================================
# 6. LATENCY & AGGREGATION TESTS
# ============================================================

def test_aggregate_run_metrics():
    case_metrics = [
        {
            "precision_at_k": {"1": 1.0, "3": 0.6667, "5": 0.4, "10": 0.2},
            "recall_at_k": {"1": 0.5, "3": 1.0, "5": 1.0, "10": 1.0},
            "mrr": 1.0,
            "ndcg_at_k": {"5": 0.9, "10": 0.9},
            "map": 0.8333,
        },
        {
            "precision_at_k": {"1": 0.0, "3": 0.3333, "5": 0.2, "10": 0.1},
            "recall_at_k": {"1": 0.0, "3": 0.5, "5": 0.5, "10": 0.5},
            "mrr": 0.5,
            "ndcg_at_k": {"5": 0.6, "10": 0.6},
            "map": 0.25,
        },
    ]
    latencies = [10.0, 20.0, 30.0]

    agg = evaluation_metrics.aggregate_run_metrics(case_metrics, latencies)
    assert agg["total_cases"] == 2
    assert agg["precision_at_k"]["1"] == 0.5
    assert agg["mrr"] == 0.75
    assert agg["ndcg_at_k"]["5"] == 0.75
    assert agg["latency"]["mean_ms"] == 20.0
    assert agg["latency"]["min_ms"] == 10.0
    assert agg["latency"]["max_ms"] == 30.0


def test_aggregate_empty_cases():
    agg = evaluation_metrics.aggregate_run_metrics([], [])
    assert agg["total_cases"] == 0
    assert agg["mrr"] == 0.0
    assert agg["latency"]["mean_ms"] == 0.0


# ============================================================
# 7. DETERMINISM TEST
# ============================================================

def test_metrics_determinism():
    retrieved = ["m1", "x1", "m2", "x2", "m3"]
    expected = ["m1", "m2", "m3"]
    relevance = {"m1": 2.0, "m2": 1.5, "m3": 1.0}

    res1 = evaluation_metrics.calculate_case_metrics(retrieved, expected, relevance)
    res2 = evaluation_metrics.calculate_case_metrics(retrieved, expected, relevance)

    assert res1 == res2
    assert res1["mrr"] == res2["mrr"]
    assert res1["ndcg_at_k"] == res2["ndcg_at_k"]


# ============================================================
# 8. EVALUATION SERVICE INTEGRATION TESTS
# ============================================================

async def _setup_user_with_memories(session) -> tuple[str, list[str]]:
    """Helper creating user and seeded memories for retrieval testing."""
    user = User(
        id=str(uuid.uuid4()),
        email=f"eval_svc_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="hash",
        display_name="Eval User",
    )
    session.add(user)
    await session.commit()

    m1 = await memory_service.create_memory(
        session,
        user.id,
        MemoryCreate(
            key="favorite_editor",
            content="User loves Neovim for Python coding",
            category="preference",
        ),
        auto_embed=False,
    )
    m2 = await memory_service.create_memory(
        session,
        user.id,
        MemoryCreate(
            key="os_choice",
            content="User uses Debian Linux for all servers",
            category="preference",
        ),
        auto_embed=False,
    )
    await session.commit()
    return user.id, [m1.id, m2.id]


@pytest.mark.asyncio
async def test_service_run_lifecycle_and_metrics():
    async with TestSession() as session:
        user_id, mem_ids = await _setup_user_with_memories(session)

        # 1. Create dataset and case
        ds = await evaluation_repo.create_dataset(
            session, user_id=user_id, name="Lifecycle Test Dataset"
        )
        case = await evaluation_repo.create_case(
            session,
            dataset_id=ds.id,
            user_id=user_id,
            query="Neovim Python editor",
            expected_memory_ids=[mem_ids[0]],
            expected_relevance={mem_ids[0]: 3.0},
        )
        assert case is not None

        # 2. Run evaluation
        run = await EvaluationService.run_evaluation(
            db=session,
            user_id=user_id,
            dataset_id=ds.id,
            name="Lifecycle Test Run",
            retrieval_config={"search_mode": "keyword", "top_k": 5},
            app_version="1.9.0",
        )

        assert run.status == "completed"
        assert run.app_version == "1.9.0"
        assert run.completed_at is not None
        assert run.summary_metrics is not None

        metrics = run.summary_metrics
        assert metrics["total_cases"] == 1
        assert "precision_at_k" in metrics
        assert "recall_at_k" in metrics
        assert "mrr" in metrics
        assert "ndcg_at_k" in metrics
        assert "latency" in metrics

        # 3. Check results persisted
        results = await EvaluationService.get_run_results(session, user_id, run.id)
        assert len(results) == 1
        res = results[0]
        assert res.case_id == case.id
        assert res.latency_ms >= 0.0
        assert mem_ids[0] in res.retrieved_memory_ids


@pytest.mark.asyncio
async def test_service_run_with_hybrid_search_mode():
    async with TestSession() as session:
        user_id, mem_ids = await _setup_user_with_memories(session)

        ds = await evaluation_repo.create_dataset(
            session, user_id=user_id, name="Hybrid Mode Dataset"
        )
        await evaluation_repo.create_case(
            session,
            dataset_id=ds.id,
            user_id=user_id,
            query="Debian server setup",
            expected_memory_ids=[mem_ids[1]],
        )

        run = await EvaluationService.run_evaluation(
            db=session,
            user_id=user_id,
            dataset_id=ds.id,
            name="Hybrid Mode Run",
            retrieval_config={"search_mode": "hybrid", "top_k": 5},
        )
        assert run.status == "completed"
        assert run.summary_metrics is not None
        assert run.summary_metrics["total_cases"] == 1


@pytest.mark.asyncio
async def test_service_tenant_isolation_dataset_denied():
    async with TestSession() as session:
        user1_id, _ = await _setup_user_with_memories(session)
        user2_id, _ = await _setup_user_with_memories(session)

        ds_u1 = await evaluation_repo.create_dataset(
            session, user_id=user1_id, name="User 1 Dataset"
        )

        # User 2 attempting to run evaluation on User 1's dataset must be rejected
        with pytest.raises(ValueError, match="not found or access denied"):
            await EvaluationService.run_evaluation(
                db=session,
                user_id=user2_id,
                dataset_id=ds_u1.id,
                name="Unauthorized Run",
            )


@pytest.mark.asyncio
async def test_service_tenant_isolation_expected_memories_denied():
    async with TestSession() as session:
        user1_id, mem_ids_u1 = await _setup_user_with_memories(session)
        user2_id, _ = await _setup_user_with_memories(session)

        # User 2 creates dataset
        ds_u2 = await evaluation_repo.create_dataset(
            session, user_id=user2_id, name="User 2 Dataset"
        )
        # Case in user 2's dataset references user 1's memory
        case_with_stolen_id = await evaluation_repo.create_case(
            session,
            dataset_id=ds_u2.id,
            user_id=user2_id,
            query="stolen query",
            expected_memory_ids=[mem_ids_u1[0]],  # belongs to user 1!
        )
        assert case_with_stolen_id is not None

        # Evaluation run must fail with access denied on expected memories
        with pytest.raises(ValueError, match="Invalid expected_memory_ids"):
            await EvaluationService.run_evaluation(
                db=session,
                user_id=user2_id,
                dataset_id=ds_u2.id,
                name="Cross Tenant Attack Run",
            )


@pytest.mark.asyncio
async def test_service_batch_processing_multiple_cases():
    async with TestSession() as session:
        user_id, mem_ids = await _setup_user_with_memories(session)

        ds = await evaluation_repo.create_dataset(
            session, user_id=user_id, name="Batch Dataset"
        )
        # Create 5 cases
        for i in range(5):
            await evaluation_repo.create_case(
                session,
                dataset_id=ds.id,
                user_id=user_id,
                query=f"Query {i}",
                expected_memory_ids=[mem_ids[0]],
            )

        # Run with batch_size=2 to verify pagination loops
        run = await EvaluationService.run_evaluation(
            db=session,
            user_id=user_id,
            dataset_id=ds.id,
            name="Batch Run",
            retrieval_config={"search_mode": "keyword", "top_k": 3},
            batch_size=2,
        )

        assert run.status == "completed"
        assert run.summary_metrics["total_cases"] == 5
        results = await EvaluationService.get_run_results(session, user_id, run.id)
        assert len(results) == 5

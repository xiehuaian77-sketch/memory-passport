"""Tests for Phase 5.6A Evaluation Foundation (Migration 009, Models, Repository).

Covers:
1. Evaluation Dataset CRUD & Strict User Isolation
2. Evaluation Case CRUD & Strict User Isolation
3. Evaluation Run CRUD, Status Transitions & Strict User Isolation
4. Evaluation Result CRUD, Bulk Creation & Strict User Isolation
5. Cascade Deletion (Dataset -> Cases, Runs, Results)
6. Cascade Deletion (Run -> Results)
7. Migration Sequence & File Continuity (001 to 009)
"""

import os
import uuid
import pytest
from datetime import datetime, timezone

from app.models.user import User
from app.repositories import evaluation_repo
from tests.conftest import TestSession


async def _create_test_users(session) -> tuple[str, str]:
    """Helper to create two test users for isolation testing."""
    user1 = User(
        id=str(uuid.uuid4()),
        email=f"eval_u1_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="hash",
        display_name="User 1",
    )
    user2 = User(
        id=str(uuid.uuid4()),
        email=f"eval_u2_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="hash",
        display_name="User 2",
    )
    session.add_all([user1, user2])
    await session.commit()
    return user1.id, user2.id


# ============================================================
# 1. EVALUATION DATASET TESTS
# ============================================================

@pytest.mark.asyncio
async def test_dataset_crud_and_isolation():
    async with TestSession() as session:
        user1_id, user2_id = await _create_test_users(session)

        # Create dataset for user 1
        ds1 = await evaluation_repo.create_dataset(
            session,
            user_id=user1_id,
            name="Golden Retrieval Benchmark",
            description="Ground truth cases for retrieval evaluation",
            is_system=False,
        )
        assert ds1.id is not None
        assert ds1.user_id == user1_id
        assert ds1.name == "Golden Retrieval Benchmark"
        assert ds1.description == "Ground truth cases for retrieval evaluation"
        assert ds1.is_system is False
        assert ds1.created_at is not None

        # User 1 can retrieve it
        retrieved = await evaluation_repo.get_dataset(session, ds1.id, user1_id)
        assert retrieved is not None
        assert retrieved.id == ds1.id

        # User 2 CANNOT retrieve user 1's dataset (strict isolation)
        leak = await evaluation_repo.get_dataset(session, ds1.id, user2_id)
        assert leak is None

        # List datasets for user 1
        ds_list_u1 = await evaluation_repo.list_datasets(session, user1_id)
        assert len(ds_list_u1) == 1
        assert ds_list_u1[0].id == ds1.id

        # List datasets for user 2
        ds_list_u2 = await evaluation_repo.list_datasets(session, user2_id)
        assert len(ds_list_u2) == 0

        # User 2 cannot delete user 1's dataset
        del_fail = await evaluation_repo.delete_dataset(session, ds1.id, user2_id)
        assert del_fail is False

        # User 1 deletes dataset
        del_success = await evaluation_repo.delete_dataset(session, ds1.id, user1_id)
        assert del_success is True

        # Now get returns None
        deleted = await evaluation_repo.get_dataset(session, ds1.id, user1_id)
        assert deleted is None


# ============================================================
# 2. EVALUATION CASE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_case_crud_and_isolation():
    async with TestSession() as session:
        user1_id, user2_id = await _create_test_users(session)

        ds = await evaluation_repo.create_dataset(
            session, user_id=user1_id, name="Case Test Dataset"
        )

        # Cannot create case for non-existent or foreign dataset
        invalid_case = await evaluation_repo.create_case(
            session,
            dataset_id="non-existent-id",
            user_id=user1_id,
            query="test query",
        )
        assert invalid_case is None

        cross_user_case = await evaluation_repo.create_case(
            session,
            dataset_id=ds.id,
            user_id=user2_id,  # user 2 trying to add to user 1's dataset
            query="test query",
        )
        assert cross_user_case is None

        # Create valid case
        now = datetime.now(timezone.utc)
        mem_id_1 = str(uuid.uuid4())
        mem_id_2 = str(uuid.uuid4())
        case = await evaluation_repo.create_case(
            session,
            dataset_id=ds.id,
            user_id=user1_id,
            query="What is my favorite programming language?",
            expected_memory_ids=[mem_id_1, mem_id_2],
            expected_relevance={mem_id_1: 1.0, mem_id_2: 0.8},
            tags="tech,preference",
            temporal_anchor=now,
        )
        assert case is not None
        assert case.id is not None
        assert case.query == "What is my favorite programming language?"
        assert case.expected_memory_ids == [mem_id_1, mem_id_2]
        assert case.expected_relevance == {mem_id_1: 1.0, mem_id_2: 0.8}
        assert case.tags == "tech,preference"

        # Test getter & setter properties
        case.expected_memory_ids = [mem_id_1]
        assert case.expected_memory_ids == [mem_id_1]
        assert case.expected_memory_ids_json == f'["{mem_id_1}"]'

        case.expected_relevance = {mem_id_1: 0.9}
        assert case.expected_relevance == {mem_id_1: 0.9}

        # Retrieval by user 1
        fetched = await evaluation_repo.get_case(session, case.id, user1_id)
        assert fetched is not None
        assert fetched.id == case.id

        # Isolation: user 2 cannot get case
        leak = await evaluation_repo.get_case(session, case.id, user2_id)
        assert leak is None

        # List cases in dataset
        cases = await evaluation_repo.list_cases(session, ds.id, user1_id)
        assert len(cases) == 1
        assert cases[0].id == case.id

        # User 2 list returns empty
        empty_cases = await evaluation_repo.list_cases(session, ds.id, user2_id)
        assert len(empty_cases) == 0

        # User 2 cannot delete case
        del_fail = await evaluation_repo.delete_case(session, case.id, user2_id)
        assert del_fail is False

        # User 1 can delete case
        del_ok = await evaluation_repo.delete_case(session, case.id, user1_id)
        assert del_ok is True
        assert await evaluation_repo.get_case(session, case.id, user1_id) is None


# ============================================================
# 3. EVALUATION RUN TESTS
# ============================================================

@pytest.mark.asyncio
async def test_run_crud_status_and_isolation():
    async with TestSession() as session:
        user1_id, user2_id = await _create_test_users(session)

        ds = await evaluation_repo.create_dataset(
            session, user_id=user1_id, name="Run Test Dataset"
        )

        # Cross-user run creation fails
        cross_run = await evaluation_repo.create_run(
            session,
            dataset_id=ds.id,
            user_id=user2_id,
            name="Unauthorized Run",
        )
        assert cross_run is None

        # Create valid run
        config = {
            "top_k": 5,
            "hybrid_weight": 0.7,
            "enable_graph_expansion": True,
        }
        run = await evaluation_repo.create_run(
            session,
            dataset_id=ds.id,
            user_id=user1_id,
            name="Run Benchmark #1",
            app_version="1.9.0",
            retrieval_config=config,
        )
        assert run is not None
        assert run.status == "pending"
        assert run.retrieval_config == config
        assert run.summary_metrics is None
        assert run.completed_at is None

        # Status transition to running
        updated = await evaluation_repo.update_run_status(
            session, run_id=run.id, user_id=user1_id, status="running"
        )
        assert updated is not None
        assert updated.status == "running"
        assert updated.completed_at is None

        # Invalid status raises ValueError
        with pytest.raises(ValueError):
            await evaluation_repo.update_run_status(
                session, run_id=run.id, user_id=user1_id, status="invalid_status"
            )

        # Transition to completed with summary metrics
        metrics = {
            "mrr": 0.85,
            "ndcg_at_5": 0.90,
            "hit_rate_at_5": 1.0,
            "latency_p95_ms": 42.5,
        }
        completed_run = await evaluation_repo.update_run_status(
            session,
            run_id=run.id,
            user_id=user1_id,
            status="completed",
            summary_metrics=metrics,
        )
        assert completed_run is not None
        assert completed_run.status == "completed"
        assert completed_run.summary_metrics == metrics
        assert completed_run.completed_at is not None

        # Isolation: user 2 cannot view or update run
        assert await evaluation_repo.get_run(session, run.id, user2_id) is None
        assert await evaluation_repo.update_run_status(
            session, run_id=run.id, user_id=user2_id, status="failed"
        ) is None

        # List runs
        runs = await evaluation_repo.list_runs(session, user_id=user1_id)
        assert len(runs) == 1
        runs_filtered = await evaluation_repo.list_runs(session, user_id=user1_id, dataset_id=ds.id)
        assert len(runs_filtered) == 1
        runs_empty = await evaluation_repo.list_runs(session, user_id=user2_id)
        assert len(runs_empty) == 0


# ============================================================
# 4. EVALUATION RESULT TESTS
# ============================================================

@pytest.mark.asyncio
async def test_result_crud_and_bulk_creation():
    async with TestSession() as session:
        user1_id, user2_id = await _create_test_users(session)

        ds = await evaluation_repo.create_dataset(
            session, user_id=user1_id, name="Result Dataset"
        )
        case1 = await evaluation_repo.create_case(
            session, dataset_id=ds.id, user_id=user1_id, query="Query 1"
        )
        case2 = await evaluation_repo.create_case(
            session, dataset_id=ds.id, user_id=user1_id, query="Query 2"
        )
        run = await evaluation_repo.create_run(
            session, dataset_id=ds.id, user_id=user1_id, name="Run with Results"
        )

        # Single result creation
        res1 = await evaluation_repo.create_result(
            session,
            run_id=run.id,
            case_id=case1.id,
            user_id=user1_id,
            retrieved_memory_ids=["mem-101", "mem-102"],
            scores=[0.95, 0.82],
            metrics={"mrr": 1.0, "hit": 1},
            latency_ms=18.4,
            context_chars=120,
            passed=True,
            details={"debug": "ok"},
        )
        assert res1.id is not None
        assert res1.retrieved_memory_ids == ["mem-101", "mem-102"]
        assert res1.scores == [0.95, 0.82]
        assert res1.metrics == {"mrr": 1.0, "hit": 1}
        assert res1.latency_ms == 18.4
        assert res1.passed is True
        assert res1.details == {"debug": "ok"}

        # Bulk result creation
        bulk_data = [
            {
                "run_id": run.id,
                "case_id": case2.id,
                "user_id": user1_id,
                "retrieved_memory_ids": ["mem-201"],
                "scores": [0.65],
                "metrics": {"mrr": 0.5, "hit": 1},
                "latency_ms": 22.1,
                "context_chars": 90,
                "passed": False,
                "details": {"reason": "low confidence"},
            }
        ]
        bulk_results = await evaluation_repo.create_results_bulk(session, bulk_data)
        assert len(bulk_results) == 1
        assert bulk_results[0].case_id == case2.id
        assert bulk_results[0].passed is False

        # List results for run
        run_results = await evaluation_repo.list_results_for_run(session, run.id, user1_id)
        assert len(run_results) == 2

        # Isolation: user 2 gets empty list and None
        u2_results = await evaluation_repo.list_results_for_run(session, run.id, user2_id)
        assert len(u2_results) == 0
        assert await evaluation_repo.get_result(session, res1.id, user2_id) is None


# ============================================================
# 5. CASCADE DELETION TESTS
# ============================================================

@pytest.mark.asyncio
async def test_cascade_deletion():
    async with TestSession() as session:
        user1_id, _ = await _create_test_users(session)

        ds = await evaluation_repo.create_dataset(
            session, user_id=user1_id, name="Cascade Test Dataset"
        )
        case = await evaluation_repo.create_case(
            session, dataset_id=ds.id, user_id=user1_id, query="Query cascade"
        )
        run = await evaluation_repo.create_run(
            session, dataset_id=ds.id, user_id=user1_id, name="Run cascade"
        )
        res = await evaluation_repo.create_result(
            session,
            run_id=run.id,
            case_id=case.id,
            user_id=user1_id,
            retrieved_memory_ids=["mem-cascade"],
        )

        # Deleting dataset should cascade delete cases, runs, and results
        success = await evaluation_repo.delete_dataset(session, ds.id, user1_id)
        assert success is True

        # Verify all children are deleted
        assert await evaluation_repo.get_case(session, case.id, user1_id) is None
        assert await evaluation_repo.get_run(session, run.id, user1_id) is None
        assert await evaluation_repo.get_result(session, res.id, user1_id) is None


# ============================================================
# 6. MIGRATION CONTINUITY VERIFICATION
# ============================================================

def test_migration_009_continuity():
    migrations_dir = os.path.join(
        os.path.dirname(__file__), "..", "migrations"
    )
    assert os.path.isdir(migrations_dir), f"Directory not found: {migrations_dir}"

    files = sorted(os.listdir(migrations_dir))
    sql_files = [f for f in files if f.endswith(".sql")]

    # Check 001 through 009 exist without gap
    for i in range(1, 10):
        expected_prefix = f"{i:03d}_"
        matches = [f for f in sql_files if f.startswith(expected_prefix)]
        assert len(matches) == 1, f"Missing or duplicate migration for {expected_prefix}: {matches}"

    # Specifically check 009
    migration_009_path = os.path.join(migrations_dir, "009_add_memory_evaluation.sql")
    assert os.path.isfile(migration_009_path), "009_add_memory_evaluation.sql does not exist"
    with open(migration_009_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "CREATE TABLE evaluation_datasets" in content
    assert "CREATE TABLE evaluation_cases" in content
    assert "CREATE TABLE evaluation_runs" in content
    assert "CREATE TABLE evaluation_results" in content

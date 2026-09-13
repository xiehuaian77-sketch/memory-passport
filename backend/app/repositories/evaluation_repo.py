"""Evaluation repository layer for Phase 5.6A (Evaluation Foundation).

Enforces strict tenant isolation (user_id = authenticated user) across all operations.
Cross-user lookups safely return None or False without leaking entity existence.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete as sql_delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation import EvaluationCase, EvaluationDataset, EvaluationResult, EvaluationRun


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# EVALUATION DATASET REPOSITORY
# ============================================================

async def create_dataset(
    db: AsyncSession,
    user_id: str,
    name: str,
    description: str = "",
    is_system: bool = False,
) -> EvaluationDataset:
    """Create a new evaluation dataset owned by user_id."""
    dataset = EvaluationDataset(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=name,
        description=description,
        is_system=is_system,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(dataset)
    await db.flush()
    await db.refresh(dataset)
    return dataset


async def get_dataset(
    db: AsyncSession,
    dataset_id: str,
    user_id: str,
) -> EvaluationDataset | None:
    """Retrieve an evaluation dataset by id for user_id."""
    stmt = select(EvaluationDataset).where(
        EvaluationDataset.id == dataset_id,
        EvaluationDataset.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_datasets(
    db: AsyncSession,
    user_id: str,
    skip: int = 0,
    limit: int = 50,
) -> Sequence[EvaluationDataset]:
    """List evaluation datasets for user_id, ordered by creation date descending."""
    stmt = (
        select(EvaluationDataset)
        .where(EvaluationDataset.user_id == user_id)
        .order_by(desc(EvaluationDataset.created_at))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def delete_dataset(
    db: AsyncSession,
    dataset_id: str,
    user_id: str,
) -> bool:
    """Delete an evaluation dataset if owned by user_id.

    Explicitly cascades deletion to child cases, runs, and results for cross-DB consistency.
    Returns True if deleted, False if not found.
    """
    dataset = await get_dataset(db, dataset_id, user_id)
    if not dataset:
        return False

    # 1. Delete all results for runs in this dataset
    runs_stmt = select(EvaluationRun.id).where(
        EvaluationRun.dataset_id == dataset_id,
        EvaluationRun.user_id == user_id,
    )
    runs_res = await db.execute(runs_stmt)
    run_ids = list(runs_res.scalars().all())
    if run_ids:
        await db.execute(
            sql_delete(EvaluationResult).where(EvaluationResult.run_id.in_(run_ids))
        )

    # 2. Delete all results for cases in this dataset
    cases_stmt = select(EvaluationCase.id).where(
        EvaluationCase.dataset_id == dataset_id,
        EvaluationCase.user_id == user_id,
    )
    cases_res = await db.execute(cases_stmt)
    case_ids = list(cases_res.scalars().all())
    if case_ids:
        await db.execute(
            sql_delete(EvaluationResult).where(EvaluationResult.case_id.in_(case_ids))
        )

    # 3. Delete runs
    await db.execute(
        sql_delete(EvaluationRun).where(
            EvaluationRun.dataset_id == dataset_id,
            EvaluationRun.user_id == user_id,
        )
    )

    # 4. Delete cases
    await db.execute(
        sql_delete(EvaluationCase).where(
            EvaluationCase.dataset_id == dataset_id,
            EvaluationCase.user_id == user_id,
        )
    )

    # 5. Delete dataset
    await db.delete(dataset)
    await db.flush()
    return True


# ============================================================
# EVALUATION CASE REPOSITORY
# ============================================================

async def create_case(
    db: AsyncSession,
    dataset_id: str,
    user_id: str,
    query: str,
    expected_memory_ids: list[str] | None = None,
    expected_relevance: dict[str, float] | None = None,
    tags: str = "",
    temporal_anchor: datetime | None = None,
) -> EvaluationCase | None:
    """Create a new evaluation case under a dataset owned by user_id.

    Returns None if the dataset does not exist or does not belong to user_id.
    """
    dataset = await get_dataset(db, dataset_id, user_id)
    if not dataset:
        return None

    case = EvaluationCase(
        id=str(uuid.uuid4()),
        dataset_id=dataset_id,
        user_id=user_id,
        query=query,
        expected_memory_ids_json=json.dumps(expected_memory_ids or []),
        expected_relevance_json=json.dumps(expected_relevance or {}),
        tags=tags,
        temporal_anchor=temporal_anchor,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(case)
    await db.flush()
    await db.refresh(case)
    return case


async def get_case(
    db: AsyncSession,
    case_id: str,
    user_id: str,
) -> EvaluationCase | None:
    """Retrieve an evaluation case by id for user_id."""
    stmt = select(EvaluationCase).where(
        EvaluationCase.id == case_id,
        EvaluationCase.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_cases(
    db: AsyncSession,
    dataset_id: str,
    user_id: str,
    skip: int = 0,
    limit: int = 100,
) -> Sequence[EvaluationCase]:
    """List evaluation cases in a dataset for user_id."""
    stmt = (
        select(EvaluationCase)
        .where(
            EvaluationCase.dataset_id == dataset_id,
            EvaluationCase.user_id == user_id,
        )
        .order_by(EvaluationCase.created_at)
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def delete_case(
    db: AsyncSession,
    case_id: str,
    user_id: str,
) -> bool:
    """Delete an evaluation case if owned by user_id.

    Returns True if deleted, False if not found.
    """
    case = await get_case(db, case_id, user_id)
    if not case:
        return False
    await db.execute(
        sql_delete(EvaluationResult).where(
            EvaluationResult.case_id == case_id,
            EvaluationResult.user_id == user_id,
        )
    )
    await db.delete(case)
    await db.flush()
    return True


# ============================================================
# EVALUATION RUN REPOSITORY
# ============================================================

async def create_run(
    db: AsyncSession,
    dataset_id: str,
    user_id: str,
    name: str,
    app_version: str = "1.9.0",
    retrieval_config: dict[str, Any] | None = None,
) -> EvaluationRun | None:
    """Create a new evaluation run under a dataset owned by user_id.

    Returns None if the dataset does not exist or does not belong to user_id.
    """
    dataset = await get_dataset(db, dataset_id, user_id)
    if not dataset:
        return None

    run = EvaluationRun(
        id=str(uuid.uuid4()),
        dataset_id=dataset_id,
        user_id=user_id,
        name=name,
        app_version=app_version,
        status="pending",
        retrieval_config_json=json.dumps(retrieval_config or {}),
        summary_metrics_json=None,
        error_message=None,
        created_at=_utcnow(),
        completed_at=None,
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    return run


async def get_run(
    db: AsyncSession,
    run_id: str,
    user_id: str,
) -> EvaluationRun | None:
    """Retrieve an evaluation run by id for user_id."""
    stmt = select(EvaluationRun).where(
        EvaluationRun.id == run_id,
        EvaluationRun.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_runs(
    db: AsyncSession,
    user_id: str,
    dataset_id: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> Sequence[EvaluationRun]:
    """List evaluation runs for user_id, optionally filtered by dataset_id."""
    stmt = select(EvaluationRun).where(EvaluationRun.user_id == user_id)
    if dataset_id:
        stmt = stmt.where(EvaluationRun.dataset_id == dataset_id)
    stmt = stmt.order_by(desc(EvaluationRun.created_at)).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


async def update_run_status(
    db: AsyncSession,
    run_id: str,
    user_id: str,
    status: str,
    summary_metrics: dict[str, Any] | None = None,
    error_message: str | None = None,
    completed_at: datetime | None = None,
) -> EvaluationRun | None:
    """Update status, summary metrics, or error message of an evaluation run.

    Automatically populates completed_at when status is 'completed' or 'failed' if not provided.
    """
    valid_statuses = {"pending", "running", "completed", "failed"}
    if status not in valid_statuses:
        raise ValueError(f"Invalid status: {status}. Must be one of {valid_statuses}")

    run = await get_run(db, run_id, user_id)
    if not run:
        return None

    run.status = status
    if summary_metrics is not None:
        run.summary_metrics_json = json.dumps(summary_metrics)
    if error_message is not None:
        run.error_message = error_message
    if status in {"completed", "failed"}:
        run.completed_at = completed_at or _utcnow()

    await db.flush()
    await db.refresh(run)
    return run


async def delete_run(
    db: AsyncSession,
    run_id: str,
    user_id: str,
) -> bool:
    """Delete an evaluation run if owned by user_id.

    Returns True if deleted, False if not found.
    """
    run = await get_run(db, run_id, user_id)
    if not run:
        return False
    await db.execute(
        sql_delete(EvaluationResult).where(
            EvaluationResult.run_id == run_id,
            EvaluationResult.user_id == user_id,
        )
    )
    await db.delete(run)
    await db.flush()
    return True


# ============================================================
# EVALUATION RESULT REPOSITORY
# ============================================================

async def create_result(
    db: AsyncSession,
    run_id: str,
    case_id: str,
    user_id: str,
    retrieved_memory_ids: list[str] | None = None,
    scores: list[float] | None = None,
    metrics: dict[str, Any] | None = None,
    latency_ms: float = 0.0,
    context_chars: int = 0,
    passed: bool = True,
    details: dict[str, Any] | None = None,
) -> EvaluationResult:
    """Create a single evaluation result."""
    result = EvaluationResult(
        id=str(uuid.uuid4()),
        run_id=run_id,
        case_id=case_id,
        user_id=user_id,
        retrieved_memory_ids_json=json.dumps(retrieved_memory_ids or []),
        scores_json=json.dumps(scores or []),
        metrics_json=json.dumps(metrics or {}),
        latency_ms=latency_ms,
        context_chars=context_chars,
        passed=passed,
        details_json=json.dumps(details) if details is not None else None,
        created_at=_utcnow(),
    )
    db.add(result)
    await db.flush()
    await db.refresh(result)
    return result


async def create_results_bulk(
    db: AsyncSession,
    results_data: list[dict[str, Any]],
) -> list[EvaluationResult]:
    """Bulk create evaluation results."""
    results: list[EvaluationResult] = []
    now = _utcnow()
    for d in results_data:
        res = EvaluationResult(
            id=d.get("id") or str(uuid.uuid4()),
            run_id=d["run_id"],
            case_id=d["case_id"],
            user_id=d["user_id"],
            retrieved_memory_ids_json=json.dumps(d.get("retrieved_memory_ids") or []),
            scores_json=json.dumps(d.get("scores") or []),
            metrics_json=json.dumps(d.get("metrics") or {}),
            latency_ms=float(d.get("latency_ms", 0.0)),
            context_chars=int(d.get("context_chars", 0)),
            passed=bool(d.get("passed", True)),
            details_json=json.dumps(d["details"]) if d.get("details") is not None else None,
            created_at=now,
        )
        db.add(res)
        results.append(res)
    await db.flush()
    for res in results:
        await db.refresh(res)
    return results


async def get_result(
    db: AsyncSession,
    result_id: str,
    user_id: str,
) -> EvaluationResult | None:
    """Retrieve an evaluation result by id for user_id."""
    stmt = select(EvaluationResult).where(
        EvaluationResult.id == result_id,
        EvaluationResult.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_results_for_run(
    db: AsyncSession,
    run_id: str,
    user_id: str,
    skip: int = 0,
    limit: int = 200,
) -> Sequence[EvaluationResult]:
    """List evaluation results belonging to a specific run for user_id."""
    stmt = (
        select(EvaluationResult)
        .where(
            EvaluationResult.run_id == run_id,
            EvaluationResult.user_id == user_id,
        )
        .order_by(EvaluationResult.created_at)
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

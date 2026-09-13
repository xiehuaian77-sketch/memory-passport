"""Evaluation & Memory Quality REST router (Phase 5.6D).

Exposes:
- Dataset management (/api/evaluation/datasets)
- Case management (/api/evaluation/datasets/{id}/cases & /api/evaluation/cases/{id})
- Run lifecycle & execution (/api/evaluation/runs/{id} & /execute)
- Metrics & Results retrieval (/api/evaluation/runs/{id}/metrics & /results)
- Memory Quality evaluation (/api/evaluation/memories/{id}/quality)

Enforces:
- Strict authenticated user tenant isolation (user_id from auth token)
- 404 Not Found on cross-user resource access without leaking existence
- Read-only safety for Memory Quality
- Idempotency / 409 Conflict on repeated run execution
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.repositories import evaluation_repo
from app.schemas.evaluation import (
    EvaluationCaseCreate,
    EvaluationCaseOut,
    EvaluationDatasetCreate,
    EvaluationDatasetOut,
    EvaluationResultOut,
    EvaluationRunCreate,
    EvaluationRunOut,
)
from app.schemas.memory_quality import MemoryQualityResult
from app.services.evaluation_service import EvaluationService
from app.services.memory_quality_service import MemoryQualityService

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


# ============================================================
# DATASET ENDPOINTS
# ============================================================

@router.post(
    "/datasets",
    response_model=EvaluationDatasetOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_dataset(
    body: EvaluationDatasetCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new evaluation dataset for authenticated user."""
    dataset = await evaluation_repo.create_dataset(
        db=db,
        user_id=user.id,
        name=body.name,
        description=body.description,
        is_system=body.is_system,
    )
    return dataset


@router.get(
    "/datasets",
    response_model=list[EvaluationDatasetOut],
    status_code=status.HTTP_200_OK,
)
async def list_datasets(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List evaluation datasets for authenticated user with pagination."""
    datasets = await evaluation_repo.list_datasets(
        db=db,
        user_id=user.id,
        skip=offset,
        limit=limit,
    )
    return datasets


@router.get(
    "/datasets/{dataset_id}",
    response_model=EvaluationDatasetOut,
    status_code=status.HTTP_200_OK,
)
async def get_dataset(
    dataset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get an evaluation dataset by id."""
    dataset = await evaluation_repo.get_dataset(db=db, dataset_id=dataset_id, user_id=user.id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation dataset not found",
        )
    return dataset


# ============================================================
# CASE ENDPOINTS
# ============================================================

@router.post(
    "/datasets/{dataset_id}/cases",
    response_model=EvaluationCaseOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_case(
    dataset_id: str,
    body: EvaluationCaseCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new evaluation case under a dataset."""
    dataset = await evaluation_repo.get_dataset(db=db, dataset_id=dataset_id, user_id=user.id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation dataset not found",
        )

    # Validate expected memories ownership
    try:
        await EvaluationService.validate_expected_memories(
            db, user.id, body.expected_memory_ids
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    case = await evaluation_repo.create_case(
        db=db,
        dataset_id=dataset_id,
        user_id=user.id,
        query=body.query,
        expected_memory_ids=body.expected_memory_ids,
        expected_relevance=body.expected_relevance,
        tags=body.tags,
        temporal_anchor=body.temporal_anchor,
    )
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Failed to create evaluation case",
        )
    return case


@router.get(
    "/datasets/{dataset_id}/cases",
    response_model=list[EvaluationCaseOut],
    status_code=status.HTTP_200_OK,
)
async def list_cases(
    dataset_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List evaluation cases in a dataset with pagination."""
    dataset = await evaluation_repo.get_dataset(db=db, dataset_id=dataset_id, user_id=user.id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation dataset not found",
        )

    cases = await evaluation_repo.list_cases(
        db=db,
        dataset_id=dataset_id,
        user_id=user.id,
        skip=offset,
        limit=limit,
    )
    return cases


@router.get(
    "/cases/{case_id}",
    response_model=EvaluationCaseOut,
    status_code=status.HTTP_200_OK,
)
async def get_case(
    case_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get an evaluation case by id."""
    case = await evaluation_repo.get_case(db=db, case_id=case_id, user_id=user.id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation case not found",
        )
    return case


# ============================================================
# RUN ENDPOINTS
# ============================================================

@router.post(
    "/datasets/{dataset_id}/runs",
    response_model=EvaluationRunOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_run(
    dataset_id: str,
    body: EvaluationRunCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new evaluation run record."""
    dataset = await evaluation_repo.get_dataset(db=db, dataset_id=dataset_id, user_id=user.id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation dataset not found",
        )

    run = await evaluation_repo.create_run(
        db=db,
        dataset_id=dataset_id,
        user_id=user.id,
        name=body.name,
        app_version=body.app_version,
        retrieval_config=body.retrieval_config,
    )
    if not run:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create evaluation run",
        )
    return run


@router.get(
    "/datasets/{dataset_id}/runs",
    response_model=list[EvaluationRunOut],
    status_code=status.HTTP_200_OK,
)
async def list_runs(
    dataset_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List evaluation runs for a dataset."""
    dataset = await evaluation_repo.get_dataset(db=db, dataset_id=dataset_id, user_id=user.id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation dataset not found",
        )

    runs = await evaluation_repo.list_runs(
        db=db,
        user_id=user.id,
        dataset_id=dataset_id,
        skip=offset,
        limit=limit,
    )
    return runs


@router.get(
    "/runs/{run_id}",
    response_model=EvaluationRunOut,
    status_code=status.HTTP_200_OK,
)
async def get_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get an evaluation run by id."""
    run = await evaluation_repo.get_run(db=db, run_id=run_id, user_id=user.id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation run not found",
        )
    return run


@router.post(
    "/runs/{run_id}/execute",
    response_model=EvaluationRunOut,
    status_code=status.HTTP_200_OK,
)
async def execute_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute an existing evaluation run."""
    run = await evaluation_repo.get_run(db=db, run_id=run_id, user_id=user.id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation run not found",
        )

    if run.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Evaluation run has already completed",
        )
    if run.status == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Evaluation run is currently in progress",
        )

    try:
        completed_run = await EvaluationService.execute_existing_run(
            db=db,
            user_id=user.id,
            run_id=run_id,
        )
        return completed_run
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Run execution failed: {exc}",
        )


# ============================================================
# RESULTS & METRICS ENDPOINTS
# ============================================================

@router.get(
    "/runs/{run_id}/results",
    response_model=list[EvaluationResultOut],
    status_code=status.HTTP_200_OK,
)
async def list_results(
    run_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List evaluation results for a run with pagination."""
    run = await evaluation_repo.get_run(db=db, run_id=run_id, user_id=user.id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation run not found",
        )

    results = await evaluation_repo.list_results_for_run(
        db=db,
        run_id=run_id,
        user_id=user.id,
        skip=offset,
        limit=limit,
    )
    return results


@router.get(
    "/runs/{run_id}/metrics",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
)
async def get_metrics(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve summary metrics for an evaluation run."""
    run = await evaluation_repo.get_run(db=db, run_id=run_id, user_id=user.id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation run not found",
        )

    if not run.summary_metrics:
        if run.status == "failed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Run failed: {run.error_message}",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Metrics not available for run; execution has not completed",
        )

    return run.summary_metrics


# ============================================================
# MEMORY QUALITY ENDPOINT
# ============================================================

@router.get(
    "/memories/{memory_id}/quality",
    response_model=MemoryQualityResult,
    status_code=status.HTTP_200_OK,
)
async def get_memory_quality(
    memory_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate memory quality in a strictly read-only, deterministic manner."""
    quality = await MemoryQualityService.evaluate_memory(
        db=db,
        user_id=user.id,
        memory_id=memory_id,
    )
    if not quality:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    return quality

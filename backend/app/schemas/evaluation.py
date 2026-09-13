"""Pydantic schemas for Evaluation REST API (Phase 5.6D)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# DATASET SCHEMAS
# ============================================================

class EvaluationDatasetCreate(BaseModel):
    """Payload to create a new evaluation dataset."""

    name: str = Field(..., min_length=1, max_length=100, description="Dataset title")
    description: str = Field(default="", max_length=1000, description="Detailed dataset description")
    is_system: bool = Field(default=False, description="Whether this is a system-level benchmark dataset")

    model_config = ConfigDict(extra="forbid")


class EvaluationDatasetOut(BaseModel):
    """Output representation of an evaluation dataset."""

    id: str
    user_id: str
    name: str
    description: str
    is_system: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# CASE SCHEMAS
# ============================================================

class EvaluationCaseCreate(BaseModel):
    """Payload to create an evaluation case."""

    query: str = Field(..., min_length=1, max_length=2000, description="Search query under evaluation")
    expected_memory_ids: list[str] = Field(
        default_factory=list, description="Ground truth relevant memory IDs"
    )
    expected_relevance: dict[str, float] = Field(
        default_factory=dict, description="Optional graded relevance mapping memory_id -> score"
    )
    tags: str = Field(default="", max_length=200, description="Comma-separated category/topic tags")
    temporal_anchor: datetime | None = Field(
        default=None, description="Optional historical or future timestamp anchor for validity"
    )

    model_config = ConfigDict(extra="forbid")


class EvaluationCaseOut(BaseModel):
    """Output representation of an evaluation case."""

    id: str
    dataset_id: str
    user_id: str
    query: str
    expected_memory_ids: list[str]
    expected_relevance: dict[str, float]
    tags: str
    temporal_anchor: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# RUN SCHEMAS
# ============================================================

class EvaluationRunCreate(BaseModel):
    """Payload to create an evaluation run."""

    name: str = Field(..., min_length=1, max_length=100, description="Identifier name for this benchmark run")
    app_version: str = Field(default="1.9.0", max_length=50, description="Target app version for reproducibility")
    retrieval_config: dict[str, Any] = Field(
        default_factory=dict, description="Retrieval pipeline parameters (search_mode, top_k, etc.)"
    )

    model_config = ConfigDict(extra="forbid")


class EvaluationRunOut(BaseModel):
    """Output representation of an evaluation run."""

    id: str
    dataset_id: str
    user_id: str
    name: str
    app_version: str
    status: str
    retrieval_config: dict[str, Any]
    summary_metrics: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# RESULT SCHEMAS
# ============================================================

class EvaluationResultOut(BaseModel):
    """Output representation of a single evaluation case result in a run."""

    id: str
    run_id: str
    case_id: str
    user_id: str
    retrieved_memory_ids: list[str]
    scores: list[float]
    metrics: dict[str, Any]
    latency_ms: float
    context_chars: int
    passed: bool
    details: dict[str, Any] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

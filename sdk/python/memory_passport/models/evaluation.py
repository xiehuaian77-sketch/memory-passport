"""Evaluation data models for Memory Passport Python SDK."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from memory_passport.models.common import BaseSDKModel


class EvaluationDataset(BaseSDKModel):
    """Evaluation dataset representation."""

    id: str
    user_id: str
    name: str
    description: str = ""
    is_system: bool = False
    created_at: datetime
    updated_at: datetime


class EvaluationCase(BaseSDKModel):
    """Evaluation test case representation."""

    id: str
    dataset_id: str
    user_id: str
    query: str
    expected_memory_ids: list[str] = Field(default_factory=list)
    expected_relevance: dict[str, float] = Field(default_factory=dict)
    tags: str = ""
    temporal_anchor: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EvaluationRun(BaseSDKModel):
    """Evaluation execution run representation."""

    id: str
    dataset_id: str
    user_id: str
    name: str
    app_version: str = "1.9.0"
    status: str
    retrieval_config: dict[str, Any] = Field(default_factory=dict)
    summary_metrics: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class EvaluationResult(BaseSDKModel):
    """Per-case evaluation result representation."""

    id: str
    run_id: str
    case_id: str
    user_id: str
    retrieved_memory_ids: list[str] = Field(default_factory=list)
    scores: list[float] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    context_chars: int = 0
    passed: bool = True
    details: dict[str, Any] | None = None
    created_at: datetime


class QualityDimensionScore(BaseSDKModel):
    """Score, weight, and reason for an individual quality dimension."""

    name: str
    score: float
    weight: float
    reason: str
    raw_risk: float | None = None


class MemoryQualityResult(BaseSDKModel):
    """Deterministic evaluation of a single memory item's quality."""

    memory_id: str
    user_id: str
    overall_score: float
    dimensions: dict[str, QualityDimensionScore] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    evaluated_at: datetime
    summary_reason: str = ""


# Ergonomic alias
MemoryQuality = MemoryQualityResult


class EvaluationRunMetrics(BaseSDKModel):
    """Aggregated evaluation metrics for a run."""

    run_id: str | None = None
    summary_metrics: dict[str, Any] = Field(default_factory=dict)

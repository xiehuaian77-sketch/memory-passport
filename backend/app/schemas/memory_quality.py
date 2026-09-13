"""Pydantic schemas for Memory Quality Engine (Phase 5.6C)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class QualityDimensionScore(BaseModel):
    """Score, weight, and human-readable explanation for a single quality dimension."""

    name: str = Field(description="Dimension name (e.g. confidence, freshness, consistency)")
    score: float = Field(ge=0.0, le=1.0, description="Normalized quality score in [0.0, 1.0]")
    weight: float = Field(ge=0.0, le=1.0, description="Dimension weight in overall score calculation")
    reason: str = Field(description="Short, explainable reason for the score")
    raw_risk: float | None = Field(
        default=None,
        description="Underlying risk value for risk-type dimensions (duplication, conflict_risk)",
    )


class MemoryQualityResult(BaseModel):
    """Comprehensive, explainable quality assessment for a single memory."""

    memory_id: str = Field(description="Unique identifier of the evaluated memory")
    user_id: str = Field(description="Owner of the memory")
    overall_score: float = Field(ge=0.0, le=1.0, description="Overall weighted quality score in [0.0, 1.0]")
    dimensions: dict[str, QualityDimensionScore] = Field(
        description="Map of dimension name -> QualityDimensionScore"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Actionable quality warnings (e.g. expired, duplicate, conflict)"
    )
    evaluated_at: datetime = Field(description="UTC timestamp of evaluation")
    summary_reason: str = Field(description="High-level explainability summary for overall score")

    model_config = {"from_attributes": True}


class BatchMemoryQualityResult(BaseModel):
    """Batch assessment output."""

    total_evaluated: int
    mean_quality_score: float
    results: list[MemoryQualityResult]

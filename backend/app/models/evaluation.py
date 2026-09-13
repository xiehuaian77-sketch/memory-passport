"""Evaluation ORM models for Phase 5.6A (Evaluation Foundation).

Defines:
- EvaluationDataset
- EvaluationCase
- EvaluationRun
- EvaluationResult
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationDataset(Base):
    """Evaluation dataset container for golden evaluation cases."""

    __tablename__ = "evaluation_datasets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # Relationships
    cases: Mapped[list[EvaluationCase]] = relationship(
        "EvaluationCase",
        back_populates="dataset",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list[EvaluationRun]] = relationship(
        "EvaluationRun",
        back_populates="dataset",
        cascade="all, delete-orphan",
    )


class EvaluationCase(Base):
    """Single evaluation case containing a query and expected memories."""

    __tablename__ = "evaluation_cases"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evaluation_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    expected_memory_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    expected_relevance_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    tags: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    temporal_anchor: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # Relationships
    dataset: Mapped[EvaluationDataset] = relationship(
        "EvaluationDataset", back_populates="cases"
    )
    results: Mapped[list[EvaluationResult]] = relationship(
        "EvaluationResult",
        back_populates="case",
        cascade="all, delete-orphan",
    )

    @property
    def expected_memory_ids(self) -> list[str]:
        """Return parsed expected memory IDs."""
        try:
            return json.loads(self.expected_memory_ids_json)
        except Exception:
            return []

    @expected_memory_ids.setter
    def expected_memory_ids(self, val: list[str]) -> None:
        self.expected_memory_ids_json = json.dumps(val or [])

    @property
    def expected_relevance(self) -> dict[str, float]:
        """Return parsed expected relevance dict mapping memory_id -> score."""
        try:
            return json.loads(self.expected_relevance_json)
        except Exception:
            return {}

    @expected_relevance.setter
    def expected_relevance(self, val: dict[str, float]) -> None:
        self.expected_relevance_json = json.dumps(val or {})


class EvaluationRun(Base):
    """Execution run of an evaluation dataset under specific retrieval parameters."""

    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evaluation_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    app_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.9.0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    retrieval_config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    summary_metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    dataset: Mapped[EvaluationDataset] = relationship(
        "EvaluationDataset", back_populates="runs"
    )
    results: Mapped[list[EvaluationResult]] = relationship(
        "EvaluationResult",
        back_populates="run",
        cascade="all, delete-orphan",
    )

    @property
    def retrieval_config(self) -> dict[str, Any]:
        """Return parsed retrieval config dictionary."""
        try:
            return json.loads(self.retrieval_config_json)
        except Exception:
            return {}

    @retrieval_config.setter
    def retrieval_config(self, val: dict[str, Any]) -> None:
        self.retrieval_config_json = json.dumps(val or {})

    @property
    def summary_metrics(self) -> dict[str, Any] | None:
        """Return parsed summary metrics dictionary."""
        if not self.summary_metrics_json:
            return None
        try:
            return json.loads(self.summary_metrics_json)
        except Exception:
            return None

    @summary_metrics.setter
    def summary_metrics(self, val: dict[str, Any] | None) -> None:
        if val is None:
            self.summary_metrics_json = None
        else:
            self.summary_metrics_json = json.dumps(val)


class EvaluationResult(Base):
    """Result of evaluating a single case in an evaluation run."""

    __tablename__ = "evaluation_results"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evaluation_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    retrieved_memory_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    scores_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    context_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # Relationships
    run: Mapped[EvaluationRun] = relationship("EvaluationRun", back_populates="results")
    case: Mapped[EvaluationCase] = relationship("EvaluationCase", back_populates="results")

    @property
    def retrieved_memory_ids(self) -> list[str]:
        try:
            return json.loads(self.retrieved_memory_ids_json)
        except Exception:
            return []

    @retrieved_memory_ids.setter
    def retrieved_memory_ids(self, val: list[str]) -> None:
        self.retrieved_memory_ids_json = json.dumps(val or [])

    @property
    def scores(self) -> list[float]:
        try:
            return json.loads(self.scores_json)
        except Exception:
            return []

    @scores.setter
    def scores(self, val: list[float]) -> None:
        self.scores_json = json.dumps(val or [])

    @property
    def metrics(self) -> dict[str, Any]:
        try:
            return json.loads(self.metrics_json)
        except Exception:
            return {}

    @metrics.setter
    def metrics(self, val: dict[str, Any]) -> None:
        self.metrics_json = json.dumps(val or {})

    @property
    def details(self) -> dict[str, Any] | None:
        if not self.details_json:
            return None
        try:
            return json.loads(self.details_json)
        except Exception:
            return None

    @details.setter
    def details(self, val: dict[str, Any] | None) -> None:
        if val is None:
            self.details_json = None
        else:
            self.details_json = json.dumps(val)

"""Evaluation Service orchestrator for Phase 5.6B/D.

Connects:
Dataset / Cases -> Production Retrieval Pipeline -> Metrics Calculation -> Persistence.
Enforces:
- Strict authenticated user tenant isolation
- Validates expected_memory_ids ownership
- Bounded batch execution to prevent OOM
- Monotonic latency measurement excluding DB overhead
- Reproducible version & retrieval config recording
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation import EvaluationCase, EvaluationResult, EvaluationRun
from app.models.memory import Memory
from app.providers.embedding_provider import EmbeddingProvider
from app.repositories import evaluation_repo, memory_repo
from app.schemas.memory import MemoryRetrievalRequest
from app.services import evaluation_metrics, memory_service

logger = logging.getLogger(__name__)

DEFAULT_APP_VERSION = "1.9.0"


class EvaluationService:
    """Orchestrates retrieval evaluation runs and calculates IR metrics."""

    @staticmethod
    async def validate_expected_memories(
        db: AsyncSession,
        user_id: str,
        expected_memory_ids: Sequence[str],
    ) -> None:
        """Ensure all expected memory IDs belong strictly to the authenticated user.

        Raises ValueError if any ID does not belong to user_id (prevents cross-tenant leaks).
        """
        if not expected_memory_ids:
            return

        unique_ids = list(dict.fromkeys(expected_memory_ids))
        stmt = select(Memory.id).where(
            Memory.id.in_(unique_ids),
            Memory.user_id == user_id,
        )
        result = await db.execute(stmt)
        owned_ids = set(result.scalars().all())

        if len(owned_ids) != len(unique_ids):
            raise ValueError(
                "Invalid expected_memory_ids: one or more memories do not exist or access is denied"
            )

    @classmethod
    async def evaluate_single_case(
        cls,
        db: AsyncSession,
        user_id: str,
        case: EvaluationCase,
        retrieval_config: dict[str, Any],
        embedding_provider: EmbeddingProvider | None = None,
    ) -> dict[str, Any]:
        """Execute retrieval for a single case and compute its IR metrics.

        Measures latency strictly around the retrieval pipeline invocation using time.perf_counter().
        """
        # 1. Enforce tenant isolation on expected memory IDs
        await cls.validate_expected_memories(db, user_id, case.expected_memory_ids)

        search_mode = retrieval_config.get("search_mode", "retrieve")
        top_k = int(retrieval_config.get("top_k", 10))
        status_filter = retrieval_config.get("status", "active")
        temporal_mode = retrieval_config.get("temporal_mode", "current")
        ref_time = case.temporal_anchor or retrieval_config.get("reference_time")

        retrieved_ids: list[str] = []
        scores: list[float] = []
        context_chars = 0

        # 2. Invoke appropriate production retrieval branch with strict monotonic timing
        t0 = time.perf_counter()

        if search_mode in ("retrieve", "context"):
            req = MemoryRetrievalRequest(
                query=case.query,
                top_k=top_k,
                min_relevance=float(retrieval_config.get("min_relevance", 0.30)),
                min_importance=float(retrieval_config.get("min_importance", 0.0)),
                min_confidence=float(retrieval_config.get("min_confidence", 0.0)),
                memory_types=retrieval_config.get("memory_types"),
                recency_half_life_days=float(
                    retrieval_config.get("recency_half_life_days", 30.0)
                ),
                status=status_filter,
                temporal_mode=temporal_mode,
                reference_time=ref_time,
                graph_enabled=bool(retrieval_config.get("graph_enabled", False)),
                graph_seed_limit=int(retrieval_config.get("graph_seed_limit", 5)),
                graph_max_expanded=int(retrieval_config.get("graph_max_expanded", 20)),
                max_memories=int(retrieval_config.get("max_memories", 10)),
                max_content_chars=int(retrieval_config.get("max_content_chars", 500)),
                max_context_chars=int(retrieval_config.get("max_context_chars", 4000)),
            )
            assembled = await memory_service.retrieve_context(
                db,
                user_id=user_id,
                request=req,
                embedding_provider=embedding_provider,
            )
            retrieved_ids = [item.id for item in assembled.items]
            scores = [round(item.retrieval_score, 4) for item in assembled.items]
            context_chars = assembled.total_chars

        elif search_mode == "hybrid":
            hybrid_res = await memory_service.hybrid_search(
                db,
                user_id=user_id,
                query=case.query,
                limit=top_k,
                status=status_filter,
                embedding_provider=embedding_provider,
            )
            retrieved_ids = [r.memory.id for r in hybrid_res]
            scores = [round(r.hybrid_score, 4) for r in hybrid_res]
            context_chars = sum(len(r.memory.content) for r in hybrid_res)

        elif search_mode == "semantic":
            sem_res = await memory_service.search_memories(
                db,
                user_id=user_id,
                query=case.query,
                top_k=top_k,
            )
            retrieved_ids = [mem.id for mem, _ in sem_res]
            scores = [round(sc, 4) for _, sc in sem_res]
            context_chars = sum(len(mem.content) for mem, _ in sem_res)

        elif search_mode == "keyword":
            kw_res = await memory_repo.keyword_search(
                db,
                user_id=user_id,
                query=case.query,
                limit=top_k,
                status=status_filter,
            )
            retrieved_ids = [mem.id for mem, _ in kw_res]
            scores = [round(sc, 4) for _, sc in kw_res]
            context_chars = sum(len(mem.content) for mem, _ in kw_res)

        else:
            raise ValueError(f"Unsupported search_mode: '{search_mode}'")

        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        # 3. Calculate deterministic IR metrics
        metrics = evaluation_metrics.calculate_case_metrics(
            retrieved=retrieved_ids,
            expected=case.expected_memory_ids,
            relevance=case.expected_relevance,
        )

        # 4. Determine passed flag: if expected IDs given, must retrieve >= 1 relevant item
        if case.expected_memory_ids:
            passed = len(set(retrieved_ids) & set(case.expected_memory_ids)) > 0
        else:
            passed = True

        return {
            "case_id": case.id,
            "user_id": user_id,
            "retrieved_memory_ids": retrieved_ids,
            "scores": scores,
            "metrics": metrics,
            "latency_ms": latency_ms,
            "context_chars": context_chars,
            "passed": passed,
            "details": {
                "query": case.query,
                "search_mode": search_mode,
                "tags": case.tags,
            },
        }

    @classmethod
    async def _execute_run_internal(
        cls,
        db: AsyncSession,
        user_id: str,
        run: EvaluationRun,
        batch_size: int = 50,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> EvaluationRun:
        """Internal runner for executing cases and computing summary metrics."""
        config = run.retrieval_config or {}
        all_case_metrics: list[dict[str, Any]] = []
        all_latencies: list[float] = []

        try:
            offset = 0
            while True:
                cases = await evaluation_repo.list_cases(
                    db, dataset_id=run.dataset_id, user_id=user_id, skip=offset, limit=batch_size
                )
                if not cases:
                    break

                batch_results_data: list[dict[str, Any]] = []
                for case in cases:
                    case_res = await cls.evaluate_single_case(
                        db=db,
                        user_id=user_id,
                        case=case,
                        retrieval_config=config,
                        embedding_provider=embedding_provider,
                    )
                    all_case_metrics.append(case_res["metrics"])
                    all_latencies.append(case_res["latency_ms"])

                    batch_results_data.append(
                        {
                            "run_id": run.id,
                            "case_id": case.id,
                            "user_id": user_id,
                            "retrieved_memory_ids": case_res["retrieved_memory_ids"],
                            "scores": case_res["scores"],
                            "metrics": case_res["metrics"],
                            "latency_ms": case_res["latency_ms"],
                            "context_chars": case_res["context_chars"],
                            "passed": case_res["passed"],
                            "details": case_res["details"],
                        }
                    )

                if batch_results_data:
                    await evaluation_repo.create_results_bulk(db, batch_results_data)

                offset += len(cases)

            # Aggregate run summary metrics
            summary = evaluation_metrics.aggregate_run_metrics(
                all_case_metrics, all_latencies
            )
            total_cases = len(all_case_metrics)
            passed_cases = sum(
                1 for m in all_case_metrics if m.get("recall_at_k", {}).get("10", 0.0) > 0 or m.get("mrr", 0.0) > 0
            )
            summary["passed_cases"] = passed_cases
            summary["pass_rate"] = round(passed_cases / total_cases, 4) if total_cases > 0 else 1.0

            completed_run = await evaluation_repo.update_run_status(
                db,
                run_id=run.id,
                user_id=user_id,
                status="completed",
                summary_metrics=summary,
            )
            return completed_run or run

        except Exception as exc:
            logger.exception("Evaluation run failed: %s", exc)
            await evaluation_repo.update_run_status(
                db,
                run_id=run.id,
                user_id=user_id,
                status="failed",
                error_message=str(exc),
            )
            raise

    @classmethod
    async def run_evaluation(
        cls,
        db: AsyncSession,
        user_id: str,
        dataset_id: str,
        name: str,
        retrieval_config: dict[str, Any] | None = None,
        app_version: str = DEFAULT_APP_VERSION,
        batch_size: int = 50,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> EvaluationRun:
        """Create and run an end-to-end evaluation over an EvaluationDataset."""
        dataset = await evaluation_repo.get_dataset(db, dataset_id, user_id)
        if not dataset:
            raise ValueError(f"Dataset '{dataset_id}' not found or access denied")

        config = retrieval_config or {}

        run = await evaluation_repo.create_run(
            db,
            dataset_id=dataset_id,
            user_id=user_id,
            name=name,
            app_version=app_version,
            retrieval_config=config,
        )
        if not run:
            raise RuntimeError("Failed to create evaluation run record")

        await evaluation_repo.update_run_status(
            db, run_id=run.id, user_id=user_id, status="running"
        )

        return await cls._execute_run_internal(
            db=db,
            user_id=user_id,
            run=run,
            batch_size=batch_size,
            embedding_provider=embedding_provider,
        )

    @classmethod
    async def execute_existing_run(
        cls,
        db: AsyncSession,
        user_id: str,
        run_id: str,
        batch_size: int = 50,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> EvaluationRun:
        """Execute an existing evaluation run (pending or re-running failed).

        Raises ValueError if not found, or RuntimeError if already completed or currently running.
        """
        run = await evaluation_repo.get_run(db, run_id, user_id)
        if not run:
            raise ValueError(f"Run '{run_id}' not found or access denied")

        if run.status == "completed":
            raise RuntimeError("Evaluation run has already completed")
        if run.status == "running":
            raise RuntimeError("Evaluation run is currently in progress")

        # Clean up any existing results (e.g. from previously failed run)
        await db.execute(
            sql_delete(EvaluationResult).where(
                EvaluationResult.run_id == run_id,
                EvaluationResult.user_id == user_id,
            )
        )
        await db.flush()

        # Update status to running
        await evaluation_repo.update_run_status(
            db, run_id=run.id, user_id=user_id, status="running", error_message=None
        )

        return await cls._execute_run_internal(
            db=db,
            user_id=user_id,
            run=run,
            batch_size=batch_size,
            embedding_provider=embedding_provider,
        )

    @classmethod
    async def get_run(
        cls,
        db: AsyncSession,
        user_id: str,
        run_id: str,
    ) -> EvaluationRun | None:
        """Retrieve an evaluation run by id for authenticated user."""
        return await evaluation_repo.get_run(db, run_id=run_id, user_id=user_id)

    @classmethod
    async def list_runs(
        cls,
        db: AsyncSession,
        user_id: str,
        dataset_id: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[EvaluationRun]:
        """List evaluation runs for authenticated user."""
        return await evaluation_repo.list_runs(
            db, user_id=user_id, dataset_id=dataset_id, skip=skip, limit=limit
        )

    @classmethod
    async def get_run_results(
        cls,
        db: AsyncSession,
        user_id: str,
        run_id: str,
        skip: int = 0,
        limit: int = 200,
    ) -> Sequence[EvaluationResult]:
        """List evaluation results for a specific run."""
        return await evaluation_repo.list_results_for_run(
            db, run_id=run_id, user_id=user_id, skip=skip, limit=limit
        )

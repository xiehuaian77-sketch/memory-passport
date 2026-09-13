"""Evaluation resource client."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

from memory_passport.models.common import SyncPage
from memory_passport.models.evaluation import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationResult,
    EvaluationRun,
    MemoryQualityResult,
)
from memory_passport.pagination import Paginator
from memory_passport.transport import MemoryPassportTransport


class EvaluationResource:
    """Resource client for /api/evaluation endpoints."""

    def __init__(self, transport: MemoryPassportTransport) -> None:
        self._transport = transport

    # --- Datasets ---

    def create_dataset(
        self,
        *,
        name: str,
        description: str = "",
        is_system: bool = False,
    ) -> EvaluationDataset:
        payload = {
            "name": name,
            "description": description,
            "is_system": is_system,
        }
        res = self._transport.request("POST", "/api/evaluation/datasets", json=payload)
        return EvaluationDataset.model_validate(res)

    def get_dataset(self, dataset_id: str) -> EvaluationDataset:
        res = self._transport.request("GET", f"/api/evaluation/datasets/{dataset_id}")
        return EvaluationDataset.model_validate(res)

    def list_datasets(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> SyncPage[EvaluationDataset]:
        params = {"offset": offset, "limit": limit}
        res = self._transport.request("GET", "/api/evaluation/datasets", params=params)
        items = [EvaluationDataset.model_validate(d) for d in res]
        return SyncPage(items=items, offset=offset, limit=limit, total=None)

    def iter_datasets(
        self,
        *,
        page_size: int = 50,
        max_items: int | None = None,
    ) -> Iterator[EvaluationDataset]:
        def fetcher(offset: int, limit: int) -> SyncPage[EvaluationDataset]:
            return self.list_datasets(offset=offset, limit=limit)

        return iter(Paginator(fetcher, page_size=page_size, max_items=max_items))

    # --- Test Cases ---

    def create_case(
        self,
        dataset_id: str,
        *,
        query: str,
        expected_memory_ids: list[str] | None = None,
        expected_relevance: dict[str, float] | None = None,
        tags: str = "",
        temporal_anchor: datetime | None = None,
    ) -> EvaluationCase:
        payload = {
            "query": query,
            "expected_memory_ids": expected_memory_ids or [],
            "expected_relevance": expected_relevance or {},
            "tags": tags,
            "temporal_anchor": temporal_anchor.isoformat() if temporal_anchor else None,
        }
        res = self._transport.request(
            "POST", f"/api/evaluation/datasets/{dataset_id}/cases", json=payload
        )
        return EvaluationCase.model_validate(res)

    def get_case(self, case_id: str) -> EvaluationCase:
        res = self._transport.request("GET", f"/api/evaluation/cases/{case_id}")
        return EvaluationCase.model_validate(res)

    def list_cases(
        self,
        dataset_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> SyncPage[EvaluationCase]:
        params = {"offset": offset, "limit": limit}
        res = self._transport.request(
            "GET", f"/api/evaluation/datasets/{dataset_id}/cases", params=params
        )
        items = [EvaluationCase.model_validate(c) for c in res]
        return SyncPage(items=items, offset=offset, limit=limit, total=None)

    def iter_cases(
        self,
        dataset_id: str,
        *,
        page_size: int = 50,
        max_items: int | None = None,
    ) -> Iterator[EvaluationCase]:
        def fetcher(offset: int, limit: int) -> SyncPage[EvaluationCase]:
            return self.list_cases(dataset_id, offset=offset, limit=limit)

        return iter(Paginator(fetcher, page_size=page_size, max_items=max_items))

    # --- Evaluation Runs ---

    def create_run(
        self,
        dataset_id: str,
        *,
        name: str = "Benchmark Run",
        app_version: str = "1.9.0",
        retrieval_config: dict[str, Any] | None = None,
    ) -> EvaluationRun:
        payload = {
            "name": name,
            "app_version": app_version,
            "retrieval_config": retrieval_config or {},
        }
        res = self._transport.request(
            "POST", f"/api/evaluation/datasets/{dataset_id}/runs", json=payload
        )
        return EvaluationRun.model_validate(res)

    def get_run(self, run_id: str) -> EvaluationRun:
        res = self._transport.request("GET", f"/api/evaluation/runs/{run_id}")
        return EvaluationRun.model_validate(res)

    def list_runs(
        self,
        dataset_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> SyncPage[EvaluationRun]:
        params = {"offset": offset, "limit": limit}
        res = self._transport.request(
            "GET", f"/api/evaluation/datasets/{dataset_id}/runs", params=params
        )
        items = [EvaluationRun.model_validate(r) for r in res]
        return SyncPage(items=items, offset=offset, limit=limit, total=None)

    def iter_runs(
        self,
        dataset_id: str,
        *,
        page_size: int = 50,
        max_items: int | None = None,
    ) -> Iterator[EvaluationRun]:
        def fetcher(offset: int, limit: int) -> SyncPage[EvaluationRun]:
            return self.list_runs(dataset_id, offset=offset, limit=limit)

        return iter(Paginator(fetcher, page_size=page_size, max_items=max_items))

    def execute_run(self, run_id: str) -> EvaluationRun:
        res = self._transport.request("POST", f"/api/evaluation/runs/{run_id}/execute")
        return EvaluationRun.model_validate(res)

    # --- Results & Metrics ---

    def list_results(
        self,
        run_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> SyncPage[EvaluationResult]:
        params = {"offset": offset, "limit": limit}
        res = self._transport.request(
            "GET", f"/api/evaluation/runs/{run_id}/results", params=params
        )
        items = [EvaluationResult.model_validate(r) for r in res]
        return SyncPage(items=items, offset=offset, limit=limit, total=None)

    def iter_results(
        self,
        run_id: str,
        *,
        page_size: int = 50,
        max_items: int | None = None,
    ) -> Iterator[EvaluationResult]:
        def fetcher(offset: int, limit: int) -> SyncPage[EvaluationResult]:
            return self.list_results(run_id, offset=offset, limit=limit)

        return iter(Paginator(fetcher, page_size=page_size, max_items=max_items))

    def get_metrics(self, run_id: str) -> dict[str, Any]:
        return self._transport.request("GET", f"/api/evaluation/runs/{run_id}/metrics")

    # --- Memory Quality ---

    def get_memory_quality(self, memory_id: str) -> MemoryQualityResult:
        res = self._transport.request("GET", f"/api/evaluation/memories/{memory_id}/quality")
        return MemoryQualityResult.model_validate(res)

"""Evaluation metrics engine for Information Retrieval (Phase 5.6B).

Provides deterministic, robust, zero-division protected implementations of:
- Precision@K
- Recall@K
- MRR (Mean Reciprocal Rank)
- MAP (Mean Average Precision)
- NDCG@K (Discounted Cumulative Gain, supports binary & graded relevance)
- Latency statistics (mean, min, max, p50, p95, p99)
- Run-level metric aggregation
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any


def precision_at_k(
    retrieved: Sequence[str],
    expected: Sequence[str],
    k: int,
) -> float:
    """Compute Precision@K.

    Precision@K = (unique relevant items retrieved in top K) / K.
    - If K <= 0, raises ValueError.
    - If expected is empty (no relevant items exist), returns 0.0.
    - If len(retrieved) < K, unretrieved slots are treated as non-relevant (divisor is still K).
    - Prevents duplicate items in retrieved from counting multiple times.
    """
    if k <= 0:
        raise ValueError(f"k must be a positive integer >= 1, got {k}")

    expected_set = set(expected)
    if not expected_set:
        return 0.0

    retrieved_in_k = retrieved[:k]
    # Count distinct relevant items retrieved in top K
    relevant_found = len(set(retrieved_in_k) & expected_set)
    return round(relevant_found / k, 4)


def recall_at_k(
    retrieved: Sequence[str],
    expected: Sequence[str],
    k: int,
) -> float:
    """Compute Recall@K.

    Recall@K = (unique relevant items retrieved in top K) / (total relevant items in expected).
    - If K <= 0, raises ValueError.
    - If expected is empty, returns 0.0 (prevents division by zero, no NaN/Infinity).
    """
    if k <= 0:
        raise ValueError(f"k must be a positive integer >= 1, got {k}")

    expected_set = set(expected)
    if not expected_set:
        return 0.0

    retrieved_in_k = retrieved[:k]
    relevant_found = len(set(retrieved_in_k) & expected_set)
    return round(relevant_found / len(expected_set), 4)


def reciprocal_rank(
    retrieved: Sequence[str],
    expected: Sequence[str],
) -> float:
    """Compute Reciprocal Rank for a single query.

    RR = 1.0 / rank(first relevant retrieved item).
    Returns 0.0 if no relevant item is found in retrieved or if expected is empty.
    """
    expected_set = set(expected)
    if not expected_set:
        return 0.0

    for rank, mid in enumerate(retrieved, start=1):
        if mid in expected_set:
            return round(1.0 / rank, 4)

    return 0.0


def average_precision(
    retrieved: Sequence[str],
    expected: Sequence[str],
) -> float:
    """Compute Average Precision (AP) for a single query.

    AP = sum(P@i for i where retrieved[i] is relevant) / total_relevant.
    Returns 0.0 if expected is empty or if no relevant items are retrieved.
    """
    expected_set = set(expected)
    if not expected_set:
        return 0.0

    sum_precision = 0.0
    relevant_count = 0
    seen: set[str] = set()

    for rank, mid in enumerate(retrieved, start=1):
        if mid in expected_set and mid not in seen:
            seen.add(mid)
            relevant_count += 1
            sum_precision += relevant_count / rank

    if relevant_count == 0:
        return 0.0

    return round(sum_precision / len(expected_set), 4)


def _build_relevance_map(
    expected: Sequence[str],
    relevance: dict[str, float] | None = None,
) -> dict[str, float]:
    """Build float relevance map from expected list and optional relevance dict."""
    rel_map: dict[str, float] = {}
    if relevance is not None and len(relevance) > 0:
        for k, v in relevance.items():
            try:
                score = float(v)
                rel_map[str(k)] = max(0.0, score)
            except (ValueError, TypeError):
                continue
        for mid in expected:
            if str(mid) not in rel_map:
                rel_map[str(mid)] = 1.0
    else:
        for mid in expected:
            rel_map[str(mid)] = 1.0

    return rel_map


def dcg_at_k(
    retrieved: Sequence[str],
    relevance_map: dict[str, float],
    k: int,
) -> float:
    """Compute Discounted Cumulative Gain at K (DCG@K).

    DCG@K = sum_{i=1}^{min(k, |retrieved|)} (2^{rel_i} - 1) / log2(i + 1).
    """
    if k <= 0:
        raise ValueError(f"k must be >= 1, got {k}")

    dcg = 0.0
    top_items = retrieved[:k]
    for i, mid in enumerate(top_items, start=1):
        rel = relevance_map.get(str(mid), 0.0)
        if rel > 0.0:
            gain = (2.0 ** rel) - 1.0
            discount = math.log2(i + 1)
            dcg += gain / discount

    return dcg


def idcg_at_k(
    relevance_map: dict[str, float],
    k: int,
) -> float:
    """Compute Ideal Discounted Cumulative Gain at K (IDCG@K).

    Sorts all positive relevance scores in descending order and computes DCG@K.
    """
    if k <= 0:
        raise ValueError(f"k must be >= 1, got {k}")

    ideal_scores = sorted(
        [score for score in relevance_map.values() if score > 0.0],
        reverse=True,
    )[:k]

    idcg = 0.0
    for i, score in enumerate(ideal_scores, start=1):
        gain = (2.0 ** score) - 1.0
        discount = math.log2(i + 1)
        idcg += gain / discount

    return idcg


def ndcg_at_k(
    retrieved: Sequence[str],
    expected: Sequence[str],
    relevance: dict[str, float] | None = None,
    k: int = 5,
) -> float:
    """Compute Normalized Discounted Cumulative Gain at K (NDCG@K).

    Supports both graded relevance and binary relevance.
    If IDCG@K == 0.0, returns 0.0 (prevents division by zero).
    """
    if k <= 0:
        raise ValueError(f"k must be >= 1, got {k}")

    rel_map = _build_relevance_map(expected, relevance)
    if not rel_map:
        return 0.0

    idcg = idcg_at_k(rel_map, k)
    if idcg == 0.0:
        return 0.0

    dcg = dcg_at_k(retrieved, rel_map, k)
    ndcg = dcg / idcg
    return round(min(1.0, max(0.0, ndcg)), 4)


def calculate_case_metrics(
    retrieved: Sequence[str],
    expected: Sequence[str],
    relevance: dict[str, float] | None = None,
    ks: Sequence[int] = (1, 3, 5, 10),
) -> dict[str, Any]:
    """Calculate all standard IR metrics for a single evaluation case."""
    p_at_k: dict[str, float] = {}
    r_at_k: dict[str, float] = {}
    ndcg_dict: dict[str, float] = {}

    for k in ks:
        p_at_k[str(k)] = precision_at_k(retrieved, expected, k)
        r_at_k[str(k)] = recall_at_k(retrieved, expected, k)
        if k in (5, 10):
            ndcg_dict[str(k)] = ndcg_at_k(retrieved, expected, relevance, k=k)

    # Ensure 5 and 10 exist in ndcg_dict even if ks didn't explicitly specify them
    if "5" not in ndcg_dict:
        ndcg_dict["5"] = ndcg_at_k(retrieved, expected, relevance, k=5)
    if "10" not in ndcg_dict:
        ndcg_dict["10"] = ndcg_at_k(retrieved, expected, relevance, k=10)

    mrr_val = reciprocal_rank(retrieved, expected)
    ap_val = average_precision(retrieved, expected)

    return {
        "precision_at_k": p_at_k,
        "recall_at_k": r_at_k,
        "mrr": mrr_val,
        "ndcg_at_k": ndcg_dict,
        "map": ap_val,
    }


def aggregate_run_metrics(
    case_metrics_list: Sequence[dict[str, Any]],
    latencies: Sequence[float],
) -> dict[str, Any]:
    """Aggregate individual case metrics into dataset / run-level summary metrics."""
    total_cases = len(case_metrics_list)
    if total_cases == 0:
        return {
            "total_cases": 0,
            "precision_at_k": {"1": 0.0, "3": 0.0, "5": 0.0, "10": 0.0},
            "recall_at_k": {"1": 0.0, "3": 0.0, "5": 0.0, "10": 0.0},
            "mrr": 0.0,
            "ndcg_at_k": {"5": 0.0, "10": 0.0},
            "map": 0.0,
            "latency": {
                "mean_ms": 0.0,
                "min_ms": 0.0,
                "max_ms": 0.0,
                "p50_ms": 0.0,
                "p95_ms": 0.0,
                "p99_ms": 0.0,
            },
        }

    # Aggregate precision and recall at K
    ks = ["1", "3", "5", "10"]
    agg_precision: dict[str, float] = {}
    agg_recall: dict[str, float] = {}
    for k in ks:
        p_vals = [m["precision_at_k"].get(k, 0.0) for m in case_metrics_list if "precision_at_k" in m]
        r_vals = [m["recall_at_k"].get(k, 0.0) for m in case_metrics_list if "recall_at_k" in m]
        agg_precision[k] = round(sum(p_vals) / total_cases, 4) if p_vals else 0.0
        agg_recall[k] = round(sum(r_vals) / total_cases, 4) if r_vals else 0.0

    # Aggregate NDCG at 5 and 10
    agg_ndcg: dict[str, float] = {}
    for k in ["5", "10"]:
        ndcg_vals = [m["ndcg_at_k"].get(k, 0.0) for m in case_metrics_list if "ndcg_at_k" in m]
        agg_ndcg[k] = round(sum(ndcg_vals) / total_cases, 4) if ndcg_vals else 0.0

    # MRR and MAP
    mrr_vals = [m.get("mrr", 0.0) for m in case_metrics_list]
    map_vals = [m.get("map", 0.0) for m in case_metrics_list]
    mean_mrr = round(sum(mrr_vals) / total_cases, 4)
    mean_map = round(sum(map_vals) / total_cases, 4)

    # Latency statistics
    sorted_latencies = sorted(latencies) if latencies else [0.0]
    n_lat = len(sorted_latencies)

    def _percentile(data: list[float], pct: float) -> float:
        if not data:
            return 0.0
        idx = int(math.ceil(pct * len(data))) - 1
        idx = max(0, min(idx, len(data) - 1))
        return round(data[idx], 2)

    latency_stats = {
        "mean_ms": round(sum(sorted_latencies) / n_lat, 2),
        "min_ms": round(sorted_latencies[0], 2),
        "max_ms": round(sorted_latencies[-1], 2),
        "p50_ms": _percentile(sorted_latencies, 0.50),
        "p95_ms": _percentile(sorted_latencies, 0.95),
        "p99_ms": _percentile(sorted_latencies, 0.99),
    }

    return {
        "total_cases": total_cases,
        "precision_at_k": agg_precision,
        "recall_at_k": agg_recall,
        "mrr": mean_mrr,
        "ndcg_at_k": agg_ndcg,
        "map": mean_map,
        "latency": latency_stats,
    }

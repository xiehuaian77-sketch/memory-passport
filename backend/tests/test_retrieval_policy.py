"""Phase 2.5A: Memory Retrieval Policy tests."""

from datetime import datetime, timedelta, timezone

import pytest
from app.models.memory import Memory
from app.services.memory_service import HybridSearchResult
from app.services.retrieval_policy import (
    MemoryRetrievalPolicy,
    RetrievalPolicyConfig,
    ScoredMemory,
)
from pydantic import ValidationError


def make_memory(
    mem_id: str,
    content: str = "Test memory",
    memory_type: str = "preference",
    importance: float = 0.5,
    confidence: float = 1.0,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> Memory:
    """Helper to instantiate Memory model for unit testing."""
    now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
    mem = Memory(
        id=mem_id,
        user_id="user_123",
        memory_type=memory_type,
        key=f"key_{mem_id}",
        content=content,
        importance=importance,
        confidence=confidence,
        created_at=created_at or now,
        updated_at=updated_at or now,
    )
    return mem


# ────────────────────── 1: Filter min_relevance ──────────────────────

def test_filter_min_relevance():
    """Candidates with hybrid_score below min_relevance must be excluded."""
    now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
    policy = MemoryRetrievalPolicy(RetrievalPolicyConfig(min_relevance=0.30))

    candidates = [
        HybridSearchResult(memory=make_memory("m1"), similarity=0.25, keyword_score=0.25, hybrid_score=0.25),
        HybridSearchResult(memory=make_memory("m2"), similarity=0.30, keyword_score=0.30, hybrid_score=0.30),
        HybridSearchResult(memory=make_memory("m3"), similarity=0.60, keyword_score=0.40, hybrid_score=0.54),
    ]

    results = policy.apply(candidates, now=now)
    ids = [r.memory.id for r in results]
    assert "m1" not in ids
    assert "m2" in ids
    assert "m3" in ids


# ────────────────────── 2: Filter min_importance ──────────────────────

def test_filter_min_importance():
    """Candidates with importance below min_importance must be excluded."""
    now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
    policy = MemoryRetrievalPolicy(RetrievalPolicyConfig(min_importance=0.50))

    candidates = [
        HybridSearchResult(memory=make_memory("m1", importance=0.2), similarity=0.8, keyword_score=0.8, hybrid_score=0.8),
        HybridSearchResult(memory=make_memory("m2", importance=0.5), similarity=0.8, keyword_score=0.8, hybrid_score=0.8),
        HybridSearchResult(memory=make_memory("m3", importance=0.9), similarity=0.8, keyword_score=0.8, hybrid_score=0.8),
    ]

    results = policy.apply(candidates, now=now)
    ids = [r.memory.id for r in results]
    assert "m1" not in ids
    assert "m2" in ids
    assert "m3" in ids


# ────────────────────── 3: Filter min_confidence ──────────────────────

def test_filter_min_confidence():
    """Candidates with confidence below min_confidence must be excluded."""
    now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
    policy = MemoryRetrievalPolicy(RetrievalPolicyConfig(min_confidence=0.70))

    candidates = [
        HybridSearchResult(memory=make_memory("m1", confidence=0.4), similarity=0.8, keyword_score=0.8, hybrid_score=0.8),
        HybridSearchResult(memory=make_memory("m2", confidence=0.7), similarity=0.8, keyword_score=0.8, hybrid_score=0.8),
        HybridSearchResult(memory=make_memory("m3", confidence=0.95), similarity=0.8, keyword_score=0.8, hybrid_score=0.8),
    ]

    results = policy.apply(candidates, now=now)
    ids = [r.memory.id for r in results]
    assert "m1" not in ids
    assert "m2" in ids
    assert "m3" in ids


# ────────────────────── 4: Filter memory_types ──────────────────────

def test_filter_memory_types():
    """When memory_types is specified, only matching types survive."""
    now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
    policy = MemoryRetrievalPolicy(RetrievalPolicyConfig(memory_types=["preference", "task"]))

    candidates = [
        HybridSearchResult(memory=make_memory("m1", memory_type="preference"), similarity=0.8, keyword_score=0.8, hybrid_score=0.8),
        HybridSearchResult(memory=make_memory("m2", memory_type="identity"), similarity=0.8, keyword_score=0.8, hybrid_score=0.8),
        HybridSearchResult(memory=make_memory("m3", memory_type="task"), similarity=0.8, keyword_score=0.8, hybrid_score=0.8),
        HybridSearchResult(memory=make_memory("m4", memory_type="context"), similarity=0.8, keyword_score=0.8, hybrid_score=0.8),
    ]

    results = policy.apply(candidates, now=now)
    ids = [r.memory.id for r in results]
    assert ids == ["m1", "m3"]


# ────────────────────── 5: Recency Exponential Decay ──────────────────────

def test_recency_exponential_decay():
    """Recency score = 0.5 ** (age_days / half_life), supporting injected now."""
    ref_now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
    policy = MemoryRetrievalPolicy(RetrievalPolicyConfig(recency_half_life_days=30.0))

    # Age 0 days -> 0.5 ** 0 = 1.0
    rec_0 = policy.calculate_recency(ref_now, ref_now, 30.0)
    assert rec_0 == 1.0

    # Age 30 days -> 0.5 ** 1 = 0.5
    dt_30 = ref_now - timedelta(days=30)
    rec_30 = policy.calculate_recency(dt_30, ref_now, 30.0)
    assert rec_30 == 0.5

    # Age 60 days -> 0.5 ** 2 = 0.25
    dt_60 = ref_now - timedelta(days=60)
    rec_60 = policy.calculate_recency(dt_60, ref_now, 30.0)
    assert rec_60 == 0.25

    # Future date (clock skew) -> age clamped to 0 -> 1.0
    dt_future = ref_now + timedelta(days=5)
    rec_future = policy.calculate_recency(dt_future, ref_now, 30.0)
    assert rec_future == 1.0

    # None datetime -> 0.0
    assert policy.calculate_recency(None, ref_now, 30.0) == 0.0


# ────────────────────── 6: Retrieval Score Formula ──────────────────────

def test_retrieval_score_formula_and_preservation():
    """Formula: 0.70*hybrid + 0.15*importance + 0.10*confidence + 0.05*recency."""
    ref_now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
    # Memory updated 30 days ago (recency = 0.5)
    dt = ref_now - timedelta(days=30)
    mem = make_memory("m1", importance=0.60, confidence=0.90, updated_at=dt)

    candidate = HybridSearchResult(
        memory=mem,
        similarity=0.85,
        keyword_score=0.70,
        hybrid_score=0.80,
    )

    policy = MemoryRetrievalPolicy(RetrievalPolicyConfig(recency_half_life_days=30.0))
    results = policy.apply([candidate], now=ref_now)
    assert len(results) == 1
    res = results[0]

    # Verify original scores are unchanged
    assert res.similarity == 0.85
    assert res.keyword_score == 0.70
    assert res.hybrid_score == 0.80
    assert res.recency_score == 0.50

    # Expected retrieval score:
    # 0.70 * 0.80 + 0.15 * 0.60 + 0.10 * 0.90 + 0.05 * 0.50
    # = 0.56 + 0.09 + 0.09 + 0.025 = 0.765
    assert res.retrieval_score == 0.765


# ────────────────────── 7: Top-K Truncation ──────────────────────

def test_top_k_truncation():
    """Only top_k items are returned."""
    now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
    policy = MemoryRetrievalPolicy(RetrievalPolicyConfig(top_k=3, min_relevance=0.0))

    candidates = [
        HybridSearchResult(memory=make_memory(f"m{i}"), similarity=0.5, keyword_score=0.5, hybrid_score=float(i) / 10.0)
        for i in range(1, 8)
    ]

    results = policy.apply(candidates, now=now)
    assert len(results) == 3
    # Highest hybrid scores are m7 (0.7), m6 (0.6), m5 (0.5)
    assert [r.memory.id for r in results] == ["m7", "m6", "m5"]


# ────────────────────── 8: Deterministic Tie-Breaking ──────────────────────

def test_tie_breaking_order():
    """Tie-breaking sequence:
    retrieval_score DESC -> hybrid_score DESC -> importance DESC -> updated_at DESC -> id ASC
    """
    ref_now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
    t_new = ref_now
    t_old = ref_now - timedelta(days=10)

    # Case A: Same retrieval_score, different hybrid_score
    # Let candidate 1 have hybrid=0.8, imp=0.2; candidate 2 have hybrid=0.7, imp=0.6666...
    # Case B: Same retrieval_score and hybrid_score, different importance
    # Case C: Same retrieval_score, hybrid_score, importance, different updated_at
    # Case D: Identical on all 4 dimensions -> id ASC

    mem_c1 = make_memory("m_new", updated_at=t_new, importance=0.5, confidence=1.0)
    mem_c2 = make_memory("m_old", updated_at=t_old, importance=0.5, confidence=1.0)

    cand_c1 = HybridSearchResult(memory=mem_c1, similarity=0.8, keyword_score=0.8, hybrid_score=0.8)
    cand_c2 = HybridSearchResult(memory=mem_c2, similarity=0.8, keyword_score=0.8, hybrid_score=0.8)

    # t_new has higher recency -> higher retrieval_score
    policy = MemoryRetrievalPolicy(RetrievalPolicyConfig())
    res_c = policy.apply([cand_c2, cand_c1], now=ref_now)
    assert res_c[0].memory.id == "m_new"

    # Perfect tie on retrieval_score, hybrid_score, importance, updated_at -> id ASC
    mem_alpha = make_memory("id_alpha", updated_at=t_new, importance=0.5, confidence=1.0)
    mem_beta = make_memory("id_beta", updated_at=t_new, importance=0.5, confidence=1.0)
    cand_beta = HybridSearchResult(memory=mem_beta, similarity=0.8, keyword_score=0.8, hybrid_score=0.8)
    cand_alpha = HybridSearchResult(memory=mem_alpha, similarity=0.8, keyword_score=0.8, hybrid_score=0.8)

    res_id = policy.apply([cand_beta, cand_alpha], now=ref_now)
    assert res_id[0].memory.id == "id_alpha"
    assert res_id[1].memory.id == "id_beta"


# ────────────────────── 9: Empty Candidates ──────────────────────

def test_empty_candidates_and_zero_matches():
    """Empty list input returns [], and all-filtered candidates return []."""
    policy = MemoryRetrievalPolicy(RetrievalPolicyConfig(min_relevance=0.80))
    now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Empty input
    assert policy.apply([], now=now) == []

    # 2. All filtered out
    cand = [HybridSearchResult(memory=make_memory("m1"), similarity=0.4, keyword_score=0.4, hybrid_score=0.4)]
    assert policy.apply(cand, now=now) == []


# ────────────────────── 10: Invalid Config Parameters ──────────────────────

def test_invalid_config_parameters():
    """Invalid parameter values must raise ValidationError."""
    # top_k < 1
    with pytest.raises(ValidationError):
        RetrievalPolicyConfig(top_k=0)

    # top_k > 50
    with pytest.raises(ValidationError):
        RetrievalPolicyConfig(top_k=51)

    # min_relevance < 0
    with pytest.raises(ValidationError):
        RetrievalPolicyConfig(min_relevance=-0.01)

    # min_relevance > 1
    with pytest.raises(ValidationError):
        RetrievalPolicyConfig(min_relevance=1.01)

    # min_importance < 0
    with pytest.raises(ValidationError):
        RetrievalPolicyConfig(min_importance=-0.1)

    # min_confidence > 1
    with pytest.raises(ValidationError):
        RetrievalPolicyConfig(min_confidence=1.1)

    # recency_half_life_days <= 0
    with pytest.raises(ValidationError):
        RetrievalPolicyConfig(recency_half_life_days=0.0)
    with pytest.raises(ValidationError):
        RetrievalPolicyConfig(recency_half_life_days=-10.0)

    # Extra forbidden parameter
    with pytest.raises(ValidationError):
        RetrievalPolicyConfig(extra_param=123)  # type: ignore[call-arg]


# ────────────────────── 11: Score Bounds [0.0, 1.0] ──────────────────────

def test_scores_strictly_bounded():
    """All output scores must fall strictly within [0.0, 1.0]."""
    now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
    policy = MemoryRetrievalPolicy(RetrievalPolicyConfig(min_relevance=0.0))

    candidates = [
        HybridSearchResult(memory=make_memory("m1", importance=0.0, confidence=0.0), similarity=-0.5, keyword_score=0.0, hybrid_score=0.0),
        HybridSearchResult(memory=make_memory("m2", importance=1.0, confidence=1.0), similarity=1.0, keyword_score=1.0, hybrid_score=1.0),
        HybridSearchResult(memory=make_memory("m3", importance=0.7, confidence=0.8), similarity=0.6, keyword_score=0.5, hybrid_score=0.55),
    ]

    results = policy.apply(candidates, now=now)
    assert len(results) == 3
    for r in results:
        assert isinstance(r, ScoredMemory)
        assert 0.0 <= r.recency_score <= 1.0
        assert 0.0 <= r.retrieval_score <= 1.0
        assert 0.0 <= r.hybrid_score <= 1.0

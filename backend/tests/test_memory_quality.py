"""Tests for Phase 5.6C: Memory Quality Engine.

Covers all 7 Quality Dimensions + Engine integration:
1. Confidence scoring (high, moderate, low, edge 0.0 & 1.0)
2. Importance scoring (high, moderate, low, edge 0.0 & 1.0)
3. Freshness (recently created, stale > 1yr, expired expires_at/valid_until, future-valid, superseded, archived)
4. Consistency (conflicted status, contradiction relationship, clean)
5. Provenance (full dialogue anchor, conversation only, manual, imported, ai_extracted without anchor, missing)
6. Duplication (exact duplicate, near duplicate, unique)
7. Conflict risk (high contradiction, opposite polarity singular key, zero risk)
8. Overall score bounds [0.0, 1.0] and weights sum = 1.0
9. Determinism (repeatable scoring)
10. Explainability (reasons & warnings)
11. Tenant isolation (cross-user access returns None without leak)
12. Read-only safety (guaranteed zero mutations)
13. Bounded batch evaluation
"""

import uuid
from datetime import datetime, timedelta, timezone
import pytest

from app.models.memory import Memory
from app.models.memory_relationship import MemoryRelationship
from app.models.user import User
from app.schemas.memory import MemoryCreate
from app.schemas.memory_relationship import RelationshipType
from app.services import memory_service
from app.services.memory_quality_service import (
    DEFAULT_QUALITY_WEIGHTS,
    MemoryQualityService,
)
from tests.conftest import TestSession


def _make_dummy_memory(**kwargs) -> Memory:
    """Helper to create an in-memory Memory instance without DB persistence."""
    defaults = {
        "id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "memory_type": "preference",
        "key": "test_key",
        "content": "User prefers writing in Python",
        "confidence": 1.0,
        "importance": 0.5,
        "status": "active",
        "source": "manual",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    mem = Memory()
    for k, v in defaults.items():
        setattr(mem, k, v)
    return mem


# ============================================================
# 1. CONFIDENCE SCORING TESTS
# ============================================================

def test_confidence_scoring_high_mid_low():
    # High confidence (>= 0.85)
    mem_high = _make_dummy_memory(confidence=0.95)
    score, reason, warnings = MemoryQualityService.evaluate_confidence(mem_high)
    assert score == 0.95
    assert "High confidence" in reason
    assert len(warnings) == 0

    # Moderate confidence (0.50 - 0.84)
    mem_mid = _make_dummy_memory(confidence=0.60)
    score, reason, warnings = MemoryQualityService.evaluate_confidence(mem_mid)
    assert score == 0.60
    assert "Moderate confidence" in reason
    assert len(warnings) == 0

    # Low confidence (< 0.50)
    mem_low = _make_dummy_memory(confidence=0.30)
    score, reason, warnings = MemoryQualityService.evaluate_confidence(mem_low)
    assert score == 0.30
    assert "Low confidence" in reason
    assert len(warnings) == 1


def test_confidence_edge_values_0_and_1():
    mem_zero = _make_dummy_memory(confidence=0.0)
    score, _, warnings = MemoryQualityService.evaluate_confidence(mem_zero)
    assert score == 0.0
    assert len(warnings) == 1

    mem_one = _make_dummy_memory(confidence=1.0)
    score, _, warnings = MemoryQualityService.evaluate_confidence(mem_one)
    assert score == 1.0
    assert len(warnings) == 0


# ============================================================
# 2. IMPORTANCE SCORING TESTS
# ============================================================

def test_importance_scoring_high_mid_low():
    mem_high = _make_dummy_memory(importance=0.9)
    score, reason, _ = MemoryQualityService.evaluate_importance(mem_high)
    assert score == 0.9
    assert "Core identity" in reason

    mem_mid = _make_dummy_memory(importance=0.5)
    score, reason, _ = MemoryQualityService.evaluate_importance(mem_mid)
    assert score == 0.5
    assert "Standard priority" in reason

    mem_low = _make_dummy_memory(importance=0.2)
    score, reason, _ = MemoryQualityService.evaluate_importance(mem_low)
    assert score == 0.2
    assert "Low priority" in reason


def test_importance_edge_values_0_and_1():
    mem_0 = _make_dummy_memory(importance=0.0)
    score, _, _ = MemoryQualityService.evaluate_importance(mem_0)
    assert score == 0.0

    mem_1 = _make_dummy_memory(importance=1.0)
    score, _, _ = MemoryQualityService.evaluate_importance(mem_1)
    assert score == 1.0


# ============================================================
# 3. FRESHNESS SCORING TESTS
# ============================================================

def test_freshness_recently_created_active():
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    mem = _make_dummy_memory(
        created_at=now - timedelta(days=5),
        updated_at=now - timedelta(days=5),
        status="active",
    )
    score, reason, warnings = MemoryQualityService.evaluate_freshness(mem, now)
    assert score == 1.00
    assert "recently created or updated" in reason
    assert len(warnings) == 0


def test_freshness_stale_memory_over_1_year():
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    mem = _make_dummy_memory(
        created_at=now - timedelta(days=400),
        updated_at=now - timedelta(days=400),
        status="active",
    )
    score, reason, warnings = MemoryQualityService.evaluate_freshness(mem, now)
    assert score == 0.40
    assert "stale" in reason
    assert len(warnings) >= 1


def test_freshness_expired_explicit_expires_at():
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    mem = _make_dummy_memory(
        expires_at=now - timedelta(days=1),
        status="active",
    )
    score, reason, warnings = MemoryQualityService.evaluate_freshness(mem, now)
    assert score == 0.05
    assert "explicit expiration date" in reason
    assert len(warnings) >= 1


def test_freshness_expired_temporal_valid_until():
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    mem = _make_dummy_memory(
        valid_until=now - timedelta(days=2),
        status="active",
    )
    score, reason, warnings = MemoryQualityService.evaluate_freshness(mem, now)
    assert score == 0.10
    assert "validity window has expired" in reason
    assert len(warnings) >= 1


def test_freshness_future_valid_memory():
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    mem = _make_dummy_memory(
        valid_from=now + timedelta(days=10),
        status="active",
    )
    score, reason, warnings = MemoryQualityService.evaluate_freshness(mem, now)
    assert score == 0.40
    assert "future validity" in reason
    assert len(warnings) >= 1


def test_freshness_superseded_memory():
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    mem = _make_dummy_memory(
        status="superseded",
        superseded_by_memory_id="new-mem-id",
    )
    score, reason, warnings = MemoryQualityService.evaluate_freshness(mem, now)
    assert score == 0.10
    assert "superseded" in reason
    assert len(warnings) >= 1


def test_freshness_archived_memory():
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    mem = _make_dummy_memory(status="archived")
    score, reason, warnings = MemoryQualityService.evaluate_freshness(mem, now)
    assert score == 0.30
    assert "archived" in reason
    assert len(warnings) >= 1


# ============================================================
# 4. CONSISTENCY SCORING TESTS
# ============================================================

def test_consistency_conflicted_status():
    mem = _make_dummy_memory(status="conflicted")
    score, reason, warnings = MemoryQualityService.evaluate_consistency(mem, [], [])
    assert score == 0.10
    assert "conflicted status" in reason
    assert len(warnings) >= 1


def test_consistency_contradiction_relationship():
    mem = _make_dummy_memory(status="active")
    rel = MemoryRelationship(
        id="rel-1",
        user_id=mem.user_id,
        source_memory_id=mem.id,
        target_memory_id="other-mem",
        relationship_type=RelationshipType.CONTRADICTS.value,
    )
    score, reason, warnings = MemoryQualityService.evaluate_consistency(mem, [rel], [])
    assert score == 0.20
    assert "contradiction relationship" in reason
    assert len(warnings) >= 1


def test_consistency_clean_active_memory():
    mem = _make_dummy_memory(status="active")
    score, reason, warnings = MemoryQualityService.evaluate_consistency(mem, [], [])
    assert score == 1.00
    assert "No contradictions" in reason
    assert len(warnings) == 0


# ============================================================
# 5. PROVENANCE SCORING TESTS
# ============================================================

def test_provenance_full_dialogue_anchor():
    mem = _make_dummy_memory(
        source="conversation",
        source_conversation_id="conv-1",
        source_message_id="msg-1",
    )
    score, reason, warnings = MemoryQualityService.evaluate_provenance(mem)
    assert score == 1.00
    assert "exact conversation and message anchor" in reason
    assert len(warnings) == 0


def test_provenance_conversation_only():
    mem = _make_dummy_memory(
        source="conversation",
        source_conversation_id="conv-1",
        source_message_id=None,
    )
    score, reason, warnings = MemoryQualityService.evaluate_provenance(mem)
    assert score == 0.85
    assert "Conversation provenance is recorded" in reason
    assert len(warnings) == 0


def test_provenance_manual_source():
    mem = _make_dummy_memory(source="manual")
    score, reason, warnings = MemoryQualityService.evaluate_provenance(mem)
    assert score == 0.90
    assert "authored and confirmed by user" in reason
    assert len(warnings) == 0


def test_provenance_imported_source():
    mem = _make_dummy_memory(source="imported")
    score, reason, warnings = MemoryQualityService.evaluate_provenance(mem)
    assert score == 0.75
    assert "Imported from external source" in reason


def test_provenance_ai_extracted_without_anchor():
    mem = _make_dummy_memory(source="ai_extracted")
    score, reason, warnings = MemoryQualityService.evaluate_provenance(mem)
    assert score == 0.60
    assert len(warnings) >= 1


def test_provenance_missing_or_empty():
    mem = _make_dummy_memory(source="")
    score, reason, warnings = MemoryQualityService.evaluate_provenance(mem)
    assert score == 0.40
    assert len(warnings) >= 1


# ============================================================
# 6. DUPLICATION SCORING TESTS
# ============================================================

def test_duplication_exact_duplicate():
    mem = _make_dummy_memory(content="User prefers Vim")
    sib = _make_dummy_memory(content="user prefers vim")  # identical normalized
    score, raw_risk, reason, warnings = MemoryQualityService.evaluate_duplication(mem, [sib])
    assert score == 0.00
    assert raw_risk == 1.00
    assert "Exact duplicate" in reason
    assert len(warnings) >= 1


def test_duplication_near_duplicate_same_key():
    mem = _make_dummy_memory(key="editor", content="User prefers Neovim code editor")
    sib = _make_dummy_memory(key="editor", content="User prefers Neovim code editor always")
    score, raw_risk, reason, warnings = MemoryQualityService.evaluate_duplication(mem, [sib])
    assert score == 0.30
    assert raw_risk == 0.70
    assert "Near-duplicate" in reason
    assert len(warnings) >= 1


def test_duplication_no_duplicate_unique():
    mem = _make_dummy_memory(content="User prefers PostgreSQL")
    sib = _make_dummy_memory(content="User enjoys playing badminton on weekends")
    score, raw_risk, reason, warnings = MemoryQualityService.evaluate_duplication(mem, [sib])
    assert score == 1.00
    assert raw_risk == 0.00
    assert "No duplicate" in reason
    assert len(warnings) == 0


# ============================================================
# 7. CONFLICT RISK TESTS
# ============================================================

def test_conflict_risk_high_contradiction():
    mem = _make_dummy_memory(status="conflicted")
    score, raw_risk, reason, warnings = MemoryQualityService.evaluate_conflict_risk(mem, [], [])
    assert score == 0.10
    assert raw_risk == 0.90
    assert "High conflict risk" in reason
    assert len(warnings) >= 1


def test_conflict_risk_zero_signal():
    mem = _make_dummy_memory(status="active")
    score, raw_risk, reason, warnings = MemoryQualityService.evaluate_conflict_risk(mem, [], [])
    assert score == 1.00
    assert raw_risk == 0.00
    assert "Zero conflict signals" in reason
    assert len(warnings) == 0


# ============================================================
# 8. OVERALL SCORE BOUNDS, WEIGHTS, AND DETERMINISM
# ============================================================

def test_weights_sum_to_one():
    total_w = sum(DEFAULT_QUALITY_WEIGHTS.values())
    assert abs(total_w - 1.0) < 1e-6
    assert len(DEFAULT_QUALITY_WEIGHTS) == 7


def test_deterministic_scoring_repeatability():
    mem = _make_dummy_memory(
        confidence=0.85,
        importance=0.7,
        content="Deterministic test content",
    )
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)

    # Evaluate multiple times
    res1 = MemoryQualityService.evaluate_confidence(mem)
    res2 = MemoryQualityService.evaluate_confidence(mem)
    assert res1 == res2

    f1 = MemoryQualityService.evaluate_freshness(mem, now)
    f2 = MemoryQualityService.evaluate_freshness(mem, now)
    assert f1 == f2


# ============================================================
# 9. INTEGRATION TESTS (DB, TENANT ISOLATION, NO MUTATION, BATCH)
# ============================================================

async def _create_user_and_memory(session) -> tuple[str, str]:
    user = User(
        id=str(uuid.uuid4()),
        email=f"qual_user_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="hash",
        display_name="Quality User",
    )
    session.add(user)
    await session.commit()

    mem = await memory_service.create_memory(
        session,
        user.id,
        MemoryCreate(
            key="primary_lang",
            content="User writes exclusively in Rust",
            category="preference",
            confidence=0.95,
            importance=0.9,
            source="manual",
        ),
        auto_embed=False,
    )
    await session.commit()
    return user.id, mem.id


@pytest.mark.asyncio
async def test_evaluate_memory_end_to_end():
    async with TestSession() as session:
        user_id, mem_id = await _create_user_and_memory(session)

        res = await MemoryQualityService.evaluate_memory(session, user_id, mem_id)
        assert res is not None
        assert res.memory_id == mem_id
        assert res.user_id == user_id
        assert 0.0 <= res.overall_score <= 1.0
        assert len(res.dimensions) == 7
        assert "confidence" in res.dimensions
        assert "importance" in res.dimensions
        assert "freshness" in res.dimensions
        assert "consistency" in res.dimensions
        assert "provenance" in res.dimensions
        assert "duplication" in res.dimensions
        assert "conflict_risk" in res.dimensions
        assert res.summary_reason is not None


@pytest.mark.asyncio
async def test_tenant_isolation_cross_user_denied():
    async with TestSession() as session:
        user1_id, mem1_id = await _create_user_and_memory(session)
        user2_id, _ = await _create_user_and_memory(session)

        # User 2 attempting to evaluate User 1's memory must return None
        res = await MemoryQualityService.evaluate_memory(session, user2_id, mem1_id)
        assert res is None


@pytest.mark.asyncio
async def test_read_only_safety_no_mutation():
    async with TestSession() as session:
        user_id, mem_id = await _create_user_and_memory(session)

        # Read state before evaluation
        mem_before = await session.get(Memory, mem_id)
        assert mem_before is not None
        updated_at_before = mem_before.updated_at
        version_before = mem_before.version
        status_before = mem_before.status

        # Evaluate quality
        await MemoryQualityService.evaluate_memory(session, user_id, mem_id)

        # Re-fetch state and confirm absolute zero mutations
        mem_after = await session.get(Memory, mem_id)
        assert mem_after is not None
        assert mem_after.updated_at == updated_at_before
        assert mem_after.version == version_before
        assert mem_after.status == status_before


@pytest.mark.asyncio
async def test_batch_memory_quality_bounded_limit():
    async with TestSession() as session:
        user_id, _ = await _create_user_and_memory(session)

        # Add 2 more memories
        for i in range(2):
            await memory_service.create_memory(
                session,
                user_id,
                MemoryCreate(
                    key=f"item_{i}",
                    content=f"Content for item {i}",
                    category="preference",
                ),
                auto_embed=False,
            )
        await session.commit()

        batch_res = await MemoryQualityService.evaluate_memories_batch(
            session, user_id, limit=2
        )
        assert batch_res.total_evaluated == 2
        assert 0.0 <= batch_res.mean_quality_score <= 1.0
        assert len(batch_res.results) == 2

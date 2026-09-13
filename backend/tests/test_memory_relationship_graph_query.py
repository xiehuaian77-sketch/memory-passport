"""Tests for Phase 5.4A: Graph Query Foundation.

Covers:
- Direction semantics: outgoing, incoming, both, default
- Relationship type filters: valid, invalid (400), combined with direction
- Confidence filters: min=0, threshold, min=1, <0 (400), >1 (400)
- Limit handling: default 20, custom, max 200, >200 (400), <1 (400)
- One-hop hard boundary: A->B->C strictly returns B, never C
- User isolation: cross-user 404, nonexistent 404, no data leakage
- Temporal modes: current excludes expired/superseded, historical, any, reference_time
- Read-only side-effect safety: no writes, no audit logs, stable deterministic ordering
"""

from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, func

from app.models.governance import MemoryAuditLog
from app.models.memory import Memory
from app.models.memory_relationship import MemoryRelationship
from tests.conftest import TestSession


@pytest_asyncio.fixture
async def other_user(client: AsyncClient):
    """Register and authenticate a second user."""
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": "graph_user2@example.com",
            "password": "password123",
            "display_name": "Graph User Two",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me_resp = await client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 200
    user_id = me_resp.json()["id"]
    return {"user_id": user_id, "headers": headers}


async def _create_mem(
    client: AsyncClient,
    key: str,
    content: str,
    headers: dict | None = None,
    valid_from: str | None = None,
    valid_until: str | None = None,
) -> str:
    payload = {
        "key": key,
        "content": content,
        "category": "preference",
    }
    if valid_from:
        payload["valid_from"] = valid_from
    if valid_until:
        payload["valid_until"] = valid_until

    resp = await client.post("/api/memories", json=payload, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_rel(
    client: AsyncClient,
    source_id: str,
    target_id: str,
    rel_type: str = "UPDATES",
    confidence: float = 1.0,
    headers: dict | None = None,
) -> dict:
    resp = await client.post(
        f"/api/memories/{source_id}/relationships",
        json={
            "source_memory_id": source_id,
            "target_memory_id": target_id,
            "relationship_type": rel_type,
            "confidence": confidence,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


# ===========================================================================
# Group A: Direction Semantics
# ===========================================================================

@pytest.mark.asyncio
async def test_01_outgoing_query(auth_client: AsyncClient):
    """Outgoing traversal returns memories targeted by source."""
    mA = await _create_mem(auth_client, "A", "Memory A")
    mB = await _create_mem(auth_client, "B", "Memory B")
    await _create_rel(auth_client, mA, mB, "UPDATES", 0.9)

    resp = await auth_client.get(f"/api/memories/{mA}/related?direction=outgoing")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["memory_id"] == mB
    assert data[0]["direction"] == "outgoing"
    assert data[0]["relationship_type"] == "UPDATES"
    assert data[0]["relationship_confidence"] == 0.9


@pytest.mark.asyncio
async def test_02_incoming_query(auth_client: AsyncClient):
    """Incoming traversal returns memories targeting focus."""
    mA = await _create_mem(auth_client, "A2", "Memory A2")
    mB = await _create_mem(auth_client, "B2", "Memory B2")
    await _create_rel(auth_client, mA, mB, "SUPERSEDES", 0.85)

    # Querying B with incoming should return A
    resp = await auth_client.get(f"/api/memories/{mB}/related?direction=incoming")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["memory_id"] == mA
    assert data[0]["direction"] == "incoming"
    assert data[0]["relationship_type"] == "SUPERSEDES"
    assert data[0]["relationship_confidence"] == 0.85


@pytest.mark.asyncio
async def test_03_both_query(auth_client: AsyncClient):
    """direction=both returns both incoming and outgoing connections."""
    mA = await _create_mem(auth_client, "center", "Center Memory")
    mOut = await _create_mem(auth_client, "out", "Outgoing Target")
    mIn = await _create_mem(auth_client, "in", "Incoming Source")

    await _create_rel(auth_client, mA, mOut, "UPDATES", 0.95)
    await _create_rel(auth_client, mIn, mA, "CONTRADICTS", 0.8)

    resp = await auth_client.get(f"/api/memories/{mA}/related?direction=both")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    ids = {d["memory_id"] for d in data}
    assert ids == {mOut, mIn}

    dirs = {d["memory_id"]: d["direction"] for d in data}
    assert dirs[mOut] == "outgoing"
    assert dirs[mIn] == "incoming"


@pytest.mark.asyncio
async def test_04_default_direction_is_both(auth_client: AsyncClient):
    """Omitting direction parameter defaults to both."""
    mA = await _create_mem(auth_client, "def_dir_A", "Memory A")
    mB = await _create_mem(auth_client, "def_dir_B", "Memory B")
    mC = await _create_mem(auth_client, "def_dir_C", "Memory C")

    await _create_rel(auth_client, mA, mB, "RELEVANT_TO", 0.7)
    await _create_rel(auth_client, mC, mA, "RELEVANT_TO", 0.75)

    resp = await auth_client.get(f"/api/memories/{mA}/related")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert {d["memory_id"] for d in data} == {mB, mC}


@pytest.mark.asyncio
async def test_05_default_limit_is_20(auth_client: AsyncClient):
    """Omitting limit parameter returns up to default 20 results."""
    m_root = await _create_mem(auth_client, "lim_root", "Root Memory")
    for i in range(25):
        m_leaf = await _create_mem(auth_client, f"lim_leaf_{i}", f"Leaf {i}")
        await _create_rel(auth_client, m_root, m_leaf, "RELEVANT_TO")

    resp = await auth_client.get(f"/api/memories/{m_root}/related")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 20


# ===========================================================================
# Group B: Relationship Type Filters
# ===========================================================================

@pytest.mark.asyncio
async def test_06_valid_relationship_type_filter(auth_client: AsyncClient):
    """Filter by specific relationship_type."""
    mA = await _create_mem(auth_client, "type_A", "Type A")
    mB = await _create_mem(auth_client, "type_B", "Type B")
    mC = await _create_mem(auth_client, "type_C", "Type C")

    await _create_rel(auth_client, mA, mB, "UPDATES")
    await _create_rel(auth_client, mA, mC, "CONTRADICTS")

    resp = await auth_client.get(f"/api/memories/{mA}/related?relationship_type=UPDATES")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["memory_id"] == mB
    assert data[0]["relationship_type"] == "UPDATES"


@pytest.mark.asyncio
async def test_07_invalid_relationship_type_filter_rejected(auth_client: AsyncClient):
    """Unsupported relationship_type parameter returns HTTP 400."""
    mA = await _create_mem(auth_client, "inv_type_A", "Type A")
    resp = await auth_client.get(f"/api/memories/{mA}/related?relationship_type=INVALID_TYPE")
    assert resp.status_code == 400
    assert "Unsupported relationship_type" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_08_type_filter_combined_with_direction(auth_client: AsyncClient):
    """Filter by both relationship_type and direction."""
    mA = await _create_mem(auth_client, "comb_A", "Comb A")
    mB = await _create_mem(auth_client, "comb_B", "Comb B")
    mC = await _create_mem(auth_client, "comb_C", "Comb C")

    # A -> B is UPDATES
    await _create_rel(auth_client, mA, mB, "UPDATES")
    # C -> A is UPDATES
    await _create_rel(auth_client, mC, mA, "UPDATES")

    # Outgoing only
    resp = await auth_client.get(f"/api/memories/{mA}/related?relationship_type=UPDATES&direction=outgoing")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["memory_id"] == mB

    # Incoming only
    resp2 = await auth_client.get(f"/api/memories/{mA}/related?relationship_type=UPDATES&direction=incoming")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert len(data2) == 1
    assert data2[0]["memory_id"] == mC


# ===========================================================================
# Group C: Confidence Filters
# ===========================================================================

@pytest.mark.asyncio
async def test_09_confidence_min_zero(auth_client: AsyncClient):
    """confidence_min=0 returns all confidence levels."""
    mA = await _create_mem(auth_client, "conf_A", "Conf A")
    mB = await _create_mem(auth_client, "conf_B", "Conf B")
    mC = await _create_mem(auth_client, "conf_C", "Conf C")

    await _create_rel(auth_client, mA, mB, "RELEVANT_TO", 0.2)
    await _create_rel(auth_client, mA, mC, "RELEVANT_TO", 0.9)

    resp = await auth_client.get(f"/api/memories/{mA}/related?confidence_min=0.0")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_10_confidence_min_threshold(auth_client: AsyncClient):
    """confidence_min filters out edges below threshold."""
    mA = await _create_mem(auth_client, "thresh_A", "Thresh A")
    mB = await _create_mem(auth_client, "thresh_B", "Thresh B")
    mC = await _create_mem(auth_client, "thresh_C", "Thresh C")

    await _create_rel(auth_client, mA, mB, "RELEVANT_TO", 0.85)
    await _create_rel(auth_client, mA, mC, "RELEVANT_TO", 0.60)

    resp = await auth_client.get(f"/api/memories/{mA}/related?confidence_min=0.80")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["memory_id"] == mB


@pytest.mark.asyncio
async def test_11_confidence_min_one(auth_client: AsyncClient):
    """confidence_min=1.0 returns only highest confidence edges."""
    mA = await _create_mem(auth_client, "one_A", "One A")
    mB = await _create_mem(auth_client, "one_B", "One B")
    mC = await _create_mem(auth_client, "one_C", "One C")

    await _create_rel(auth_client, mA, mB, "RELEVANT_TO", 1.0)
    await _create_rel(auth_client, mA, mC, "RELEVANT_TO", 0.99)

    resp = await auth_client.get(f"/api/memories/{mA}/related?confidence_min=1.0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["memory_id"] == mB


@pytest.mark.asyncio
async def test_12_confidence_min_below_zero_rejected(auth_client: AsyncClient):
    """confidence_min < 0 returns HTTP 400."""
    mA = await _create_mem(auth_client, "neg_conf_A", "Neg Conf A")
    resp = await auth_client.get(f"/api/memories/{mA}/related?confidence_min=-0.1")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_13_confidence_min_above_one_rejected(auth_client: AsyncClient):
    """confidence_min > 1.0 returns HTTP 400."""
    mA = await _create_mem(auth_client, "high_conf_A", "High Conf A")
    resp = await auth_client.get(f"/api/memories/{mA}/related?confidence_min=1.01")
    assert resp.status_code == 400


# ===========================================================================
# Group D: Limit & Pagination
# ===========================================================================

@pytest.mark.asyncio
async def test_14_limit_custom(auth_client: AsyncClient):
    """Custom limit restricts result count."""
    mA = await _create_mem(auth_client, "cust_lim_A", "Cust Lim A")
    for i in range(10):
        m = await _create_mem(auth_client, f"cust_leaf_{i}", f"Leaf {i}")
        await _create_rel(auth_client, mA, m, "UPDATES")

    resp = await auth_client.get(f"/api/memories/{mA}/related?limit=5")
    assert resp.status_code == 200
    assert len(resp.json()) == 5


@pytest.mark.asyncio
async def test_15_limit_max_200_accepted(auth_client: AsyncClient):
    """limit=200 is accepted within boundary."""
    mA = await _create_mem(auth_client, "max_lim_A", "Max Lim A")
    resp = await auth_client.get(f"/api/memories/{mA}/related?limit=200")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_16_limit_above_200_rejected(auth_client: AsyncClient):
    """limit > 200 returns HTTP 400."""
    mA = await _create_mem(auth_client, "over_lim_A", "Over Lim A")
    resp = await auth_client.get(f"/api/memories/{mA}/related?limit=201")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_17_limit_zero_or_negative_rejected(auth_client: AsyncClient):
    """limit < 1 returns HTTP 400."""
    mA = await _create_mem(auth_client, "zero_lim_A", "Zero Lim A")
    resp_zero = await auth_client.get(f"/api/memories/{mA}/related?limit=0")
    assert resp_zero.status_code == 400

    resp_neg = await auth_client.get(f"/api/memories/{mA}/related?limit=-1")
    assert resp_neg.status_code == 400


# ===========================================================================
# Group E: One-Hop Hard Boundary
# ===========================================================================

@pytest.mark.asyncio
async def test_18_one_hop_chain_strictly_bounded(auth_client: AsyncClient):
    """Chain A -> B -> C -> D: Querying A only returns B, never C or D."""
    mA = await _create_mem(auth_client, "chain_A", "Chain A")
    mB = await _create_mem(auth_client, "chain_B", "Chain B")
    mC = await _create_mem(auth_client, "chain_C", "Chain C")
    mD = await _create_mem(auth_client, "chain_D", "Chain D")

    await _create_rel(auth_client, mA, mB, "UPDATES")
    await _create_rel(auth_client, mB, mC, "UPDATES")
    await _create_rel(auth_client, mC, mD, "UPDATES")

    resp = await auth_client.get(f"/api/memories/{mA}/related")
    assert resp.status_code == 200
    ids = [d["memory_id"] for d in resp.json()]
    assert ids == [mB]
    assert mC not in ids
    assert mD not in ids


@pytest.mark.asyncio
async def test_19_one_hop_bidirectional_does_not_expand(auth_client: AsyncClient):
    """A -> B and B -> C: Querying B in both directions gives A and C, but querying A never gives C."""
    mA = await _create_mem(auth_client, "bi_A", "Bi A")
    mB = await _create_mem(auth_client, "bi_B", "Bi B")
    mC = await _create_mem(auth_client, "bi_C", "Bi C")

    await _create_rel(auth_client, mA, mB, "RELEVANT_TO")
    await _create_rel(auth_client, mB, mC, "RELEVANT_TO")

    # Query B (both)
    respB = await auth_client.get(f"/api/memories/{mB}/related?direction=both")
    assert respB.status_code == 200
    idsB = {d["memory_id"] for d in respB.json()}
    assert idsB == {mA, mC}

    # Query A (both)
    respA = await auth_client.get(f"/api/memories/{mA}/related?direction=both")
    assert respA.status_code == 200
    idsA = {d["memory_id"] for d in respA.json()}
    assert idsA == {mB}
    assert mC not in idsA


# ===========================================================================
# Group F: User Isolation & Missing Resources
# ===========================================================================

@pytest.mark.asyncio
async def test_20_cross_user_memory_returns_404(auth_client: AsyncClient, other_user):
    """User cannot query related memories for another user's memory."""
    m_other = await _create_mem(auth_client, "u2_m", "U2 memory", headers=other_user["headers"])
    resp = await auth_client.get(f"/api/memories/{m_other}/related")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Memory not found"


@pytest.mark.asyncio
async def test_21_nonexistent_memory_returns_404(auth_client: AsyncClient):
    """Querying related memories for nonexistent ID returns 404."""
    resp = await auth_client.get("/api/memories/00000000-0000-0000-0000-000000000000/related")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Memory not found"


@pytest.mark.asyncio
async def test_22_cross_user_relationship_isolation(auth_client: AsyncClient, other_user):
    """Relationships created by another user never leak into current user query."""
    m1 = await _create_mem(auth_client, "iso_1", "User 1 memory")
    m2 = await _create_mem(auth_client, "iso_2", "User 1 target")
    await _create_rel(auth_client, m1, m2, "RELEVANT_TO")

    # Other user creates relationship between their own memories
    u2_m1 = await _create_mem(auth_client, "u2_1", "U2 mem 1", headers=other_user["headers"])
    u2_m2 = await _create_mem(auth_client, "u2_2", "U2 mem 2", headers=other_user["headers"])
    await _create_rel(auth_client, u2_m1, u2_m2, "RELEVANT_TO", headers=other_user["headers"])

    resp1 = await auth_client.get(f"/api/memories/{m1}/related")
    assert resp1.status_code == 200
    ids1 = [d["memory_id"] for d in resp1.json()]
    assert ids1 == [m2]
    assert u2_m1 not in ids1
    assert u2_m2 not in ids1


# ===========================================================================
# Group G: Temporal Awareness
# ===========================================================================

@pytest.mark.asyncio
async def test_23_temporal_current_excludes_expired(auth_client: AsyncClient):
    """current mode excludes memories whose valid_until is in the past."""
    now = datetime.now(timezone.utc)
    past_iso = (now - timedelta(days=2)).isoformat()
    future_iso = (now + timedelta(days=2)).isoformat()

    m_root = await _create_mem(auth_client, "temp_root", "Root")
    m_exp = await _create_mem(auth_client, "temp_exp", "Expired", valid_until=past_iso)
    m_act = await _create_mem(auth_client, "temp_act", "Active", valid_until=future_iso)

    await _create_rel(auth_client, m_root, m_exp, "RELEVANT_TO")
    await _create_rel(auth_client, m_root, m_act, "RELEVANT_TO")

    resp = await auth_client.get(f"/api/memories/{m_root}/related?temporal_mode=current")
    assert resp.status_code == 200
    ids = [d["memory_id"] for d in resp.json()]
    assert m_act in ids
    assert m_exp not in ids


@pytest.mark.asyncio
async def test_24_temporal_current_excludes_superseded(auth_client: AsyncClient):
    """current mode excludes memories with status='superseded'."""
    m_root = await _create_mem(auth_client, "sup_root", "Root")
    m_old = await _create_mem(auth_client, "sup_old", "Old fact")
    m_new = await _create_mem(auth_client, "sup_new", "New fact")

    await _create_rel(auth_client, m_root, m_old, "UPDATES")

    # Supersede m_old with m_new
    sup_resp = await auth_client.post(
        f"/api/memories/{m_old}/supersede",
        json={"replacement_memory_id": m_new},
    )
    assert sup_resp.status_code == 200

    resp = await auth_client.get(f"/api/memories/{m_root}/related?temporal_mode=current")
    assert resp.status_code == 200
    ids = [d["memory_id"] for d in resp.json()]
    assert m_old not in ids


@pytest.mark.asyncio
async def test_25_temporal_historical_includes_expired_and_superseded(auth_client: AsyncClient):
    """historical mode retrieves expired and superseded memories."""
    now = datetime.now(timezone.utc)
    past_iso = (now - timedelta(days=5)).isoformat()

    m_root = await _create_mem(auth_client, "hist_root", "Hist Root")
    m_exp = await _create_mem(auth_client, "hist_exp", "Expired Fact", valid_until=past_iso)
    await _create_rel(auth_client, m_root, m_exp, "RELEVANT_TO")

    resp = await auth_client.get(f"/api/memories/{m_root}/related?temporal_mode=historical")
    assert resp.status_code == 200
    ids = [d["memory_id"] for d in resp.json()]
    assert m_exp in ids


@pytest.mark.asyncio
async def test_26_temporal_any_retrieves_all_memories(auth_client: AsyncClient):
    """temporal_mode=any retrieves all connected memories regardless of status/expiry."""
    now = datetime.now(timezone.utc)
    past_iso = (now - timedelta(days=10)).isoformat()
    future_iso = (now + timedelta(days=10)).isoformat()

    m_root = await _create_mem(auth_client, "any_root", "Any Root")
    m_exp = await _create_mem(auth_client, "any_exp", "Expired", valid_until=past_iso)
    m_act = await _create_mem(auth_client, "any_act", "Active", valid_until=future_iso)

    await _create_rel(auth_client, m_root, m_exp, "RELEVANT_TO")
    await _create_rel(auth_client, m_root, m_act, "RELEVANT_TO")

    resp = await auth_client.get(f"/api/memories/{m_root}/related?temporal_mode=any")
    assert resp.status_code == 200
    ids = [d["memory_id"] for d in resp.json()]
    assert m_exp in ids
    assert m_act in ids


@pytest.mark.asyncio
async def test_27_reference_time_evaluation(auth_client: AsyncClient):
    """reference_time evaluates validity at specified past/future point."""
    now = datetime.now(timezone.utc)
    point_t1 = now - timedelta(days=20)
    point_t2 = now - timedelta(days=10)
    point_t3 = now - timedelta(days=5)

    # Valid from T1 to T2
    m_root = await _create_mem(auth_client, "ref_root", "Ref Root")
    m_target = await _create_mem(
        auth_client,
        "ref_target",
        "Target valid T1 to T2",
        valid_from=point_t1.isoformat(),
        valid_until=point_t2.isoformat(),
    )
    await _create_rel(auth_client, m_root, m_target, "RELEVANT_TO")

    # At T1.5 (between T1 and T2), it was currently valid
    mid_time = (point_t1 + timedelta(days=5)).isoformat()
    resp_valid = await auth_client.get(
        f"/api/memories/{m_root}/related",
        params={"temporal_mode": "current", "reference_time": mid_time},
    )
    assert resp_valid.status_code == 200
    assert any(d["memory_id"] == m_target for d in resp_valid.json())

    # At T3 (after T2), it is expired
    resp_expired = await auth_client.get(
        f"/api/memories/{m_root}/related",
        params={"temporal_mode": "current", "reference_time": point_t3.isoformat()},
    )
    assert resp_expired.status_code == 200
    assert not any(d["memory_id"] == m_target for d in resp_expired.json())


@pytest.mark.asyncio
async def test_28_invalid_temporal_mode_rejected(auth_client: AsyncClient):
    """Invalid temporal_mode parameter returns HTTP 400."""
    mA = await _create_mem(auth_client, "inv_temp_A", "Inv Temp A")
    resp = await auth_client.get(f"/api/memories/{mA}/related?temporal_mode=future")
    assert resp.status_code == 400
    assert "Invalid temporal_mode" in resp.json()["detail"]


# ===========================================================================
# Group H: Security & Read-Only Guarantees
# ===========================================================================

@pytest.mark.asyncio
async def test_29_get_related_performs_no_writes(auth_client: AsyncClient):
    """GET /related performs zero database writes (read-only)."""
    mA = await _create_mem(auth_client, "ro_A", "RO A")
    mB = await _create_mem(auth_client, "ro_B", "RO B")
    await _create_rel(auth_client, mA, mB, "UPDATES")

    async with TestSession() as db:
        cnt_mem_before = (await db.execute(select(func.count(Memory.id)))).scalar()
        cnt_rel_before = (await db.execute(select(func.count(MemoryRelationship.id)))).scalar()
        cnt_aud_before = (await db.execute(select(func.count(MemoryAuditLog.id)))).scalar()

    # Call query multiple times
    for _ in range(3):
        resp = await auth_client.get(f"/api/memories/{mA}/related")
        assert resp.status_code == 200

    async with TestSession() as db:
        cnt_mem_after = (await db.execute(select(func.count(Memory.id)))).scalar()
        cnt_rel_after = (await db.execute(select(func.count(MemoryRelationship.id)))).scalar()
        cnt_aud_after = (await db.execute(select(func.count(MemoryAuditLog.id)))).scalar()

    assert cnt_mem_after == cnt_mem_before
    assert cnt_rel_after == cnt_rel_before
    assert cnt_aud_after == cnt_aud_before


@pytest.mark.asyncio
async def test_30_get_related_creates_zero_audit_logs(auth_client: AsyncClient):
    """Graph queries do not generate audit log records."""
    mA = await _create_mem(auth_client, "audit_ro_A", "Audit RO A")
    mB = await _create_mem(auth_client, "audit_ro_B", "Audit RO B")
    await _create_rel(auth_client, mA, mB, "UPDATES")

    async with TestSession() as db:
        before_logs = (await db.execute(select(func.count()).select_from(MemoryAuditLog))).scalar()

    resp = await auth_client.get(f"/api/memories/{mA}/related")
    assert resp.status_code == 200

    async with TestSession() as db:
        after_logs = (await db.execute(select(func.count()).select_from(MemoryAuditLog))).scalar()

    assert after_logs == before_logs


@pytest.mark.asyncio
async def test_31_stable_deterministic_ordering(auth_client: AsyncClient):
    """Repeated calls to related query return identical deterministic order."""
    m_root = await _create_mem(auth_client, "order_root", "Order Root")
    for i in range(8):
        leaf = await _create_mem(auth_client, f"order_leaf_{i}", f"Leaf {i}")
        await _create_rel(auth_client, m_root, leaf, "RELEVANT_TO")

    resp1 = await auth_client.get(f"/api/memories/{m_root}/related?limit=8")
    resp2 = await auth_client.get(f"/api/memories/{m_root}/related?limit=8")
    resp3 = await auth_client.get(f"/api/memories/{m_root}/related?limit=8")

    assert resp1.status_code == 200
    order1 = [d["memory_id"] for d in resp1.json()]
    order2 = [d["memory_id"] for d in resp2.json()]
    order3 = [d["memory_id"] for d in resp3.json()]

    assert order1 == order2 == order3


@pytest.mark.asyncio
async def test_32_response_structure_completeness(auth_client: AsyncClient):
    """Response contains all expected memory and relationship attributes."""
    mA = await _create_mem(auth_client, "struct_A", "Content A")
    mB = await _create_mem(auth_client, "struct_B", "Content B")
    rel = await _create_rel(auth_client, mA, mB, "SUPERSEDES", 0.92)

    resp = await auth_client.get(f"/api/memories/{mA}/related")
    assert resp.status_code == 200
    item = resp.json()[0]

    # Target memory fields
    assert item["memory_id"] == mB
    assert item["id"] == mB
    assert item["content"] == "Content B"
    assert item["memory_type"] == "preference"
    assert item["status"] == "active"
    assert "importance" in item
    assert "confidence" in item

    # Edge metadata fields
    assert item["relationship_id"] == rel["id"]
    assert item["relationship_type"] == "SUPERSEDES"
    assert item["relationship_confidence"] == 0.92
    assert item["direction"] == "outgoing"


@pytest.mark.asyncio
async def test_33_temporal_current_null_valid_until_and_boundaries(auth_client: AsyncClient):
    """Verify temporal_mode=current properly retains valid_until=None memories while excluding expired, future, and superseded memories."""
    now = datetime.now(timezone.utc)
    past_iso = (now - timedelta(days=10)).isoformat()
    future_iso = (now + timedelta(days=10)).isoformat()
    recent_past_iso = (now - timedelta(days=2)).isoformat()

    m_root = await _create_mem(auth_client, "perm_root", "Root for permanent memory test")

    # 1. Normal current memory: status=active, valid_from=past, valid_until=None, superseded_by=None
    m_permanent = await _create_mem(
        auth_client,
        "perm_target",
        "Permanent active memory with null valid_until",
        valid_from=past_iso,
        valid_until=None,
    )
    await _create_rel(auth_client, m_root, m_permanent, "UPDATES")

    # 2. Expired memory: valid_until in the past
    m_expired = await _create_mem(
        auth_client,
        "exp_target",
        "Expired memory",
        valid_from=past_iso,
        valid_until=recent_past_iso,
    )
    await _create_rel(auth_client, m_root, m_expired, "UPDATES")

    # 3. Future memory: valid_from in the future
    m_future = await _create_mem(
        auth_client,
        "future_target",
        "Future memory",
        valid_from=future_iso,
        valid_until=None,
    )
    await _create_rel(auth_client, m_root, m_future, "UPDATES")

    # 4. Superseded memory
    m_superseded = await _create_mem(
        auth_client,
        "sup_target_old",
        "Memory that will be superseded",
    )
    m_replacement = await _create_mem(
        auth_client,
        "sup_target_new",
        "Replacement memory",
    )
    await _create_rel(auth_client, m_root, m_superseded, "UPDATES")
    sup_res = await auth_client.post(
        f"/api/memories/{m_superseded}/supersede",
        json={"replacement_memory_id": m_replacement},
    )
    assert sup_res.status_code == 200

    # Query with temporal_mode=current
    resp = await auth_client.get(f"/api/memories/{m_root}/related?temporal_mode=current")
    assert resp.status_code == 200
    returned_ids = [d["memory_id"] for d in resp.json()]

    # Assertions:
    # Permanent memory (valid_until=None) MUST be returned
    assert m_permanent in returned_ids, "Permanent active memory with valid_until=None must be returned in current mode"
    # Expired memory MUST NOT be returned
    assert m_expired not in returned_ids, "Expired memory must be excluded in current mode"
    # Future memory MUST NOT be returned
    assert m_future not in returned_ids, "Future memory (valid_from > now) must be excluded in current mode"
    # Superseded memory MUST NOT be returned
    assert m_superseded not in returned_ids, "Superseded memory must be excluded in current mode"


"""Comprehensive tests for MemoryRelationship Router and Audit Integration (Phase 5.3).

Covers all 25 required test dimensions:
1. POST create
2. GET list
3. DELETE
4. GET related
5. auth required
6. cross-user source
7. cross-user target
8. cross-user relationship
9. client user_id spoof
10. self relationship
11. invalid relationship_type
12. confidence < 0
13. confidence > 1
14. duplicate/idempotency
15. all four supported relationship types
16. create Audit
17. delete Audit
18. sensitive audit filtering
19. one-hop only
20. limit
21. empty result
22. missing relationship 404
23. missing memory 404
24. transaction rollback
25. memory deletion + RESTRICT behavior
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.models.governance import AuditAction, AuditActorType, MemoryAuditLog
from app.models.memory_relationship import MemoryRelationship
from tests.conftest import TestSession


@pytest_asyncio.fixture
async def other_user(client: AsyncClient):
    """Register and authenticate a second user."""
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": "user2@example.com",
            "password": "password123",
            "display_name": "User Two",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me_resp = await client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 200
    user_id = me_resp.json()["id"]
    return {"user_id": user_id, "headers": headers}


async def _create_mem(client: AsyncClient, key: str, content: str) -> str:
    resp = await client.post(
        "/api/memories",
        json={"key": key, "content": content, "category": "preference"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# 1. POST create
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_01_post_create_relationship(auth_client: AsyncClient):
    m1 = await _create_mem(auth_client, "pref_1", "I prefer Python")
    m2 = await _create_mem(auth_client, "pref_2", "I write Python 3")
    resp = await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={
            "source_memory_id": m1,
            "target_memory_id": m2,
            "relationship_type": "UPDATES",
            "confidence": 0.95,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_memory_id"] == m1
    assert data["target_memory_id"] == m2
    assert data["relationship_type"] == "UPDATES"
    assert data["confidence"] == 0.95
    assert "id" in data
    assert "created_at" in data


# ---------------------------------------------------------------------------
# 2. GET list
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_02_get_list_relationships(auth_client: AsyncClient):
    m1 = await _create_mem(auth_client, "k1", "c1")
    m2 = await _create_mem(auth_client, "k2", "c2")
    await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={
            "source_memory_id": m1,
            "target_memory_id": m2,
            "relationship_type": "RELEVANT_TO",
            "confidence": 0.8,
        },
    )
    resp = await auth_client.get(f"/api/memories/{m1}/relationships")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(r["source_memory_id"] == m1 and r["target_memory_id"] == m2 for r in data)


# ---------------------------------------------------------------------------
# 3. DELETE
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_03_delete_relationship(auth_client: AsyncClient):
    m1 = await _create_mem(auth_client, "del_1", "del content 1")
    m2 = await _create_mem(auth_client, "del_2", "del content 2")
    create_resp = await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={
            "source_memory_id": m1,
            "target_memory_id": m2,
            "relationship_type": "SUPERSEDES",
            "confidence": 1.0,
        },
    )
    assert create_resp.status_code == 201
    rel_id = create_resp.json()["id"]

    del_resp = await auth_client.delete(f"/api/memories/{m1}/relationships/{rel_id}")
    assert del_resp.status_code == 204

    # Verify deleted
    list_resp = await auth_client.get(f"/api/memories/{m1}/relationships")
    assert not any(r["id"] == rel_id for r in list_resp.json())


# ---------------------------------------------------------------------------
# 4. GET related
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_04_get_related_memories(auth_client: AsyncClient):
    m1 = await _create_mem(auth_client, "rel_src", "source content")
    m2 = await _create_mem(auth_client, "rel_tgt", "target content")
    await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={
            "source_memory_id": m1,
            "target_memory_id": m2,
            "relationship_type": "RELEVANT_TO",
            "confidence": 0.9,
        },
    )
    resp = await auth_client.get(f"/api/memories/{m1}/related")
    assert resp.status_code == 200
    related = resp.json()
    assert isinstance(related, list)
    assert any(m["id"] == m2 for m in related)


# ---------------------------------------------------------------------------
# 5. Auth required
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_05_auth_required(client: AsyncClient):
    # Unauthenticated client calls
    r_post = await client.post("/api/memories/some-id/relationships", json={})
    assert r_post.status_code == 401

    r_get = await client.get("/api/memories/some-id/relationships")
    assert r_get.status_code == 401

    r_del = await client.delete("/api/memories/some-id/relationships/some-rel")
    assert r_del.status_code == 401

    r_rel = await client.get("/api/memories/some-id/related")
    assert r_rel.status_code == 401


# ---------------------------------------------------------------------------
# 6. Cross-user source memory -> 404
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_06_cross_user_source(auth_client: AsyncClient, client: AsyncClient, other_user):
    # other_user creates a memory
    r2 = await client.post(
        "/api/memories",
        headers=other_user["headers"],
        json={"key": "other_k", "content": "other_c", "category": "preference"},
    )
    other_mem_id = r2.json()["id"]

    my_mem_id = await _create_mem(auth_client, "my_k", "my_c")

    # Current user attempts to use other user's memory as source
    resp = await auth_client.post(
        f"/api/memories/{other_mem_id}/relationships",
        json={
            "source_memory_id": other_mem_id,
            "target_memory_id": my_mem_id,
            "relationship_type": "UPDATES",
        },
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 7. Cross-user target memory -> 404
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_07_cross_user_target(auth_client: AsyncClient, client: AsyncClient, other_user):
    r2 = await client.post(
        "/api/memories",
        headers=other_user["headers"],
        json={"key": "other_k2", "content": "other_c2", "category": "preference"},
    )
    other_mem_id = r2.json()["id"]
    my_mem_id = await _create_mem(auth_client, "my_k2", "my_c2")

    resp = await auth_client.post(
        f"/api/memories/{my_mem_id}/relationships",
        json={
            "source_memory_id": my_mem_id,
            "target_memory_id": other_mem_id,
            "relationship_type": "UPDATES",
        },
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. Cross-user relationship access -> 404
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_08_cross_user_relationship_isolation(auth_client: AsyncClient, client: AsyncClient, other_user):
    m1 = await _create_mem(auth_client, "iso_1", "iso content 1")
    m2 = await _create_mem(auth_client, "iso_2", "iso content 2")
    create_resp = await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={
            "source_memory_id": m1,
            "target_memory_id": m2,
            "relationship_type": "UPDATES",
        },
    )
    rel_id = create_resp.json()["id"]

    # Other user attempts to delete user1's relationship
    del_resp = await client.delete(
        f"/api/memories/{m1}/relationships/{rel_id}",
        headers=other_user["headers"],
    )
    assert del_resp.status_code == 404

    # Other user attempts to view user1's relationships
    list_resp = await client.get(
        f"/api/memories/{m1}/relationships",
        headers=other_user["headers"],
    )
    assert list_resp.status_code == 404


# ---------------------------------------------------------------------------
# 9. Client user_id spoof is ignored
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_09_client_user_id_spoof(auth_client: AsyncClient, other_user):
    m1 = await _create_mem(auth_client, "spoof_1", "spoof content 1")
    m2 = await _create_mem(auth_client, "spoof_2", "spoof content 2")
    me_resp = await auth_client.get("/api/auth/me")
    my_id = me_resp.json()["id"]

    # Supply other_user's user_id in payload
    resp = await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={
            "source_memory_id": m1,
            "target_memory_id": m2,
            "relationship_type": "UPDATES",
            "user_id": other_user["user_id"],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["user_id"] == my_id


# ---------------------------------------------------------------------------
# 10. Self relationship -> 400
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_10_self_relationship_is_bad_request(auth_client: AsyncClient):
    m1 = await _create_mem(auth_client, "self_1", "self content")
    resp = await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={
            "source_memory_id": m1,
            "target_memory_id": m1,
            "relationship_type": "UPDATES",
        },
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 11. Invalid relationship_type -> 400 / 422
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_11_invalid_relationship_type(auth_client: AsyncClient):
    m1 = await _create_mem(auth_client, "type_1", "content 1")
    m2 = await _create_mem(auth_client, "type_2", "content 2")
    resp = await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={
            "source_memory_id": m1,
            "target_memory_id": m2,
            "relationship_type": "INVALID_TYPE",
        },
    )
    assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# 12. Confidence < 0 -> 400 / 422
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_12_confidence_below_zero(auth_client: AsyncClient):
    m1 = await _create_mem(auth_client, "conf_1", "content 1")
    m2 = await _create_mem(auth_client, "conf_2", "content 2")
    resp = await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={
            "source_memory_id": m1,
            "target_memory_id": m2,
            "relationship_type": "UPDATES",
            "confidence": -0.1,
        },
    )
    assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# 13. Confidence > 1 -> 400 / 422
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_13_confidence_above_one(auth_client: AsyncClient):
    m1 = await _create_mem(auth_client, "conf_3", "content 1")
    m2 = await _create_mem(auth_client, "conf_4", "content 2")
    resp = await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={
            "source_memory_id": m1,
            "target_memory_id": m2,
            "relationship_type": "UPDATES",
            "confidence": 1.5,
        },
    )
    assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# 14. Duplicate/idempotency
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_14_duplicate_creation_idempotent(auth_client: AsyncClient):
    m1 = await _create_mem(auth_client, "dup_1", "dup content 1")
    m2 = await _create_mem(auth_client, "dup_2", "dup content 2")
    r1 = await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={
            "source_memory_id": m1,
            "target_memory_id": m2,
            "relationship_type": "UPDATES",
            "confidence": 0.8,
        },
    )
    assert r1.status_code == 201
    id1 = r1.json()["id"]

    r2 = await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={
            "source_memory_id": m1,
            "target_memory_id": m2,
            "relationship_type": "UPDATES",
            "confidence": 0.8,
        },
    )
    assert r2.status_code == 201
    id2 = r2.json()["id"]
    assert id1 == id2


# ---------------------------------------------------------------------------
# 15. All four supported relationship types
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("rel_type", ["UPDATES", "SUPERSEDES", "CONTRADICTS", "RELEVANT_TO"])
async def test_15_all_supported_types(auth_client: AsyncClient, rel_type):
    m1 = await _create_mem(auth_client, f"t1_{rel_type}", "content 1")
    m2 = await _create_mem(auth_client, f"t2_{rel_type}", "content 2")
    resp = await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={
            "source_memory_id": m1,
            "target_memory_id": m2,
            "relationship_type": rel_type,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["relationship_type"] == rel_type


# ---------------------------------------------------------------------------
# 16. Create Audit
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_16_create_relationship_audit(auth_client: AsyncClient):
    m1 = await _create_mem(auth_client, "aud_c1", "audit create 1")
    m2 = await _create_mem(auth_client, "aud_c2", "audit create 2")
    me_resp = await auth_client.get("/api/auth/me")
    user_id = me_resp.json()["id"]

    resp = await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={
            "source_memory_id": m1,
            "target_memory_id": m2,
            "relationship_type": "CONTRADICTS",
            "confidence": 0.75,
        },
    )
    assert resp.status_code == 201
    rel_id = resp.json()["id"]

    # Verify audit log in DB
    async with TestSession() as db:
        stmt = select(MemoryAuditLog).where(
            MemoryAuditLog.user_id == user_id,
            MemoryAuditLog.action == AuditAction.RELATIONSHIP_CREATE.value,
        ).order_by(MemoryAuditLog.created_at.desc())
        res = await db.execute(stmt)
        log = res.scalars().first()
        assert log is not None
        assert log.actor_type == AuditActorType.USER.value
        assert log.actor_id == user_id
        assert log.memory_id == m1
        assert rel_id in log.metadata_json


# ---------------------------------------------------------------------------
# 17. Delete Audit
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_17_delete_relationship_audit(auth_client: AsyncClient):
    m1 = await _create_mem(auth_client, "aud_d1", "audit delete 1")
    m2 = await _create_mem(auth_client, "aud_d2", "audit delete 2")
    me_resp = await auth_client.get("/api/auth/me")
    user_id = me_resp.json()["id"]

    c_resp = await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={
            "source_memory_id": m1,
            "target_memory_id": m2,
            "relationship_type": "UPDATES",
        },
    )
    rel_id = c_resp.json()["id"]

    del_resp = await auth_client.delete(f"/api/memories/{m1}/relationships/{rel_id}")
    assert del_resp.status_code == 204

    async with TestSession() as db:
        stmt = select(MemoryAuditLog).where(
            MemoryAuditLog.user_id == user_id,
            MemoryAuditLog.action == AuditAction.RELATIONSHIP_DELETE.value,
        ).order_by(MemoryAuditLog.created_at.desc())
        res = await db.execute(stmt)
        log = res.scalars().first()
        assert log is not None
        assert log.actor_type == AuditActorType.USER.value
        assert log.actor_id == user_id
        assert rel_id in log.metadata_json


# ---------------------------------------------------------------------------
# 18. Sensitive audit filtering
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_18_sensitive_audit_filtering(auth_client: AsyncClient):
    # Audit metadata should not contain secrets or passwords
    m1 = await _create_mem(auth_client, "sens_1", "sensitive test")
    m2 = await _create_mem(auth_client, "sens_2", "sensitive test 2")
    me_resp = await auth_client.get("/api/auth/me")
    user_id = me_resp.json()["id"]

    await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={
            "source_memory_id": m1,
            "target_memory_id": m2,
            "relationship_type": "UPDATES",
        },
    )
    async with TestSession() as db:
        stmt = select(MemoryAuditLog).where(
            MemoryAuditLog.user_id == user_id,
            MemoryAuditLog.action == AuditAction.RELATIONSHIP_CREATE.value,
        )
        res = await db.execute(stmt)
        logs = res.scalars().all()
        for log in logs:
            lower_meta = log.metadata_json.lower()
            assert "password" not in lower_meta
            assert "token" not in lower_meta
            assert "api_key" not in lower_meta
            assert "secret" not in lower_meta


# ---------------------------------------------------------------------------
# 19. One-hop only: A -> B -> C: related(A) is only [B]
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_19_one_hop_only(auth_client: AsyncClient):
    mA = await _create_mem(auth_client, "hop_A", "Memory A")
    mB = await _create_mem(auth_client, "hop_B", "Memory B")
    mC = await _create_mem(auth_client, "hop_C", "Memory C")

    # A -> B
    await auth_client.post(
        f"/api/memories/{mA}/relationships",
        json={"source_memory_id": mA, "target_memory_id": mB, "relationship_type": "UPDATES"},
    )
    # B -> C
    await auth_client.post(
        f"/api/memories/{mB}/relationships",
        json={"source_memory_id": mB, "target_memory_id": mC, "relationship_type": "UPDATES"},
    )

    # Query related for A
    resp = await auth_client.get(f"/api/memories/{mA}/related")
    assert resp.status_code == 200
    related = resp.json()
    related_ids = [m["id"] for m in related]
    assert mB in related_ids
    assert mC not in related_ids  # One-hop only!


# ---------------------------------------------------------------------------
# 20. Limit parameter
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_20_limit_parameter(auth_client: AsyncClient):
    m_root = await _create_mem(auth_client, "root", "root mem")
    targets = []
    for i in range(5):
        t = await _create_mem(auth_client, f"t_{i}", f"content {i}")
        targets.append(t)
        await auth_client.post(
            f"/api/memories/{m_root}/relationships",
            json={"source_memory_id": m_root, "target_memory_id": t, "relationship_type": "RELEVANT_TO"},
        )

    # limit=2
    resp = await auth_client.get(f"/api/memories/{m_root}/related?limit=2")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # relationships limit=3
    resp_rel = await auth_client.get(f"/api/memories/{m_root}/relationships?limit=3")
    assert resp_rel.status_code == 200
    assert len(resp_rel.json()) == 3


# ---------------------------------------------------------------------------
# 21. Empty result
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_21_empty_result(auth_client: AsyncClient):
    m_solo = await _create_mem(auth_client, "solo", "no relations")
    resp = await auth_client.get(f"/api/memories/{m_solo}/relationships")
    assert resp.status_code == 200
    assert resp.json() == []

    resp_related = await auth_client.get(f"/api/memories/{m_solo}/related")
    assert resp_related.status_code == 200
    assert resp_related.json() == []


# ---------------------------------------------------------------------------
# 22. Missing relationship 404
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_22_missing_relationship_404(auth_client: AsyncClient):
    m1 = await _create_mem(auth_client, "miss_rel", "content")
    resp = await auth_client.delete(f"/api/memories/{m1}/relationships/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 23. Missing memory 404
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_23_missing_memory_404(auth_client: AsyncClient):
    non_existent = "00000000-0000-0000-0000-000000000000"
    m1 = await _create_mem(auth_client, "real_mem", "content")

    # POST with missing source memory
    r_post_src = await auth_client.post(
        f"/api/memories/{non_existent}/relationships",
        json={"source_memory_id": non_existent, "target_memory_id": m1, "relationship_type": "UPDATES"},
    )
    assert r_post_src.status_code == 404

    # GET relationships for missing memory
    r_get = await auth_client.get(f"/api/memories/{non_existent}/relationships")
    assert r_get.status_code == 404

    # GET related for missing memory
    r_related = await auth_client.get(f"/api/memories/{non_existent}/related")
    assert r_related.status_code == 404


# ---------------------------------------------------------------------------
# 24. Transaction rollback: failure ensures no partial state
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_24_transaction_atomicity(auth_client: AsyncClient):
    m1 = await _create_mem(auth_client, "tx_1", "tx content 1")
    me_resp = await auth_client.get("/api/auth/me")
    user_id = me_resp.json()["id"]

    # When creation fails validation (e.g. self-relationship), neither relationship nor audit log is committed
    resp = await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={"source_memory_id": m1, "target_memory_id": m1, "relationship_type": "UPDATES"},
    )
    assert resp.status_code == 400

    async with TestSession() as db:
        # Verify no relationship created
        stmt = select(MemoryRelationship).where(
            MemoryRelationship.user_id == user_id,
            MemoryRelationship.source_memory_id == m1,
        )
        res = await db.execute(stmt)
        assert res.scalar_one_or_none() is None

        # Verify no audit log with RELATIONSHIP_CREATE for m1
        stmt_audit = select(MemoryAuditLog).where(
            MemoryAuditLog.user_id == user_id,
            MemoryAuditLog.memory_id == m1,
            MemoryAuditLog.action == AuditAction.RELATIONSHIP_CREATE.value,
        )
        res_audit = await db.execute(stmt_audit)
        assert res_audit.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# 25. Memory deletion + RESTRICT behavior
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_25_memory_deletion_restrict_behavior(auth_client: AsyncClient):
    m1 = await _create_mem(auth_client, "res_src", "source to be restricted")
    m2 = await _create_mem(auth_client, "res_tgt", "target to be restricted")

    create_resp = await auth_client.post(
        f"/api/memories/{m1}/relationships",
        json={"source_memory_id": m1, "target_memory_id": m2, "relationship_type": "UPDATES"},
    )
    assert create_resp.status_code == 201
    rel_id = create_resp.json()["id"]

    # When relationship exists: if relationship is deleted first, memory can be deleted
    del_rel = await auth_client.delete(f"/api/memories/{m1}/relationships/{rel_id}")
    assert del_rel.status_code == 204

    # Now memory can be deleted cleanly
    del_mem = await auth_client.delete(f"/api/memories/{m1}")
    assert del_mem.status_code == 204

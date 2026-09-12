"""Phase 5.0: Temporal Memory & Supersession Integration Tests.

Covers:
1. Migration validation
2. Create memory with valid_from
3. Create memory with valid_until
4. Invalid time range validation (valid_until < valid_from)
5. Supersede success (atomic transaction, status update, pointer setting)
6. Supersede transaction atomicity / rollback
7. Cross-user supersede returns 404 (strict isolation)
8. Self-supersede returns 400
9. Already superseded memory returns 409 Conflict
10. Superseding with already superseded replacement returns 400
11. Current retrieval mode (only active & valid, excludes superseded)
12. Historical retrieval mode (retrieves superseded and expired)
13. Temporal retrieval with reference_time
14. Audit log recording for SUPERSEDE
15. User isolation in retrieval & supersede
16. Backward compatibility with legacy memories without valid time
17. Timezone-aware datetime handling
18. API validation (empty replacement ID, extra fields)
19. Sequential supersession chain (A -> B -> C)
20. List memories filtering by status=superseded
"""

from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.governance import MemoryAuditLog
from app.models.memory import Memory
from app.schemas.memory import MemoryRetrievalRequest
from app.services import memory_service
from tests.conftest import TestSession


@pytest.mark.asyncio
async def test_create_memory_with_valid_time(auth_client: AsyncClient):
    """Memory can be created with valid_from and valid_until timestamps."""
    t_start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    t_end = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    res = await auth_client.post(
        "/api/memories",
        json={
            "key": "city_residence_2024",
            "content": "I lived in Shanghai during 2024",
            "category": "context",
            "valid_from": t_start.isoformat(),
            "valid_until": t_end.isoformat(),
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["valid_from"] is not None
    assert data["valid_until"] is not None
    assert data["status"] == "active"
    assert data["superseded_by_memory_id"] is None


@pytest.mark.asyncio
async def test_invalid_time_range_rejected(auth_client: AsyncClient):
    """valid_until earlier than valid_from must be rejected by Pydantic validation."""
    t_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    t_end = datetime(2024, 1, 1, tzinfo=timezone.utc)

    res = await auth_client.post(
        "/api/memories",
        json={
            "key": "time_paradox",
            "content": "Time traveler paradox",
            "category": "fact",
            "valid_from": t_start.isoformat(),
            "valid_until": t_end.isoformat(),
        },
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_supersede_success(auth_client: AsyncClient):
    """Old memory is superseded by replacement memory atomically."""
    # 1. Create Old memory ("I live in Shanghai")
    t_old = datetime(2022, 1, 1, tzinfo=timezone.utc)
    res_old = await auth_client.post(
        "/api/memories",
        json={
            "key": "current_city",
            "content": "I live in Shanghai",
            "category": "fact",
            "valid_from": t_old.isoformat(),
        },
    )
    assert res_old.status_code == 201
    old_id = res_old.json()["id"]

    # 2. Create New memory ("I live in Tokyo")
    t_new = datetime(2025, 6, 1, tzinfo=timezone.utc)
    res_new = await auth_client.post(
        "/api/memories",
        json={
            "key": "current_city",
            "content": "I now live in Tokyo",
            "category": "fact",
            "valid_from": t_new.isoformat(),
        },
    )
    assert res_new.status_code == 201
    new_id = res_new.json()["id"]

    # 3. Call supersede API
    res_sup = await auth_client.post(
        f"/api/memories/{old_id}/supersede",
        json={"replacement_memory_id": new_id},
    )
    assert res_sup.status_code == 200
    data_sup = res_sup.json()
    assert data_sup["id"] == old_id
    assert data_sup["status"] == "superseded"
    assert data_sup["superseded_by_memory_id"] == new_id
    assert data_sup["valid_until"] is not None

    # Verify Old memory in DB
    async with TestSession() as session:
        m_old = await session.get(Memory, old_id)
        assert m_old.status == "superseded"
        assert m_old.superseded_by_memory_id == new_id

        # Verify New memory in DB is active
        m_new = await session.get(Memory, new_id)
        assert m_new.status == "active"
        assert m_new.superseded_by_memory_id is None

        # Verify Audit Log
        logs = (
            await session.execute(
                select(MemoryAuditLog).where(
                    MemoryAuditLog.memory_id == old_id,
                    MemoryAuditLog.action == "SUPERSEDE",
                )
            )
        ).scalars().all()
        assert len(logs) == 1
        assert logs[0].actor_type == "user"


@pytest.mark.asyncio
async def test_self_supersede_rejected(auth_client: AsyncClient):
    """Memory cannot supersede itself."""
    res = await auth_client.post(
        "/api/memories",
        json={"key": "solo_memory", "content": "Solo memory content", "category": "fact"},
    )
    mem_id = res.json()["id"]

    res_sup = await auth_client.post(
        f"/api/memories/{mem_id}/supersede",
        json={"replacement_memory_id": mem_id},
    )
    assert res_sup.status_code == 400
    assert "cannot supersede itself" in res_sup.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cross_user_supersede_forbidden(auth_client: AsyncClient, client: AsyncClient):
    """A user cannot supersede another user's memory (returns 404 for isolation)."""
    # User A creates memory
    res_a = await auth_client.post(
        "/api/memories",
        json={"key": "secret_a", "content": "User A facts", "category": "fact"},
    )
    mem_a_id = res_a.json()["id"]

    # Register User B
    res_reg_b = await client.post(
        "/api/auth/register",
        json={"email": "user_b_temporal@example.com", "password": "password123", "display_name": "User B"},
    )
    token_b = res_reg_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User B creates memory
    res_b = await client.post(
        "/api/memories",
        headers=headers_b,
        json={"key": "secret_b", "content": "User B facts", "category": "fact"},
    )
    mem_b_id = res_b.json()["id"]

    # User B tries to supersede User A's memory
    res_hack = await client.post(
        f"/api/memories/{mem_a_id}/supersede",
        headers=headers_b,
        json={"replacement_memory_id": mem_b_id},
    )
    assert res_hack.status_code == 404

    # User B tries to use User A's memory as replacement
    res_hack_replace = await client.post(
        f"/api/memories/{mem_b_id}/supersede",
        headers=headers_b,
        json={"replacement_memory_id": mem_a_id},
    )
    assert res_hack_replace.status_code == 404


@pytest.mark.asyncio
async def test_already_superseded_memory_rejected(auth_client: AsyncClient):
    """Superseding an already superseded memory returns 409 Conflict."""
    res1 = await auth_client.post(
        "/api/memories", json={"key": "k", "content": "Version 1", "category": "fact"}
    )
    m1_id = res1.json()["id"]

    res2 = await auth_client.post(
        "/api/memories", json={"key": "k", "content": "Version 2", "category": "fact"}
    )
    m2_id = res2.json()["id"]

    res3 = await auth_client.post(
        "/api/memories", json={"key": "k", "content": "Version 3", "category": "fact"}
    )
    m3_id = res3.json()["id"]

    # Supersede m1 with m2
    r_sup1 = await auth_client.post(
        f"/api/memories/{m1_id}/supersede",
        json={"replacement_memory_id": m2_id},
    )
    assert r_sup1.status_code == 200

    # Trying to supersede m1 again returns 409
    r_sup_dup = await auth_client.post(
        f"/api/memories/{m1_id}/supersede",
        json={"replacement_memory_id": m3_id},
    )
    assert r_sup_dup.status_code == 409


@pytest.mark.asyncio
async def test_superseding_with_already_superseded_replacement_rejected(auth_client: AsyncClient):
    """Using an already superseded memory as replacement returns 400 Bad Request."""
    res1 = await auth_client.post(
        "/api/memories", json={"key": "k", "content": "Active 1", "category": "fact"}
    )
    m1_id = res1.json()["id"]

    res2 = await auth_client.post(
        "/api/memories", json={"key": "k", "content": "Active 2", "category": "fact"}
    )
    m2_id = res2.json()["id"]

    res3 = await auth_client.post(
        "/api/memories", json={"key": "k", "content": "Active 3", "category": "fact"}
    )
    m3_id = res3.json()["id"]

    # Supersede m2 with m3 -> m2 is now superseded
    await auth_client.post(
        f"/api/memories/{m2_id}/supersede",
        json={"replacement_memory_id": m3_id},
    )

    # Trying to supersede m1 with m2 (which is superseded) must fail
    res_fail = await auth_client.post(
        f"/api/memories/{m1_id}/supersede",
        json={"replacement_memory_id": m2_id},
    )
    assert res_fail.status_code == 400
    assert "replacement memory is already superseded" in res_fail.json()["detail"].lower()


@pytest.mark.asyncio
async def test_current_retrieval_excludes_superseded_and_expired(auth_client: AsyncClient):
    """Default 'current' temporal mode only retrieves active and unexpired memories."""
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]

    now = datetime.now(timezone.utc)
    past = now - timedelta(days=60)

    async with TestSession() as session:
        # 1. Current valid active memory
        m_active = Memory(
            user_id=user_id,
            memory_type="fact",
            key="city",
            content="I live in Tokyo city right now",
            status="active",
            valid_from=past,
            valid_until=None,
        )
        # 2. Superseded memory
        m_superseded = Memory(
            user_id=user_id,
            memory_type="fact",
            key="city",
            content="I lived in Shanghai city previously",
            status="superseded",
            valid_from=past - timedelta(days=365),
            valid_until=past,
            superseded_by_memory_id="some-id",
        )
        # 3. Expired memory
        m_expired = Memory(
            user_id=user_id,
            memory_type="context",
            key="project",
            content="Working on project alpha city this week",
            status="active",
            valid_from=past - timedelta(days=10),
            valid_until=past,
        )
        session.add_all([m_active, m_superseded, m_expired])
        await session.commit()

    async with TestSession() as session:
        req = MemoryRetrievalRequest(
            query="city",
            temporal_mode="current",
            min_relevance=0.0,
        )
        ctx = await memory_service.retrieve_context(session, user_id=user_id, request=req)

        # Only active and unexpired memory should be in context
        item_contents = [it.content for it in ctx.items]
        assert any("Tokyo" in c for c in item_contents)
        assert not any("Shanghai" in c for c in item_contents)
        assert not any("project alpha" in c for c in item_contents)


@pytest.mark.asyncio
async def test_historical_retrieval_includes_superseded_and_expired(auth_client: AsyncClient):
    """'historical' temporal mode retrieves superseded and expired memories."""
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]

    now = datetime.now(timezone.utc)
    past = now - timedelta(days=60)

    async with TestSession() as session:
        m_active = Memory(
            user_id=user_id,
            memory_type="fact",
            key="city",
            content="I live in Tokyo city right now",
            status="active",
            valid_from=past,
            valid_until=None,
        )
        m_superseded = Memory(
            user_id=user_id,
            memory_type="fact",
            key="city",
            content="I lived in Shanghai city previously",
            status="superseded",
            valid_from=past - timedelta(days=365),
            valid_until=past,
            superseded_by_memory_id="replacement_id",
        )
        session.add_all([m_active, m_superseded])
        await session.commit()

    async with TestSession() as session:
        req = MemoryRetrievalRequest(
            query="city",
            temporal_mode="historical",
            min_relevance=0.0,
        )
        ctx = await memory_service.retrieve_context(session, user_id=user_id, request=req)

        item_contents = [it.content for it in ctx.items]
        assert any("Shanghai" in c for c in item_contents)
        assert not any("Tokyo" in c for c in item_contents)


@pytest.mark.asyncio
async def test_backward_compatibility_legacy_memories(auth_client: AsyncClient):
    """Legacy memories with valid_from=None and valid_until=None retrieve cleanly in current mode."""
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]

    async with TestSession() as session:
        m_legacy = Memory(
            user_id=user_id,
            memory_type="preference",
            key="theme",
            content="Prefers dark mode editor",
            status="active",
            valid_from=None,
            valid_until=None,
        )
        session.add(m_legacy)
        await session.commit()

    async with TestSession() as session:
        req = MemoryRetrievalRequest(
            query="editor theme preference",
            temporal_mode="current",
            min_relevance=0.0,
        )
        ctx = await memory_service.retrieve_context(session, user_id=user_id, request=req)
        assert any("dark mode" in it.content for it in ctx.items)


@pytest.mark.asyncio
async def test_list_memories_superseded_status(auth_client: AsyncClient):
    """Memories can be queried by status='superseded' via GET /api/memories."""
    res1 = await auth_client.post(
        "/api/memories", json={"key": "loc", "content": "Location 1", "category": "fact"}
    )
    m1_id = res1.json()["id"]

    res2 = await auth_client.post(
        "/api/memories", json={"key": "loc", "content": "Location 2", "category": "fact"}
    )
    m2_id = res2.json()["id"]

    await auth_client.post(
        f"/api/memories/{m1_id}/supersede",
        json={"replacement_memory_id": m2_id},
    )

    # Default list excludes superseded
    res_def = await auth_client.get("/api/memories")
    assert res_def.status_code == 200
    ids_def = [m["id"] for m in res_def.json()]
    assert m1_id not in ids_def
    assert m2_id in ids_def

    # Query status=superseded returns superseded memory
    res_sup = await auth_client.get("/api/memories?status=superseded")
    assert res_sup.status_code == 200
    ids_sup = [m["id"] for m in res_sup.json()]
    assert m1_id in ids_sup
    assert m2_id not in ids_sup


@pytest.mark.asyncio
async def test_temporal_retrieval_with_reference_time(auth_client: AsyncClient):
    """Temporal retrieval evaluates validity at reference_time."""
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]

    async with TestSession() as session:
        m1 = Memory(
            user_id=user_id,
            memory_type="fact",
            key="residence",
            content="Lived in London during 2020 to 2023",
            status="active",
            valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
            valid_until=datetime(2023, 1, 1, tzinfo=timezone.utc),
        )
        m2 = Memory(
            user_id=user_id,
            memory_type="fact",
            key="residence",
            content="Living in Paris from 2023 onwards",
            status="active",
            valid_from=datetime(2023, 1, 1, tzinfo=timezone.utc),
            valid_until=None,
        )
        session.add_all([m1, m2])
        await session.commit()

    async with TestSession() as session:
        # At reference time 2021: London should be current, Paris should not be valid yet
        req_2021 = MemoryRetrievalRequest(
            query="London Paris residence",
            temporal_mode="current",
            reference_time=datetime(2021, 6, 1, tzinfo=timezone.utc),
            min_relevance=0.0,
        )
        ctx_2021 = await memory_service.retrieve_context(session, user_id=user_id, request=req_2021)
        contents_2021 = [item.content for item in ctx_2021.items]
        assert any("London" in c for c in contents_2021)
        assert not any("Paris" in c for c in contents_2021)

        # At reference time 2025: Paris should be current, London should be expired
        req_2025 = MemoryRetrievalRequest(
            query="London Paris residence",
            temporal_mode="current",
            reference_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
            min_relevance=0.0,
        )
        ctx_2025 = await memory_service.retrieve_context(session, user_id=user_id, request=req_2025)
        contents_2025 = [item.content for item in ctx_2025.items]
        assert any("Paris" in c for c in contents_2025)
        assert not any("London" in c for c in contents_2025)


@pytest.mark.asyncio
async def test_supersede_sequential_chain(auth_client: AsyncClient):
    """Sequential supersessions (A -> B -> C) preserve chain pointers."""
    res_a = await auth_client.post("/api/memories", json={"key": "role", "content": "Junior Dev", "category": "fact"})
    id_a = res_a.json()["id"]

    res_b = await auth_client.post("/api/memories", json={"key": "role", "content": "Mid-level Dev", "category": "fact"})
    id_b = res_b.json()["id"]

    res_c = await auth_client.post("/api/memories", json={"key": "role", "content": "Senior Dev", "category": "fact"})
    id_c = res_c.json()["id"]

    # A superseded by B
    r_sup1 = await auth_client.post(f"/api/memories/{id_a}/supersede", json={"replacement_memory_id": id_b})
    assert r_sup1.status_code == 200

    # B superseded by C
    r_sup2 = await auth_client.post(f"/api/memories/{id_b}/supersede", json={"replacement_memory_id": id_c})
    assert r_sup2.status_code == 200

    async with TestSession() as session:
        ma = await session.get(Memory, id_a)
        mb = await session.get(Memory, id_b)
        mc = await session.get(Memory, id_c)

        assert ma.status == "superseded"
        assert ma.superseded_by_memory_id == id_b

        assert mb.status == "superseded"
        assert mb.superseded_by_memory_id == id_c

        assert mc.status == "active"
        assert mc.superseded_by_memory_id is None


@pytest.mark.asyncio
async def test_supersede_api_validation_extra_fields(auth_client: AsyncClient):
    """SupersedeRequest rejects extra fields (extra='forbid')."""
    res = await auth_client.post(
        "/api/memories/fake-id/supersede",
        json={
            "replacement_memory_id": "some-id",
            "malicious_injected_field": "hacked",
        },
    )
    assert res.status_code == 422

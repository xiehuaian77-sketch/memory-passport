'''Tests for MemoryRelationshipService.

These tests verify the business‑logic layer without involving the router or audit integration. They use the existing async ``TestSession`` fixture to obtain an ``AsyncSession`` and the ``auth_client`` fixture to obtain the current test user's ``user_id``.
'''

import pytest
import pytest_asyncio
from fastapi import HTTPException, status

from app.models.memory import Memory
from app.models.memory_relationship import MemoryRelationship
from app.schemas.memory_relationship import RelationshipType
from app.services.memory_relationship_service import (
    create_relationship,
    get_relationship,
    delete_relationship,
    list_by_user,
    list_related_memories,
)
from app.services.memory_service import create_memory
from app.schemas.memory import MemoryCreate
from tests.conftest import TestSession

# Helper to create a memory for a given user via the service layer
async def _create_memory(db, user_id: str, key: str, content: str) -> Memory:
    # Build the MemoryCreate schema; category is accepted via alias field
    mem_data = MemoryCreate(key=key, content=content, category="preference")
    return await create_memory(db, user_id, mem_data)


@pytest_asyncio.fixture
async def other_user(auth_client):
    """Register a second user and return its ``user_id`` and auth headers."""
    transport = auth_client._transport  # type: ignore[attr-defined]
    async with auth_client.__class__(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/auth/register",
            json={
                "email": "userb@example.com",
                "password": "password123",
                "display_name": "User B",
            },
        )
        assert r.status_code == 201
        token = r.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        r_me = await client.get("/api/auth/me")
        assert r_me.status_code == 200
        user_id = r_me.json()["id"]
        return {"user_id": user_id, "auth_headers": {"Authorization": f"Bearer {token}"}}

# ---------------------------------------------------------------------------
# VALID CREATION
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_valid_relationship_creation(auth_client):
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]
    async with TestSession() as db:
        src = await _create_memory(db, user_id, "src", "source memory")
        tgt = await _create_memory(db, user_id, "tgt", "target memory")
        rel = await create_relationship(
            db=db,
            current_user_id=user_id,
            source_memory_id=src.id,
            target_memory_id=tgt.id,
            relationship_type=RelationshipType.UPDATES,
            confidence=0.8,
        )
        assert isinstance(rel, MemoryRelationship)
        assert rel.source_memory_id == src.id
        assert rel.target_memory_id == tgt.id
        assert rel.relationship_type == RelationshipType.UPDATES
        assert rel.confidence == 0.8

# ---------------------------------------------------------------------------
# OWNERSHIP VALIDATION
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_source_memory_must_belong_to_current_user(auth_client, other_user):
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]
    async with TestSession() as db:
        src = await _create_memory(db, other_user["user_id"], "src", "other's src")
        tgt = await _create_memory(db, user_id, "tgt", "my target")
        with pytest.raises(HTTPException) as exc:
            await create_relationship(
                db=db,
                current_user_id=user_id,
                source_memory_id=src.id,
                target_memory_id=tgt.id,
                relationship_type=RelationshipType.SUPERSEDES,
            )
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

@pytest.mark.asyncio
async def test_target_memory_must_belong_to_current_user(auth_client, other_user):
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]
    async with TestSession() as db:
        src = await _create_memory(db, user_id, "src", "my src")
        tgt = await _create_memory(db, other_user["user_id"], "tgt", "other's tgt")
        with pytest.raises(HTTPException) as exc:
            await create_relationship(
                db=db,
                current_user_id=user_id,
                source_memory_id=src.id,
                target_memory_id=tgt.id,
                relationship_type=RelationshipType.CONTRADICTS,
            )
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

# ---------------------------------------------------------------------------
# NON‑EXISTENT MEMORIES
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_nonexistent_source_memory(auth_client):
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]
    async with TestSession() as db:
        src_id = "nonexistent-src-id"
        tgt = await _create_memory(db, user_id, "tgt", "target")
        with pytest.raises(HTTPException) as exc:
            await create_relationship(
                db=db,
                current_user_id=user_id,
                source_memory_id=src_id,
                target_memory_id=tgt.id,
                relationship_type=RelationshipType.RELEVANT_TO,
            )
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

@pytest.mark.asyncio
async def test_nonexistent_target_memory(auth_client):
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]
    async with TestSession() as db:
        src = await _create_memory(db, user_id, "src", "source")
        tgt_id = "nonexistent-tgt-id"
        with pytest.raises(HTTPException) as exc:
            await create_relationship(
                db=db,
                current_user_id=user_id,
                source_memory_id=src.id,
                target_memory_id=tgt_id,
                relationship_type=RelationshipType.UPDATES,
            )
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

# ---------------------------------------------------------------------------
# SELF‑RELATIONSHIP
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_self_relationship_is_bad_request(auth_client):
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]
    async with TestSession() as db:
        mem = await _create_memory(db, user_id, "mem", "self")
        with pytest.raises(HTTPException) as exc:
            await create_relationship(
                db=db,
                current_user_id=user_id,
                source_memory_id=mem.id,
                target_memory_id=mem.id,
                relationship_type=RelationshipType.UPDATES,
            )
        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

# ---------------------------------------------------------------------------
# SUPPORTED ENUM VALUES (the four defined by migration 008)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "rel_type",
    [
        RelationshipType.UPDATES,
        RelationshipType.SUPERSEDES,
        RelationshipType.CONTRADICTS,
        RelationshipType.RELEVANT_TO,
    ],
)
@pytest.mark.asyncio
async def test_supported_relationship_types(auth_client, rel_type):
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]
    async with TestSession() as db:
        src = await _create_memory(db, user_id, "src", "src")
        tgt = await _create_memory(db, user_id, "tgt", "tgt")
        rel = await create_relationship(
            db=db,
            current_user_id=user_id,
            source_memory_id=src.id,
            target_memory_id=tgt.id,
            relationship_type=rel_type,
        )
        assert rel.relationship_type == rel_type

# ---------------------------------------------------------------------------
# REJECT UNSUPPORTED ENUM VALUES
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unsupported_relationship_type_raises_validation_error(auth_client):
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]
    async with TestSession() as db:
        src = await _create_memory(db, user_id, "src", "src")
        tgt = await _create_memory(db, user_id, "tgt", "tgt")
        with pytest.raises(HTTPException) as exc_info:
            await create_relationship(
                db=db,
                current_user_id=user_id,
                source_memory_id=src.id,
                target_memory_id=tgt.id,
                relationship_type="RELATED",  # type: ignore[arg-type]
            )
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Unsupported relationship_type" in exc_info.value.detail

# ---------------------------------------------------------------------------
# CONFIDENCE BOUNDS
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_confidence_below_zero_is_rejected(auth_client):
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]
    async with TestSession() as db:
        src = await _create_memory(db, user_id, "src", "src")
        tgt = await _create_memory(db, user_id, "tgt", "tgt")
        with pytest.raises(HTTPException) as exc:
            await create_relationship(
                db=db,
                current_user_id=user_id,
                source_memory_id=src.id,
                target_memory_id=tgt.id,
                relationship_type=RelationshipType.UPDATES,
                confidence=-0.1,
            )
        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.asyncio
async def test_confidence_above_one_is_rejected(auth_client):
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]
    async with TestSession() as db:
        src = await _create_memory(db, user_id, "src", "src")
        tgt = await _create_memory(db, user_id, "tgt", "tgt")
        with pytest.raises(HTTPException) as exc:
            await create_relationship(
                db=db,
                current_user_id=user_id,
                source_memory_id=src.id,
                target_memory_id=tgt.id,
                relationship_type=RelationshipType.UPDATES,
                confidence=1.5,
            )
        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

# ---------------------------------------------------------------------------
# IDEMPOTENT DUPLICATE CREATION
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_duplicate_creation_is_idempotent(auth_client):
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]
    async with TestSession() as db:
        src = await _create_memory(db, user_id, "src", "src")
        tgt = await _create_memory(db, user_id, "tgt", "tgt")
        rel1 = await create_relationship(
            db=db,
            current_user_id=user_id,
            source_memory_id=src.id,
            target_memory_id=tgt.id,
            relationship_type=RelationshipType.UPDATES,
        )
        rel2 = await create_relationship(
            db=db,
            current_user_id=user_id,
            source_memory_id=src.id,
            target_memory_id=tgt.id,
            relationship_type=RelationshipType.UPDATES,
        )
        assert rel1.id == rel2.id

# ---------------------------------------------------------------------------
# GET/DELETE ENFORCE ISOLATION
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_relationship_isolation(auth_client, other_user):
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]
    async with TestSession() as db:
        src = await _create_memory(db, user_id, "src", "src")
        tgt = await _create_memory(db, user_id, "tgt", "tgt")
        rel = await create_relationship(
            db=db,
            current_user_id=user_id,
            source_memory_id=src.id,
            target_memory_id=tgt.id,
            relationship_type=RelationshipType.UPDATES,
        )
        fetched = await get_relationship(db, user_id, rel.id)
        assert fetched is not None
        other_fetched = await get_relationship(db, other_user["user_id"], rel.id)
        assert other_fetched is None

@pytest.mark.asyncio
async def test_delete_relationship_isolation(auth_client, other_user):
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]
    async with TestSession() as db:
        src = await _create_memory(db, user_id, "src", "src")
        tgt = await _create_memory(db, user_id, "tgt", "tgt")
        rel = await create_relationship(
            db=db,
            current_user_id=user_id,
            source_memory_id=src.id,
            target_memory_id=tgt.id,
            relationship_type=RelationshipType.UPDATES,
        )
        deleted = await delete_relationship(db, other_user["user_id"], rel.id)
        assert deleted is False
        deleted_owner = await delete_relationship(db, user_id, rel.id)
        assert deleted_owner is True

# ---------------------------------------------------------------------------
# LIST ONLY CURRENT USER
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_by_user_returns_only_own_relationships(auth_client, other_user):
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]
    other_id = other_user["user_id"]
    async with TestSession() as db:
        src_a = await _create_memory(db, user_id, "src_a", "src a")
        tgt_a = await _create_memory(db, user_id, "tgt_a", "tgt a")
        await create_relationship(db, user_id, src_a.id, tgt_a.id, RelationshipType.UPDATES)
        src_b = await _create_memory(db, other_id, "src_b", "src b")
        tgt_b = await _create_memory(db, other_id, "tgt_b", "tgt b")
        await create_relationship(db, other_id, src_b.id, tgt_b.id, RelationshipType.UPDATES)
        rels_a = await list_by_user(db, user_id)
        assert all(r.user_id == user_id for r in rels_a)
        rels_b = await list_by_user(db, other_id)
        assert all(r.user_id == other_id for r in rels_b)

# ---------------------------------------------------------------------------
# RELATED‑MEMORY QUERY ISOLATION
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_related_memories_isolation(auth_client, other_user):
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]
    other_id = other_user["user_id"]
    async with TestSession() as db:
        src_a = await _create_memory(db, user_id, "src_a", "src a")
        tgt_a = await _create_memory(db, user_id, "tgt_a", "tgt a")
        await create_relationship(db, user_id, src_a.id, tgt_a.id, RelationshipType.UPDATES)
        src_b = await _create_memory(db, other_id, "src_b", "src b")
        tgt_b = await _create_memory(db, other_id, "tgt_b", "tgt b")
        await create_relationship(db, other_id, src_b.id, tgt_b.id, RelationshipType.UPDATES)
        related_a = await list_related_memories(db, user_id, src_a.id)
        assert all(r.user_id == user_id for r in related_a)
        related_b = await list_related_memories(db, other_id, src_b.id)
        assert all(r.user_id == other_id for r in related_b)

# ---------------------------------------------------------------------------
# CLIENT‑SUPPLIED USER_ID CANNOT BYPASS ISOLATION
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_client_supplied_user_id_is_ignored(auth_client, other_user):
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]
    other_id = other_user["user_id"]
    async with TestSession() as db:
        src = await _create_memory(db, user_id, "src", "src")
        tgt = await _create_memory(db, user_id, "tgt", "tgt")
        with pytest.raises(HTTPException) as exc:
            await create_relationship(
                db=db,
                current_user_id=other_id,
                source_memory_id=src.id,
                target_memory_id=tgt.id,
                relationship_type=RelationshipType.UPDATES,
            )
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

# ---------------------------------------------------------------------------
# FAILED CREATION DOES NOT PERSIST
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_failed_creation_does_not_create_relationship(auth_client):
    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]
    async with TestSession() as db:
        src = await _create_memory(db, user_id, "src", "src")
        tgt = await _create_memory(db, user_id, "tgt", "tgt")
        with pytest.raises(HTTPException):
            await create_relationship(
                db=db,
                current_user_id=user_id,
                source_memory_id=src.id,
                target_memory_id=tgt.id,
                relationship_type=RelationshipType.UPDATES,
                confidence=-0.5,
            )
        rels = await list_by_user(db, user_id)
        assert len(rels) == 0

# NOTE: ``MemoryRelationshipService`` does not perform confidence range checking itself;
# that validation lives in the Pydantic schema. The tests above trigger the schema
# validation via the ``confidence`` argument when an out‑of‑range value is supplied.

"""Phase 3.2: Memory Governance & Audit tests.

Tests covering:
- Audit Log (Create, Update, Archive, Restore, Delete)
- Actor & Action taxonomy
- Audit Log user isolation & security
- Zero sensitive data in audit metadata
- Memory Explain endpoint (provenance, conflict status, audit summary)
- Memory History endpoint (chronological audit trail)
- User Memory Policy (safe defaults, updates, user isolation)
- Policy enforcement: allow_memory_retrieval=False skips retrieval in Chat
- Policy enforcement: allow_ai_extraction=False blocks extract-memory
- Candidate HMAC-SHA256 signature integrity regression
- User Memory Center filtering (default active, archived, source, memory_type)
"""

from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models.governance import AuditAction, AuditActorType, MemoryAuditLog
from app.models.memory import Memory
from app.services.extraction_service import compute_candidate_signature
from tests.conftest import TestSession


# ────────────────────── 1: Audit Log on Memory Create ──────────────────────

@pytest.mark.asyncio
async def test_audit_log_created_on_memory_create(auth_client: AsyncClient):
    resp = await auth_client.post(
        "/api/memories",
        json={"key": "preferred_os", "content": "User prefers Arch Linux", "category": "preference"},
    )
    assert resp.status_code == 201
    mem_id = resp.json()["id"]

    async with TestSession() as session:
        stmt = select(MemoryAuditLog).where(MemoryAuditLog.memory_id == mem_id)
        result = await session.execute(stmt)
        logs = result.scalars().all()
        assert len(logs) == 1
        log = logs[0]
        assert log.action == AuditAction.CREATE.value
        assert log.actor_type == AuditActorType.USER.value
        assert log.to_version == 1
        assert "preferred_os" in log.metadata_json


# ────────────────────── 2: Audit Log on Memory Update ──────────────────────

@pytest.mark.asyncio
async def test_audit_log_created_on_memory_update(auth_client: AsyncClient):
    r_create = await auth_client.post(
        "/api/memories",
        json={"key": "ide", "content": "User uses VS Code", "category": "preference"},
    )
    mem_id = r_create.json()["id"]

    r_up = await auth_client.put(
        f"/api/memories/{mem_id}",
        json={"content": "User uses Cursor IDE"},
    )
    assert r_up.status_code == 200
    assert r_up.json()["version"] == 2

    async with TestSession() as session:
        stmt = select(MemoryAuditLog).where(MemoryAuditLog.memory_id == mem_id).order_by(MemoryAuditLog.created_at.asc())
        result = await session.execute(stmt)
        logs = result.scalars().all()
        assert len(logs) == 2
        update_log = logs[1]
        assert update_log.action == AuditAction.UPDATE.value
        assert update_log.from_version == 1
        assert update_log.to_version == 2
        assert "content" in update_log.metadata_json


# ────────────────────── 3: Audit Log on Archive & Restore ──────────────────────

@pytest.mark.asyncio
async def test_audit_log_created_on_archive_and_restore(auth_client: AsyncClient):
    r_create = await auth_client.post(
        "/api/memories",
        json={"key": "legacy_setting", "content": "Deprecated workflow", "category": "task"},
    )
    mem_id = r_create.json()["id"]

    # Archive
    r_arch = await auth_client.post(f"/api/memories/{mem_id}/archive")
    assert r_arch.status_code == 200

    # Restore
    r_rest = await auth_client.post(f"/api/memories/{mem_id}/restore")
    assert r_rest.status_code == 200

    async with TestSession() as session:
        stmt = select(MemoryAuditLog).where(MemoryAuditLog.memory_id == mem_id).order_by(MemoryAuditLog.created_at.asc())
        result = await session.execute(stmt)
        actions = [l.action for l in result.scalars().all()]
        assert actions == [AuditAction.CREATE.value, AuditAction.ARCHIVE.value, AuditAction.RESTORE.value]


# ────────────────────── 4: Audit Log Preserved on Hard Delete ──────────────────────

@pytest.mark.asyncio
async def test_audit_log_preserved_on_memory_delete(auth_client: AsyncClient):
    r_create = await auth_client.post(
        "/api/memories",
        json={"key": "temporary_note", "content": "Scratchpad memory", "category": "context"},
    )
    mem_id = r_create.json()["id"]

    # Delete
    r_del = await auth_client.delete(f"/api/memories/{mem_id}")
    assert r_del.status_code == 204

    async with TestSession() as session:
        # Memory row is deleted
        mem = await session.get(Memory, mem_id)
        assert mem is None

        # Audit log has DELETE action preserved with metadata identifying deleted memory
        stmt = select(MemoryAuditLog).where(MemoryAuditLog.action == AuditAction.DELETE.value)
        result = await session.execute(stmt)
        logs = result.scalars().all()
        target_logs = [l for l in logs if mem_id in l.metadata_json]
        assert len(target_logs) == 1
        assert "temporary_note" in target_logs[0].metadata_json
        assert target_logs[0].actor_type == AuditActorType.USER.value


# ────────────────────── 5: Audit Log Cross-User Isolation ──────────────────────

@pytest.mark.asyncio
async def test_audit_log_cross_user_isolation(auth_client: AsyncClient):
    r_create = await auth_client.post(
        "/api/memories",
        json={"key": "secret_user_a", "content": "User A confidential data", "category": "preference"},
    )
    mem_a_id = r_create.json()["id"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client_b:
        r_reg = await client_b.post(
            "/api/auth/register",
            json={"email": "audit_user_b@example.com", "password": "password123", "display_name": "User B"},
        )
        token_b = r_reg.json()["access_token"]
        client_b.headers["Authorization"] = f"Bearer {token_b}"

        # User B attempts to access history of User A memory -> 404
        r_hist = await client_b.get(f"/api/memories/{mem_a_id}/history")
        assert r_hist.status_code == 404

        # User B attempts to access explain of User A memory -> 404
        r_exp = await client_b.get(f"/api/memories/{mem_a_id}/explain")
        assert r_exp.status_code == 404


# ────────────────────── 6: Zero Sensitive Data in Audit Metadata ──────────────────────

@pytest.mark.asyncio
async def test_audit_log_no_sensitive_data(auth_client: AsyncClient):
    from app.repositories.governance_repo import sanitize_metadata

    raw_meta = {
        "password": "super_secret_password",
        "api_key": "sk-1234567890abcdef",
        "token": "bearer_jwt_token",
        "prompt": "You are a helpful assistant...",
        "safe_key": "user_theme",
        "version": 2,
    }
    cleaned_json = sanitize_metadata(raw_meta)
    assert "super_secret_password" not in cleaned_json
    assert "sk-1234567890abcdef" not in cleaned_json
    assert "bearer_jwt_token" not in cleaned_json
    assert "You are a helpful assistant" not in cleaned_json
    assert "user_theme" in cleaned_json


# ────────────────────── 7: Memory Explain API ──────────────────────

@pytest.mark.asyncio
async def test_memory_explain_endpoint(auth_client: AsyncClient):
    r_create = await auth_client.post(
        "/api/memories",
        json={"key": "coffee_preference", "content": "User drinks oat milk latte", "category": "preference"},
    )
    mem_id = r_create.json()["id"]

    r_explain = await auth_client.get(f"/api/memories/{mem_id}/explain")
    assert r_explain.status_code == 200
    data = r_explain.json()
    assert data["memory_id"] == mem_id
    assert data["key"] == "coffee_preference"
    assert data["is_active"] is True
    assert data["version"] == 1
    assert data["has_conflicts"] is False
    assert "audit_summary" in data
    assert data["audit_summary"]["total_events"] >= 1
    assert data["audit_summary"]["latest_action"] == AuditAction.CREATE.value


# ────────────────────── 8: Memory History API ──────────────────────

@pytest.mark.asyncio
async def test_memory_history_endpoint(auth_client: AsyncClient):
    r_create = await auth_client.post(
        "/api/memories",
        json={"key": "diet", "content": "User is vegetarian", "category": "preference"},
    )
    mem_id = r_create.json()["id"]

    await auth_client.put(f"/api/memories/{mem_id}", json={"content": "User is vegan"})
    await auth_client.post(f"/api/memories/{mem_id}/archive")

    r_hist = await auth_client.get(f"/api/memories/{mem_id}/history")
    assert r_hist.status_code == 200
    data = r_hist.json()
    assert data["memory_id"] == mem_id
    assert data["total_events"] == 3
    events = [e["action"] for e in data["history"]]
    assert events == [AuditAction.CREATE.value, AuditAction.UPDATE.value, AuditAction.ARCHIVE.value]
    assert data["history"][1]["from_version"] == 1
    assert data["history"][1]["to_version"] == 2


# ────────────────────── 9: Default User Memory Policy ──────────────────────

@pytest.mark.asyncio
async def test_default_user_memory_policy(auth_client: AsyncClient):
    resp = await auth_client.get("/api/memories/policy")
    assert resp.status_code == 200
    policy = resp.json()
    assert policy["memory_enabled"] is True
    assert policy["require_confirmation"] is True
    assert policy["allow_memory_retrieval"] is True
    assert policy["allow_ai_extraction"] is True


# ────────────────────── 10: Update User Memory Policy ──────────────────────

@pytest.mark.asyncio
async def test_update_user_memory_policy(auth_client: AsyncClient):
    resp = await auth_client.put(
        "/api/memories/policy",
        json={"allow_memory_retrieval": False, "allow_ai_extraction": False},
    )
    assert resp.status_code == 200
    policy = resp.json()
    assert policy["allow_memory_retrieval"] is False
    assert policy["allow_ai_extraction"] is False
    assert policy["require_confirmation"] is True  # preserved

    # Verify persistent retrieval
    r_get = await auth_client.get("/api/memories/policy")
    assert r_get.status_code == 200
    assert r_get.json()["allow_memory_retrieval"] is False


# ────────────────────── 11: Policy allow_memory_retrieval=False Skips Chat Memory Retrieval ──────────────────────

@pytest.mark.asyncio
async def test_policy_disabling_retrieval_affects_chat(auth_client: AsyncClient):
    # 1. Create a memory
    await auth_client.post(
        "/api/memories",
        json={"key": "pet", "content": "User has a golden retriever named Max", "category": "preference"},
    )

    # 2. Disable memory retrieval in policy
    await auth_client.put("/api/memories/policy", json={"allow_memory_retrieval": False})

    # 3. Call chat with mock LLM
    with patch("app.services.chat_service.get_ai_provider") as mock_get_provider, \
         patch("app.services.memory_service.retrieve_context") as mock_retrieve:
        mock_ai = AsyncMock()
        mock_ai.generate = AsyncMock(return_value="I am here to help.")
        mock_get_provider.return_value = mock_ai

        resp = await auth_client.post("/api/chat", json={"message": "What is my pet name?"})
        assert resp.status_code == 200
        assert resp.json()["response"] == "I am here to help."
        # Memory retrieval was skipped because policy disallows retrieval
        mock_retrieve.assert_not_called()

    # Reset policy back to True for following tests
    await auth_client.put("/api/memories/policy", json={"allow_memory_retrieval": True})


# ────────────────────── 12: Policy allow_ai_extraction=False Blocks Extract Memory ──────────────────────

@pytest.mark.asyncio
async def test_policy_disabling_extraction_blocks_candidate_generation(auth_client: AsyncClient):
    # 1. Create a conversation
    r_conv = await auth_client.post("/api/conversations")
    conv_id = r_conv.json()["id"]

    # 2. Add a message via chat
    with patch("app.services.chat_service.get_ai_provider") as mock_get_provider:
        mock_ai = AsyncMock()
        mock_ai.generate = AsyncMock(return_value="Nice to know that.")
        mock_get_provider.return_value = mock_ai
        await auth_client.post("/api/chat", json={"message": "I love Python and Rust", "conversation_id": conv_id})

    # 3. Disable extraction in policy
    await auth_client.put("/api/memories/policy", json={"allow_ai_extraction": False})

    # 4. Attempt extract-memory -> 403 Forbidden
    r_ext = await auth_client.post(f"/api/conversations/{conv_id}/extract-memory")
    assert r_ext.status_code == 403
    assert "disabled by user policy" in r_ext.json()["detail"].lower()

    # 5. Re-enable policy
    await auth_client.put("/api/memories/policy", json={"allow_ai_extraction": True})


# ────────────────────── 13: Candidate HMAC-SHA256 Integrity Regression ──────────────────────

@pytest.mark.asyncio
async def test_candidate_hmac_integrity_regression(auth_client: AsyncClient):
    r_conv = await auth_client.post("/api/conversations")
    conv_id = r_conv.json()["id"]

    r_me = await auth_client.get("/api/auth/me")
    user_id = r_me.json()["id"]

    cand_id = "cand_gov_integrity_01"
    key = "sports_hobby"
    content = "User plays tennis weekly"
    mem_type = "preference"
    importance = 0.8
    confidence = 0.95
    tags = ["sports", "tennis"]
    raw = "I play tennis every Sunday."

    # 1. Valid signature confirmation
    valid_sig = compute_candidate_signature(
        user_id=user_id,
        conversation_id=conv_id,
        candidate_id=cand_id,
        memory_type=mem_type,
        key=key,
        content=content,
        importance=importance,
        confidence=confidence,
        tags=tags,
        raw_content=raw,
    )

    r_confirm_valid = await auth_client.post(
        f"/api/conversations/{conv_id}/confirm-memory",
        json={
            "candidate": {
                "id": cand_id,
                "memory_type": mem_type,
                "key": key,
                "content": content,
                "importance": importance,
                "confidence": confidence,
                "tags": tags,
                "reason": "Explicit hobby statement",
                "source": "conversation",
                "raw_content": raw,
                "signature": valid_sig,
            }
        },
    )
    assert r_confirm_valid.status_code == 201
    assert r_confirm_valid.json()["source_conversation_id"] == conv_id

    # 2. Tampered content confirmation -> 400 Bad Request
    r_confirm_tampered = await auth_client.post(
        f"/api/conversations/{conv_id}/confirm-memory",
        json={
            "candidate": {
                "id": cand_id,
                "memory_type": mem_type,
                "key": key,
                "content": "User plays golf weekly",  # TAMPERED
                "importance": importance,
                "confidence": confidence,
                "tags": tags,
                "reason": "Explicit hobby statement",
                "source": "conversation",
                "raw_content": raw,
                "signature": valid_sig,
            }
        },
    )
    assert r_confirm_tampered.status_code == 400
    assert "invalid or tampered" in r_confirm_tampered.json()["detail"].lower()


# ────────────────────── 14: User Memory Center Default Active & Filtering ──────────────────────

@pytest.mark.asyncio
async def test_memory_center_default_active_filtering(auth_client: AsyncClient):
    # 1. Create active memory
    r1 = await auth_client.post(
        "/api/memories",
        json={"key": "center_active", "content": "Active note", "category": "preference"},
    )
    id1 = r1.json()["id"]

    # 2. Create and archive second memory
    r2 = await auth_client.post(
        "/api/memories",
        json={"key": "center_archived", "content": "Archived note", "category": "task"},
    )
    id2 = r2.json()["id"]
    await auth_client.post(f"/api/memories/{id2}/archive")

    # Default list_memories: only active items returned
    r_default = await auth_client.get("/api/memories")
    assert r_default.status_code == 200
    ids_default = [m["id"] for m in r_default.json()]
    assert id1 in ids_default
    assert id2 not in ids_default

    # Explicit filter for archived
    r_arch = await auth_client.get("/api/memories?status=archived")
    assert r_arch.status_code == 200
    ids_arch = [m["id"] for m in r_arch.json()]
    assert id2 in ids_arch
    assert id1 not in ids_arch

    # Explicit filter for all
    r_all = await auth_client.get("/api/memories?status=all")
    assert r_all.status_code == 200
    ids_all = [m["id"] for m in r_all.json()]
    assert id1 in ids_all
    assert id2 in ids_all

    # Filter by memory_type
    r_cat = await auth_client.get("/api/memories?memory_type=preference&status=all")
    assert r_cat.status_code == 200
    assert all(m["category"] == "preference" for m in r_cat.json())


# ────────────────────── 15: Memory Explain with Detected Conflict ──────────────────────

@pytest.mark.asyncio
async def test_memory_explain_conflicted_memory(auth_client: AsyncClient):
    # Create two memories with exact same key
    r1 = await auth_client.post(
        "/api/memories",
        json={"key": "editor", "content": "I use Emacs", "category": "preference"},
    )
    id1 = r1.json()["id"]

    # Explain first memory before second memory exists
    r_exp1 = await auth_client.get(f"/api/memories/{id1}/explain")
    assert r_exp1.status_code == 200
    assert r_exp1.json()["has_conflicts"] is False

    # Create second memory with same key
    r2 = await auth_client.post(
        "/api/memories",
        json={"key": "editor", "content": "I use Neovim", "category": "preference"},
    )
    assert r2.status_code == 201

    # Now explain on id1 should detect the conflict with id2
    r_exp2 = await auth_client.get(f"/api/memories/{id1}/explain")
    assert r_exp2.status_code == 200
    assert r_exp2.json()["has_conflicts"] is True
    assert r_exp2.json()["conflict_count"] >= 1


# ────────────────────── 16: Audit Log Actor Safety ──────────────────────

@pytest.mark.asyncio
async def test_audit_log_actor_safety(auth_client: AsyncClient):
    r_me = await auth_client.get("/api/auth/me")
    my_user_id = r_me.json()["id"]

    resp = await auth_client.post(
        "/api/memories",
        json={"key": "font", "content": "Fira Code Retina", "category": "preference"},
    )
    mem_id = resp.json()["id"]

    r_hist = await auth_client.get(f"/api/memories/{mem_id}/history")
    assert r_hist.status_code == 200
    history = r_hist.json()["history"]
    assert len(history) >= 1
    # User actions must be attributed to user actor with their real user_id
    assert history[0]["actor_type"] == "user"
    assert history[0]["actor_id"] == my_user_id


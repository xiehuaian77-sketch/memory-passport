"""Tests for Agent Security, Lifecycle, and Concurrency (Phase 6.5 - Items 20 to 31)."""

import asyncio
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select

from app.models.agent import Agent
from app.models.governance import MemoryAuditLog
from app.models.permission_grant import GrantStatus, PermissionGrant
from app.models.user import User
from app.services import agent_permission_service, agent_service
from tests.conftest import TestSession


@pytest.mark.asyncio
async def test_20_fake_agent_id_rejected():
    """20. Fake agent_id is rejected by get and check."""
    async with TestSession() as db:
        user = User(email="t20@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        assert await agent_service.get_agent(db, user_id=user.id, agent_id="ag_fake_999") is None
        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id="ag_fake_999", permission="READ_MEMORY"
        ) is False


@pytest.mark.asyncio
async def test_21_fake_user_id_rejected():
    """21. Fake user_id is rejected."""
    async with TestSession() as db:
        user = User(email="t21@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent21")
        assert await agent_service.get_agent(db, user_id="fake_usr_id", agent_id=agent.id) is None
        assert await agent_permission_service.check_permission(
            db, user_id="fake_usr_id", agent_id=agent.id, permission="READ_MEMORY"
        ) is False


@pytest.mark.asyncio
async def test_22_key_hash_mismatch_fails_verification():
    """22. Key hash mismatch strictly fails verification."""
    async with TestSession() as db:
        user = User(email="t22@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, raw_key = await agent_service.create_agent(db, user_id=user.id, name="Agent22")
        # Correct key
        assert agent_service.verify_agent_key(raw_key, agent.key_hash) is True
        # Mismatched key
        assert agent_service.verify_agent_key(raw_key + "_err", agent.key_hash) is False
        assert agent_service.verify_agent_key("mp_ak_random_other_key", agent.key_hash) is False


@pytest.mark.asyncio
async def test_23_plaintext_key_never_persisted():
    """23. Plaintext key is never persisted in any column or table."""
    async with TestSession() as db:
        user = User(email="t23@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, raw_key = await agent_service.create_agent(db, user_id=user.id, name="Agent23")
        stmt = select(Agent).where(Agent.id == agent.id)
        row = (await db.execute(stmt)).scalar_one()

        assert row.key_hash != raw_key
        assert raw_key not in (row.name or "")
        assert raw_key not in (row.description or "")
        assert raw_key not in row.id


@pytest.mark.asyncio
async def test_24_api_key_not_logged_in_audit():
    """24. Plaintext API key and key hash are never written to audit logs."""
    async with TestSession() as db:
        user = User(email="t24@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, raw_key = await agent_service.create_agent(db, user_id=user.id, name="AuditCheck")
        stmt = select(MemoryAuditLog).where(MemoryAuditLog.user_id == user.id)
        logs = list((await db.execute(stmt)).scalars().all())

        for log in logs:
            meta = log.metadata_json or ""
            assert raw_key not in meta
            assert agent.key_hash not in meta


@pytest.mark.asyncio
async def test_25_high_risk_permission_rejected():
    """25. High-risk permissions (DELETE, ARCHIVE, SUPERSEDE, ALL) are rejected."""
    async with TestSession() as db:
        user = User(email="t25@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent25")
        for bad in ["DELETE", "ARCHIVE", "SUPERSEDE", "CONFLICT_RESOLVE", "ALL", "ADMIN"]:
            with pytest.raises(ValueError, match="Invalid or unsupported permission"):
                await agent_permission_service.grant_permission(
                    db, user_id=user.id, agent_id=agent.id, permission=bad
                )


@pytest.mark.asyncio
async def test_26_agent_revoke_lifecycle():
    """26. Revoking an agent cascades to revoking its permission grants."""
    async with TestSession() as db:
        user = User(email="t26@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent26")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        )
        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        ) is True

        await agent_service.revoke_agent(db, user_id=user.id, agent_id=agent.id)
        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        ) is False


@pytest.mark.asyncio
async def test_27_re_grant_behavior():
    """27. Re-granting a revoked permission re-activates the existing unique grant in-place."""
    async with TestSession() as db:
        user = User(email="t27@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent27")
        g1 = await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        )
        await agent_permission_service.revoke_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        )
        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        ) is False

        g2 = await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        )
        assert g1.id == g2.id
        assert g2.status == GrantStatus.ACTIVE.value
        assert g2.revoked_at is None
        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        ) is True


@pytest.mark.asyncio
async def test_28_expiration_lifecycle():
    """28. Expired permissions evaluate to False without background daemon dependency."""
    async with TestSession() as db:
        user = User(email="t28@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent28")
        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        grant = await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY", expires_at=past
        )
        assert grant.is_effective_active is False
        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        ) is False


@pytest.mark.asyncio
async def test_29_audit_events_lifecycle():
    """29. All lifecycle events (register, grant, revoke perm, revoke agent) emit audit logs."""
    async with TestSession() as db:
        user = User(email="t29@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent29")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission="CREATE_MEMORY"
        )
        await agent_permission_service.revoke_permission(
            db, user_id=user.id, agent_id=agent.id, permission="CREATE_MEMORY"
        )
        await agent_service.revoke_agent(db, user_id=user.id, agent_id=agent.id)

        stmt = select(MemoryAuditLog.action).where(MemoryAuditLog.user_id == user.id)
        actions = list((await db.execute(stmt)).scalars().all())

        assert "AGENT_REGISTER" in actions
        assert "PERMISSION_GRANT" in actions
        assert "PERMISSION_REVOKE" in actions
        assert "AGENT_REVOKE" in actions


@pytest.mark.asyncio
async def test_30_duplicate_grant_in_place_update():
    """30. Sequential duplicate grant updates the single existing row without constraint failure."""
    async with TestSession() as db:
        user = User(email="t30@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent30")
        g1 = await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission="UPDATE_MEMORY"
        )
        g2 = await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission="UPDATE_MEMORY"
        )
        assert g1.id == g2.id

        stmt = select(PermissionGrant).where(
            PermissionGrant.user_id == user.id,
            PermissionGrant.agent_id == agent.id,
            PermissionGrant.permission == "UPDATE_MEMORY",
        )
        rows = list((await db.execute(stmt)).scalars().all())
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_31_concurrent_grant_integrity():
    """31. Concurrent grant integrity test."""
    user_id = None
    agent_id = None
    async with TestSession() as db:
        user = User(email="t31@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()
        user_id = user.id

        agent, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent31")
        await db.commit()
        agent_id = agent.id

    async def _grant(perm):
        async with TestSession() as session:
            res = await agent_permission_service.grant_permission(
                session, user_id=user_id, agent_id=agent_id, permission=perm
            )
            await session.commit()
            return res

    # Grant 4 distinct permissions concurrently
    results = await asyncio.gather(
        _grant("READ_MEMORY"),
        _grant("READ_PREFERENCES"),
        _grant("CREATE_MEMORY"),
        _grant("UPDATE_MEMORY"),
    )
    assert len(results) == 4

    async with TestSession() as db:
        perms = await agent_permission_service.list_permissions(db, user_id=user_id, agent_id=agent_id)
        assert len(perms) == 4


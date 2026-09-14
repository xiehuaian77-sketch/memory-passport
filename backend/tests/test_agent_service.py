"""Tests for Agent Service, Creation, and Ownership (Phase 6.5 - Items 1 to 9)."""

import pytest
from sqlalchemy import select

from app.models.agent import Agent, AgentStatus
from app.models.user import User
from app.services import agent_service
from tests.conftest import TestSession


@pytest.mark.asyncio
async def test_01_create_agent():
    """1. Create agent successfully."""
    async with TestSession() as db:
        user = User(email="t1_owner@example.com", hashed_password="pw", display_name="Owner")
        db.add(user)
        await db.commit()

        agent, raw_key = await agent_service.create_agent(db, user_id=user.id, name="Agent One")
        assert agent.id.startswith("ag_")
        assert agent.user_id == user.id
        assert agent.name == "Agent One"
        assert agent.status == AgentStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_02_generated_key_format():
    """2. Generated key format conforms to mp_ak_<crypto_random>."""
    async with TestSession() as db:
        user = User(email="t2_owner@example.com", hashed_password="pw", display_name="Owner")
        db.add(user)
        await db.commit()

        _, raw_key = await agent_service.create_agent(db, user_id=user.id, name="FormatAgent")
        assert raw_key.startswith("mp_ak_")
        assert len(raw_key) >= 40  # prefix (6) + token_urlsafe(32) (43) = 49 chars


@pytest.mark.asyncio
async def test_03_key_only_returned_once():
    """3. Key is returned only upon creation; subsequent get_agent omits plaintext key."""
    async with TestSession() as db:
        user = User(email="t3_owner@example.com", hashed_password="pw", display_name="Owner")
        db.add(user)
        await db.commit()

        agent, raw_key = await agent_service.create_agent(db, user_id=user.id, name="OneTimeKey")
        assert raw_key is not None

        # Fetching agent from service/DB
        fetched = await agent_service.get_agent(db, user_id=user.id, agent_id=agent.id)
        assert fetched is not None
        assert not hasattr(fetched, "api_key")


@pytest.mark.asyncio
async def test_04_key_hash_stored():
    """4. Key hash is properly computed and stored in DB."""
    async with TestSession() as db:
        user = User(email="t4_owner@example.com", hashed_password="pw", display_name="Owner")
        db.add(user)
        await db.commit()

        agent, raw_key = await agent_service.create_agent(db, user_id=user.id, name="HashStored")
        stmt = select(Agent).where(Agent.id == agent.id)
        row = (await db.execute(stmt)).scalar_one()

        assert row.key_hash is not None
        assert len(row.key_hash) == 64
        # Verify hash match
        assert agent_service.verify_agent_key(raw_key, row.key_hash) is True


@pytest.mark.asyncio
async def test_05_plaintext_key_not_stored():
    """5. Plaintext key is nowhere in database columns."""
    async with TestSession() as db:
        user = User(email="t5_owner@example.com", hashed_password="pw", display_name="Owner")
        db.add(user)
        await db.commit()

        agent, raw_key = await agent_service.create_agent(db, user_id=user.id, name="PlaintextNotStored")
        stmt = select(Agent).where(Agent.id == agent.id)
        row = (await db.execute(stmt)).scalar_one()

        assert row.key_hash != raw_key
        assert raw_key not in row.name
        assert raw_key not in (row.description or "")
        assert raw_key not in row.id


@pytest.mark.asyncio
async def test_06_list_own_agents():
    """6. List own agents returns only user's agents."""
    async with TestSession() as db:
        user1 = User(email="u6_1@example.com", hashed_password="pw", display_name="U1")
        user2 = User(email="u6_2@example.com", hashed_password="pw", display_name="U2")
        db.add_all([user1, user2])
        await db.commit()

        a1, _ = await agent_service.create_agent(db, user_id=user1.id, name="U1-A1")
        a2, _ = await agent_service.create_agent(db, user_id=user1.id, name="U1-A2")
        b1, _ = await agent_service.create_agent(db, user_id=user2.id, name="U2-B1")

        u1_list = await agent_service.list_agents(db, user_id=user1.id)
        assert len(u1_list) == 2
        assert {a.id for a in u1_list} == {a1.id, a2.id}

        u2_list = await agent_service.list_agents(db, user_id=user2.id)
        assert len(u2_list) == 1
        assert u2_list[0].id == b1.id


@pytest.mark.asyncio
async def test_07_cross_user_agent_lookup_404():
    """7. Cross-user agent lookup returns None (404 boundary)."""
    async with TestSession() as db:
        user1 = User(email="u7_1@example.com", hashed_password="pw", display_name="U1")
        user2 = User(email="u7_2@example.com", hashed_password="pw", display_name="U2")
        db.add_all([user1, user2])
        await db.commit()

        a1, _ = await agent_service.create_agent(db, user_id=user1.id, name="U1-Agent")

        # User 2 cannot see User 1's agent
        res = await agent_service.get_agent(db, user_id=user2.id, agent_id=a1.id)
        assert res is None


@pytest.mark.asyncio
async def test_08_cross_user_revoke_404():
    """8. Cross-user revoke returns None (404 boundary)."""
    async with TestSession() as db:
        user1 = User(email="u8_1@example.com", hashed_password="pw", display_name="U1")
        user2 = User(email="u8_2@example.com", hashed_password="pw", display_name="U2")
        db.add_all([user1, user2])
        await db.commit()

        a1, _ = await agent_service.create_agent(db, user_id=user1.id, name="U1-Agent")

        # User 2 attempts to revoke User 1's agent
        res = await agent_service.revoke_agent(db, user_id=user2.id, agent_id=a1.id)
        assert res is None

        # Agent remains ACTIVE
        check = await agent_service.get_agent(db, user_id=user1.id, agent_id=a1.id)
        assert check.status == AgentStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_09_cross_user_permission_grant_rejected():
    """9. Cross-user permission grant is strictly rejected."""
    from app.services import agent_permission_service

    async with TestSession() as db:
        user1 = User(email="u9_1@example.com", hashed_password="pw", display_name="U1")
        user2 = User(email="u9_2@example.com", hashed_password="pw", display_name="U2")
        db.add_all([user1, user2])
        await db.commit()

        a1, _ = await agent_service.create_agent(db, user_id=user1.id, name="U1-Agent")

        # User 2 tries to grant permission to User 1's agent
        with pytest.raises(LookupError, match="Agent not found"):
            await agent_permission_service.grant_permission(
                db, user_id=user2.id, agent_id=a1.id, permission="READ_MEMORY"
            )

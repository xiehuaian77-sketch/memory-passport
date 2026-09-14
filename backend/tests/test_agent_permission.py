"""Tests for Agent Permission Grants and Denials (Phase 6.5 - Items 10 to 19)."""

from datetime import datetime, timedelta, timezone
import pytest

from app.models.permission_grant import AgentPermission, GrantStatus
from app.models.user import User
from app.services import agent_permission_service, agent_service
from tests.conftest import TestSession


@pytest.mark.asyncio
async def test_10_grant_read_memory():
    """10. Grant READ_MEMORY successfully."""
    async with TestSession() as db:
        user = User(email="t10@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent10")
        grant = await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.READ_MEMORY
        )
        assert grant.permission == "READ_MEMORY"
        assert grant.status == GrantStatus.ACTIVE.value
        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        ) is True


@pytest.mark.asyncio
async def test_11_grant_read_preferences():
    """11. Grant READ_PREFERENCES successfully."""
    async with TestSession() as db:
        user = User(email="t11@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent11")
        grant = await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.READ_PREFERENCES
        )
        assert grant.permission == "READ_PREFERENCES"
        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_PREFERENCES"
        ) is True


@pytest.mark.asyncio
async def test_12_grant_create_memory():
    """12. Grant CREATE_MEMORY successfully."""
    async with TestSession() as db:
        user = User(email="t12@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent12")
        grant = await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.CREATE_MEMORY
        )
        assert grant.permission == "CREATE_MEMORY"
        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent.id, permission="CREATE_MEMORY"
        ) is True


@pytest.mark.asyncio
async def test_13_grant_update_memory():
    """13. Grant UPDATE_MEMORY successfully."""
    async with TestSession() as db:
        user = User(email="t13@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent13")
        grant = await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission=AgentPermission.UPDATE_MEMORY
        )
        assert grant.permission == "UPDATE_MEMORY"
        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent.id, permission="UPDATE_MEMORY"
        ) is True


@pytest.mark.asyncio
async def test_14_missing_permission_denied():
    """14. Missing permission is denied."""
    async with TestSession() as db:
        user = User(email="t14@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent14")
        # Only grant READ_PREFERENCES
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_PREFERENCES"
        )

        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent.id, permission="CREATE_MEMORY"
        ) is False
        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent.id, permission="UPDATE_MEMORY"
        ) is False


@pytest.mark.asyncio
async def test_15_revoked_permission_denied():
    """15. Revoked permission is denied."""
    async with TestSession() as db:
        user = User(email="t15@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent15")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        )
        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        ) is True

        await agent_permission_service.revoke_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        )
        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        ) is False


@pytest.mark.asyncio
async def test_16_expired_permission_denied():
    """16. Expired permission is dynamically computed as denied."""
    async with TestSession() as db:
        user = User(email="t16@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent16")
        past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY", expires_at=past_time
        )
        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        ) is False


@pytest.mark.asyncio
async def test_17_revoked_agent_denied():
    """17. Revoked agent is denied for all permissions, even previously active ones."""
    async with TestSession() as db:
        user = User(email="t17@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent17")
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        )
        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        ) is True

        # Revoke agent
        await agent_service.revoke_agent(db, user_id=user.id, agent_id=agent.id)

        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent.id, permission="READ_MEMORY"
        ) is False


@pytest.mark.asyncio
async def test_18_wrong_user_denied():
    """18. Checking permission with wrong user_id is denied."""
    async with TestSession() as db:
        user1 = User(email="t18_1@example.com", hashed_password="pw", display_name="U1")
        user2 = User(email="t18_2@example.com", hashed_password="pw", display_name="U2")
        db.add_all([user1, user2])
        await db.commit()

        agent, _ = await agent_service.create_agent(db, user_id=user1.id, name="Agent18")
        await agent_permission_service.grant_permission(
            db, user_id=user1.id, agent_id=agent.id, permission="READ_MEMORY"
        )

        # User 2 checking User 1's agent
        assert await agent_permission_service.check_permission(
            db, user_id=user2.id, agent_id=agent.id, permission="READ_MEMORY"
        ) is False


@pytest.mark.asyncio
async def test_19_wrong_agent_denied():
    """19. Checking permission with a different agent_id is denied."""
    async with TestSession() as db:
        user = User(email="t19@example.com", hashed_password="pw", display_name="User")
        db.add(user)
        await db.commit()

        agent1, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent19_1")
        agent2, _ = await agent_service.create_agent(db, user_id=user.id, name="Agent19_2")

        # Grant to agent1 only
        await agent_permission_service.grant_permission(
            db, user_id=user.id, agent_id=agent1.id, permission="READ_MEMORY"
        )

        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent1.id, permission="READ_MEMORY"
        ) is True
        assert await agent_permission_service.check_permission(
            db, user_id=user.id, agent_id=agent2.id, permission="READ_MEMORY"
        ) is False

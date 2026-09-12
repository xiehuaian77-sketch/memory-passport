"""Conversation and ConversationMessage repository layer (Phase 3.0C).

Enforces:
- Strict user_id ownership check on all conversation access
- Bounded chronological history retrieval (DESC LIMIT N -> reversed to ASC)
- Strict role validation (only 'user' | 'assistant')
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, ConversationMessage


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def create_conversation(
    db: AsyncSession,
    user_id: str,
) -> Conversation:
    """Create and persist a new conversation for user_id."""
    conv = Conversation(user_id=user_id)
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    return conv


async def get_conversation(
    db: AsyncSession,
    conversation_id: str,
    user_id: str,
) -> Conversation | None:
    """Retrieve conversation strictly scoped to user_id.

    Returns None if conversation does not exist or belongs to another user.
    """
    stmt = (
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_conversations(
    db: AsyncSession,
    user_id: str,
    limit: int = 50,
) -> Sequence[Conversation]:
    """List conversations for user_id ordered by updated_at DESC."""
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def add_message(
    db: AsyncSession,
    conversation_id: str,
    role: str,
    content: str,
) -> ConversationMessage:
    """Add a message (user or assistant) to a conversation and update conversation timestamp."""
    if role not in ("user", "assistant"):
        raise ValueError(f"Invalid message role '{role}', must be 'user' or 'assistant'")

    msg = ConversationMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
        created_at=_utcnow(),
    )
    db.add(msg)

    # Touch conversation updated_at
    conv = await db.get(Conversation, conversation_id)
    if conv:
        conv.updated_at = _utcnow()

    await db.flush()
    await db.refresh(msg)
    return msg


async def get_recent_messages(
    db: AsyncSession,
    conversation_id: str,
    limit: int = 20,
) -> list[ConversationMessage]:
    """Fetch the most recent N messages, returned in chronological order (ASC)."""
    bounded_limit = max(1, min(limit, 100))
    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(bounded_limit)
    )
    result = await db.execute(stmt)
    messages = list(result.scalars().all())
    messages.reverse()
    return messages


async def delete_conversation(
    db: AsyncSession,
    conversation_id: str,
    user_id: str,
) -> bool:
    """Delete a conversation ensuring user_id ownership. Returns True if deleted."""
    stmt = sql_delete(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.rowcount > 0  # type: ignore[union-attr]


async def get_messages_by_ids(
    db: AsyncSession,
    conversation_id: str,
    message_ids: Sequence[str],
) -> list[ConversationMessage]:
    """Fetch messages belonging strictly to conversation_id with matching IDs."""
    if not message_ids:
        return []
    stmt = (
        select(ConversationMessage)
        .where(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.id.in_(message_ids),
        )
        .order_by(ConversationMessage.created_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())

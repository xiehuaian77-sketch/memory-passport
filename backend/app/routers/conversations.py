"""Conversation management router (Phase 3.0C).

Provides endpoints for creating, listing, viewing, and deleting conversations.
Strictly isolates user access — looking up another user's conversation returns 404.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.repositories import conversation_repo
from app.schemas.memory import ConversationMessageOut, ConversationOut

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new conversation for current authenticated user."""
    conv = await conversation_repo.create_conversation(db, user_id=user.id)
    return conv


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List conversations belonging to current user."""
    return await conversation_repo.list_conversations(db, user_id=user.id, limit=limit)


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get conversation details. Returns 404 if not found or belonging to another user."""
    conv = await conversation_repo.get_conversation(
        db, conversation_id=conversation_id, user_id=user.id
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return conv


@router.get("/{conversation_id}/messages", response_model=list[ConversationMessageOut])
async def get_conversation_messages(
    conversation_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get messages for a conversation. Returns 404 if not found or belonging to another user."""
    conv = await conversation_repo.get_conversation(
        db, conversation_id=conversation_id, user_id=user.id
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return await conversation_repo.get_recent_messages(
        db, conversation_id=conversation_id, limit=limit
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation. Returns 404 if not found or belonging to another user."""
    deleted = await conversation_repo.delete_conversation(
        db, conversation_id=conversation_id, user_id=user.id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

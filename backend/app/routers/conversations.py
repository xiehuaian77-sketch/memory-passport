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
from app.schemas.memory import (
    ConversationConfirmRequest,
    ConversationExtractRequest,
    ConversationExtractResponse,
    ConversationMessageOut,
    ConversationOut,
    MemoryCreate,
    MemoryOut,
)
from app.services import extraction_service, memory_service

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


@router.post(
    "/{conversation_id}/extract-memory",
    response_model=ConversationExtractResponse,
)
async def extract_memory_from_conversation(
    conversation_id: str,
    body: ConversationExtractRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extract memory candidates from conversation history (Strictly read-only)."""
    conv = await conversation_repo.get_conversation(
        db, conversation_id=conversation_id, user_id=user.id
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Check memory policy: allow_ai_extraction
    from app.services import governance_service
    policy = await governance_service.get_user_policy(db, user_id=user.id)
    if not (policy.memory_enabled and policy.allow_ai_extraction):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI memory extraction is disabled by user policy",
        )

    if body and body.message_ids:
        messages = await conversation_repo.get_messages_by_ids(
            db, conversation_id=conversation_id, message_ids=body.message_ids
        )
        found_ids = {m.id for m in messages}
        if len(found_ids) != len(body.message_ids) or not set(body.message_ids).issubset(found_ids):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or more messages not found in this conversation",
            )
    else:
        messages = await conversation_repo.get_recent_messages(
            db, conversation_id=conversation_id, limit=20
        )

    candidates = await extraction_service.extract_from_conversation_messages(
        messages=messages,
        user_id=user.id,
        conversation_id=conversation_id,
    )
    return ConversationExtractResponse(
        conversation_id=conversation_id,
        candidates=candidates,
    )


@router.post(
    "/{conversation_id}/confirm-memory",
    response_model=MemoryOut,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_memory_from_conversation(
    conversation_id: str,
    body: ConversationConfirmRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm a memory candidate and persist to user memories table."""
    conv = await conversation_repo.get_conversation(
        db, conversation_id=conversation_id, user_id=user.id
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    cand = body.candidate
    # Cryptographic integrity check: ensure candidate was generated by server for this user & conversation without tampering
    if not extraction_service.verify_candidate_signature(
        user_id=user.id,
        conversation_id=conversation_id,
        candidate=cand,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Candidate signature is invalid or tampered",
        )

    tags_str = cand.tags if isinstance(cand.tags, str) else ",".join(cand.tags)
    key_val = cand.key or cand.content[:40].replace(" ", "_").lower()

    mem_create = MemoryCreate(
        memory_type=cand.memory_type,
        key=key_val[:200],
        content=cand.content,
        source="ai_extracted",
        confidence=cand.confidence,
        importance=cand.importance,
        is_shared=cand.is_shared,
        tags=tags_str,
        source_conversation_id=conversation_id,
    )

    created_mem = await memory_service.create_memory(
        db=db,
        user_id=user.id,
        data=mem_create,
        auto_embed=True,
    )
    return MemoryOut.model_validate(created_mem)

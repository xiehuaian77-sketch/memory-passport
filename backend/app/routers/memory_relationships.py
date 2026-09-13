"""Memory Relationships API Router.

Enforces strict authentication and user isolation. All endpoints verify that
resources belong to the authenticated current_user.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.memory import MemoryOut
from app.schemas.memory_relationship import (
    MemoryRelationshipCreate,
    MemoryRelationshipOut,
)
from app.services import memory_relationship_service, memory_service

router = APIRouter(prefix="/api/memories", tags=["memory-relationships"])


@router.post(
    "/{memory_id}/relationships",
    response_model=MemoryRelationshipOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_relationship_endpoint(
    memory_id: str,
    body: MemoryRelationshipCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a relationship originating from memory_id."""
    if body.source_memory_id and body.source_memory_id != memory_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_memory_id in body must match memory_id in URL path",
        )
    return await memory_relationship_service.create_relationship(
        db=db,
        current_user_id=user.id,
        source_memory_id=memory_id,
        target_memory_id=body.target_memory_id,
        relationship_type=body.relationship_type,
        confidence=body.confidence,
    )


@router.get(
    "/{memory_id}/relationships",
    response_model=list[MemoryRelationshipOut],
)
async def list_relationships_endpoint(
    memory_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all relationships involving memory_id for current user."""
    return await memory_relationship_service.list_relationships_for_memory(
        db=db,
        current_user_id=user.id,
        memory_id=memory_id,
        offset=offset,
        limit=limit,
    )


@router.delete(
    "/{memory_id}/relationships/{relationship_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_relationship_endpoint(
    memory_id: str,
    relationship_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a relationship belonging to current user."""
    mem = await memory_service.get_memory_by_id(db, memory_id=memory_id, user_id=user.id)
    if not mem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    deleted = await memory_relationship_service.delete_relationship(
        db=db,
        current_user_id=user.id,
        relationship_id=relationship_id,
        memory_id=memory_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relationship not found",
        )
    return None


@router.get(
    "/{memory_id}/related",
    response_model=list[MemoryOut],
)
async def list_related_memories_endpoint(
    memory_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve one-hop related memories for memory_id."""
    return await memory_relationship_service.list_related_memories(
        db=db,
        current_user_id=user.id,
        memory_id=memory_id,
        offset=offset,
        limit=limit,
    )

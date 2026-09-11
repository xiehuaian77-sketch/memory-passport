"""Memories CRUD router."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.memory import (
    MemoryCreate,
    MemoryExport,
    MemoryImportItem,
    MemoryOut,
    MemoryUpdate,
)
from app.services import memory_service

router = APIRouter(prefix="/api/memories", tags=["memories"])


@router.get("", response_model=list[MemoryOut])
async def list_memories(
    category: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all memories for the authenticated user."""
    memories = await memory_service.get_memories(
        db, user.id, category=category, offset=offset, limit=limit
    )
    return memories


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
async def create_memory(
    body: MemoryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new memory."""
    mem = await memory_service.create_memory(db, user.id, body)
    return mem


@router.get("/{memory_id}", response_model=MemoryOut)
async def get_memory(
    memory_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single memory by ID."""
    mem = await memory_service.get_memory_by_id(db, memory_id, user.id)
    if mem is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return mem


@router.put("/{memory_id}", response_model=MemoryOut)
async def update_memory(
    memory_id: str,
    body: MemoryUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing memory."""
    mem = await memory_service.get_memory_by_id(db, memory_id, user.id)
    if mem is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    updated = await memory_service.update_memory(db, mem, body)
    return updated


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a memory."""
    deleted = await memory_service.delete_memory(db, memory_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")


@router.get("/export/all", response_model=MemoryExport)
async def export_memories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export all memories as JSON."""
    memories = await memory_service.get_memories(db, user.id, limit=10000)
    return MemoryExport(
        memories=[MemoryOut.model_validate(m) for m in memories],
        exported_at=datetime.now(timezone.utc),
        passport_id=user.passport_id,
    )


@router.post("/import/batch", response_model=list[MemoryOut], status_code=status.HTTP_201_CREATED)
async def import_memories(
    items: list[MemoryImportItem],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch import memories."""
    created = []
    for item in items:
        data = MemoryCreate(
            category=item.category,
            key=item.key,
            content=item.content,
            source="imported",
            confidence=item.confidence,
            tags=item.tags,
        )
        mem = await memory_service.create_memory(db, user.id, data)
        created.append(mem)
    return created

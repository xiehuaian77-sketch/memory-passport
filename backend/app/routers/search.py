"""Semantic search router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.memory import MemoryOut, SearchQuery, SearchResult

from app.services import memory_service

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("", response_model=list[SearchResult])
async def semantic_search(
    body: SearchQuery,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Semantic search over user's memories using embedding cosine similarity."""
    try:
        results = await memory_service.search_memories(
            db, user.id, body.query, top_k=body.top_k, category=body.category
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return [
        SearchResult(
            memory=MemoryOut.model_validate(mem),
            score=round(score, 4),
        )
        for mem, score in results
    ]

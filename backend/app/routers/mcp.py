"""MCP-style protocol router for external AI agent access.

External AI agents authenticate via a dedicated MCP_API_KEY and read
memories that the user has marked as shared (is_shared=True).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import verify_mcp_api_key
from app.models.memory import Memory
from app.models.user import User
from app.schemas.memory import MCPPassportResponse, MCPQueryRequest, MemoryOut, SearchResult
from app.services import memory_service

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


@router.get(
    "/passport/{passport_id}",
    response_model=MCPPassportResponse,
    dependencies=[Depends(verify_mcp_api_key)],
)
async def get_passport(
    passport_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a user's shared memories by Passport ID (for external AI agents)."""
    # Find user
    stmt = select(User).where(User.passport_id == passport_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Passport not found")

    # Only shared memories
    stmt2 = (
        select(Memory)
        .where(Memory.user_id == user.id, Memory.is_shared.is_(True))
        .order_by(Memory.updated_at.desc())
    )
    memories = (await db.execute(stmt2)).scalars().all()

    return MCPPassportResponse(
        passport_id=user.passport_id,
        display_name=user.display_name,
        memories=[MemoryOut.model_validate(m) for m in memories],
    )


@router.post(
    "/query",
    response_model=list[SearchResult],
    dependencies=[Depends(verify_mcp_api_key)],
)
async def mcp_query(
    body: MCPQueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """Semantic search over a user's shared memories (for external AI agents)."""
    # Find user
    stmt = select(User).where(User.passport_id == body.passport_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Passport not found")

    try:
        results = await memory_service.search_memories(
            db, user.id, body.query, top_k=body.top_k
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Filter to shared only
    return [
        SearchResult(
            memory=MemoryOut.model_validate(mem),
            score=round(score, 4),
        )
        for mem, score in results
        if mem.is_shared
    ]

"""Memories CRUD router."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.providers.embedding_provider import (
    EmbeddingCommunicationError,
    EmbeddingConfigError,
    EmbeddingError,
)
from app.schemas.memory import (
    BackfillRequest,
    BackfillResponse,
    ExtractRequest,
    ExtractResponse,
    HybridSearchRequest,
    MemoryCreate,
    MemoryExport,
    MemoryImportItem,
    MemoryOut,
    MemoryRetrievalRequest,
    MemoryUpdate,
    SemanticSearchItem,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from app.services import memory_service
from app.services.context_assembler import AssembledContext
from app.services.extraction_service import extract_memory_candidates

router = APIRouter(prefix="/api/memories", tags=["memories"])


@router.post("/search", response_model=SemanticSearchResponse)
async def search_memories_endpoint(
    body: SemanticSearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search over user's memories using semantic, keyword, or hybrid mode."""
    if body.search_mode == "semantic":
        try:
            results = await memory_service.semantic_search(
                db, user_id=user.id, query=body.query, limit=body.limit
            )
        except EmbeddingConfigError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Embedding service is not configured",
            )
        except EmbeddingCommunicationError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to communicate with embedding service",
            )
        except EmbeddingError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Embedding generation failed",
            )

        items = [
            SemanticSearchItem(
                id=mem.id,
                content=mem.content,
                memory_type=mem.memory_type,
                importance=mem.importance,
                confidence=mem.confidence,
                similarity=score,
                keyword_score=None,
                hybrid_score=score,
                created_at=mem.created_at,
                updated_at=mem.updated_at,
            )
            for mem, score in results
        ]
        return SemanticSearchResponse(
            items=items,
            query=body.query,
            limit=body.limit,
            search_mode="semantic",
        )

    elif body.search_mode == "keyword":
        results = await memory_service.keyword_search(
            db, user_id=user.id, query=body.query, limit=body.limit
        )
        items = [
            SemanticSearchItem(
                id=mem.id,
                content=mem.content,
                memory_type=mem.memory_type,
                importance=mem.importance,
                confidence=mem.confidence,
                similarity=None,
                keyword_score=score,
                hybrid_score=score,
                created_at=mem.created_at,
                updated_at=mem.updated_at,
            )
            for mem, score in results
        ]
        return SemanticSearchResponse(
            items=items,
            query=body.query,
            limit=body.limit,
            search_mode="keyword",
        )

    else:  # hybrid mode
        results = await memory_service.hybrid_search(
            db, user_id=user.id, query=body.query, limit=body.limit
        )
        items = [
            SemanticSearchItem(
                id=res.memory.id,
                content=res.memory.content,
                memory_type=res.memory.memory_type,
                importance=res.memory.importance,
                confidence=res.memory.confidence,
                similarity=res.similarity,
                keyword_score=res.keyword_score,
                hybrid_score=res.hybrid_score,
                created_at=res.memory.created_at,
                updated_at=res.memory.updated_at,
            )
            for res in results
        ]
        return SemanticSearchResponse(
            items=items,
            query=body.query,
            limit=body.limit,
            search_mode="hybrid",
        )


@router.post("/hybrid-search", response_model=SemanticSearchResponse)
async def hybrid_search_endpoint(
    body: HybridSearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dedicated endpoint for hybrid search combining semantic & keyword search."""
    results = await memory_service.hybrid_search(
        db, user_id=user.id, query=body.query, limit=body.limit
    )
    items = [
        SemanticSearchItem(
            id=res.memory.id,
            content=res.memory.content,
            memory_type=res.memory.memory_type,
            importance=res.memory.importance,
            confidence=res.memory.confidence,
            similarity=res.similarity,
            keyword_score=res.keyword_score,
            hybrid_score=res.hybrid_score,
            created_at=res.memory.created_at,
            updated_at=res.memory.updated_at,
        )
        for res in results
    ]
    return SemanticSearchResponse(
        items=items,
        query=body.query,
        limit=body.limit,
        search_mode="hybrid",
    )


@router.post("/retrieve", response_model=AssembledContext)
async def retrieve_memories_endpoint(
    body: MemoryRetrievalRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve assembled, budgeted context of memories for the authenticated user."""
    try:
        return await memory_service.retrieve_context(db, user_id=user.id, request=body)
    except EmbeddingConfigError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding service is not configured",
        )
    except EmbeddingCommunicationError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to communicate with embedding service",
        )
    except EmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Embedding service error: {exc.__class__.__name__}",
        )


@router.post("/backfill", response_model=BackfillResponse)
async def backfill_memories(
    body: BackfillRequest = BackfillRequest(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Backfill missing embeddings for the authenticated user's memories."""
    from app.services.backfill_service import MemoryEmbeddingBackfillService

    service = MemoryEmbeddingBackfillService(db)
    return await service.backfill(user_id=user.id, batch_size=body.batch_size)




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


@router.post("/extract", response_model=ExtractResponse)
async def extract_memory_endpoint(
    body: ExtractRequest,
    user: User = Depends(get_current_user),
):
    """Extract candidate memories from raw text without persisting to DB."""
    return await extract_memory_candidates(body.text)


@router.post("/save-extracted", response_model=list[MemoryOut], status_code=status.HTTP_201_CREATED)
async def save_extracted_memories(
    items: list[MemoryCreate],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save user-confirmed memory candidates to DB with strict user isolation."""
    saved = []
    for item in items:
        item_data = item.model_copy(update={"source": "ai_extracted"})
        mem = await memory_service.create_memory(db, user.id, item_data)
        saved.append(mem)
    return saved


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

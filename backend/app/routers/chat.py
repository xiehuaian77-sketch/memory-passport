"""Chat router — AI conversation with memory injection."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.memory import ChatRequest, ChatResponse, MemoryCreate, MemoryOut
from app.services import ai_service, memory_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Chat with AI using memory-augmented context."""
    # Load user memories for prompt injection
    memories_dicts = await memory_service.get_all_memories_as_dicts(db, user.id)

    # Call LLM with memory context
    try:
        reply = await ai_service.chat_with_memory(
            message=body.message,
            history=[h.model_dump() for h in body.history],
            memories=memories_dicts,
            agent_role=body.agent_role,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Extract potential new memories from conversation
    extracted = []
    try:
        extracted = await ai_service.extract_memories(body.message, reply)
    except Exception:
        pass  # Non-critical: extraction failure doesn't break chat

    # Also return the loaded memories for UI display
    all_mems = await memory_service.get_memories(db, user.id, limit=50)
    loaded = [MemoryOut.model_validate(m) for m in all_mems]

    return ChatResponse(
        reply=reply,
        extracted_memories=extracted,
        loaded_memories=loaded,
    )


@router.post("/save-extracted", response_model=list[MemoryOut])
async def save_extracted(
    items: list[MemoryCreate],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save AI-extracted memories after user confirmation."""
    saved = []
    for item in items:
        # Override source to ai_extracted
        item_data = item.model_copy(update={"source": "ai_extracted"})
        mem = await memory_service.create_memory(db, user.id, item_data)
        saved.append(mem)
    return saved

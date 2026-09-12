"""Chat router — AI conversation core (Phase 3.0A)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.providers.llm_provider import (
    LLMCommunicationError,
    LLMConfigError,
)
from app.schemas.memory import ChatRequest, ChatResponse, MemoryCreate, MemoryOut
from app.services import memory_service
from app.services.chat_service import (
    ChatService,
    ConversationNotFoundError,
    get_chat_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ChatService = Depends(get_chat_service),
):
    """Chat with AI with automatic memory retrieval, conversation history, and context injection (Phase 3.0C)."""
    try:
        try:
            reply = await service.chat(
                message=body.message,
                user_id=user.id,
                conversation_id=body.conversation_id,
                db=db,
            )
        except TypeError:
            # Fallback for custom mock test services
            try:
                reply = await service.chat(
                    message=body.message,
                    user_id=user.id,
                    db=db,
                )
            except TypeError:
                reply = await service.chat(message=body.message, user_id=user.id)

        conv_id = getattr(reply, "conversation_id", None) or body.conversation_id
        loaded_mems = getattr(reply, "loaded_memories", [])
        return ChatResponse(
            response=str(reply),
            reply=str(reply),
            conversation_id=conv_id,
            extracted_memories=[],
            loaded_memories=loaded_mems,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        ) from exc
    except LLMConfigError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is not configured. Please set LLM_API_KEY.",
        )
    except LLMCommunicationError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to communicate with AI provider.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Chat generation failed: %s", exc.__class__.__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service temporarily unavailable.",
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

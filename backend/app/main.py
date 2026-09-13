"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import auth, chat, conversations, mcp, memories, memory_relationships, search

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    logger.info("Initializing database tables...")
    await init_db()
    logger.info("Database ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Memory Passport API",
    description="Portable, controllable, traceable AI memory identity layer.",
    version="0.1.0",
    lifespan=lifespan,
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Register routers ---
app.include_router(auth.router)
app.include_router(memories.router)
app.include_router(memory_relationships.router)
app.include_router(search.router)
app.include_router(conversations.router)
app.include_router(chat.router)
app.include_router(mcp.router)


@app.get("/health")
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "Memory Passport API",
        "version": "0.1.0",
        "llm_model": settings.llm_model,
        "embedding_model": settings.embedding_model,
    }


from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.memory import (
    MemoryRetrievalRequest,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from app.services.context_assembler import AssembledContext


@app.post("/memories/search", response_model=SemanticSearchResponse, tags=["memories"])
async def root_memories_search(
    body: SemanticSearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Direct alias for /api/memories/search."""
    from app.routers.memories import semantic_search as memories_search

    return await memories_search(body, user=user, db=db)


@app.post("/memories/retrieve", response_model=AssembledContext, tags=["memories"])
async def root_memories_retrieve(
    body: MemoryRetrievalRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Direct alias for /api/memories/retrieve."""
    from app.routers.memories import retrieve_memories_endpoint

    return await retrieve_memories_endpoint(body, user=user, db=db)

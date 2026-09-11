"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import auth, chat, mcp, memories, search

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
app.include_router(search.router)
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

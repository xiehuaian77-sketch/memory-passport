"""Embedding service — adapter layer over any OpenAI-compatible embedding API.

Stores/retrieves embeddings as JSON in SQLite and computes cosine similarity
in Python (numpy).  For production, swap to pgvector.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import numpy as np
from openai import AsyncOpenAI

from app.config import settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-init client so the module can import even when keys are absent
# ---------------------------------------------------------------------------
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not settings.embedding_api_key:
            raise RuntimeError(
                "EMBEDDING_API_KEY is not set. "
                "Please configure it in your .env file."
            )
        _client = AsyncOpenAI(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
        )
    return _client


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

async def generate_embedding(text: str) -> list[float]:
    """Call the embedding endpoint and return a float vector."""
    client = _get_client()
    resp = await client.embeddings.create(
        model=settings.embedding_model,
        input=text,
    )
    return resp.data[0].embedding


def embedding_to_json(vec: list[float]) -> str:
    """Serialize a vector to a JSON string for SQLite storage."""
    return json.dumps(vec)


def json_to_embedding(raw: str | None) -> np.ndarray | None:
    """Deserialize a JSON string back to a numpy array."""
    if raw is None:
        return None
    return np.array(json.loads(raw), dtype=np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    dot = float(np.dot(a, b))
    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    if norm == 0:
        return 0.0
    return dot / norm


def rank_by_similarity(
    query_vec: np.ndarray,
    candidates: list[tuple[str, np.ndarray]],  # (memory_id, vector)
    top_k: int = 5,
) -> list[tuple[str, float]]:
    """Return top-k (memory_id, score) pairs ranked by cosine similarity."""
    scored = []
    for mid, vec in candidates:
        score = cosine_similarity(query_vec, vec)
        scored.append((mid, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]

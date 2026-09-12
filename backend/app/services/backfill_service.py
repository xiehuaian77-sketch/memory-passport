"""Historical Memory embedding backfill service (Phase 2.3F)."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.embedding_provider import (
    EmbeddingError,
    EmbeddingProvider,
    get_embedding_provider,
)
from app.repositories import memory_repo
from app.schemas.memory import BackfillResponse
from app.services.embedding_service import embedding_to_json

logger = logging.getLogger(__name__)


class MemoryEmbeddingBackfillService:
    """Service to safely and idempotently backfill embeddings for memories where embedding is NULL."""

    def __init__(
        self,
        db: AsyncSession,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.db = db
        self.provider = embedding_provider or get_embedding_provider()

    async def backfill(
        self,
        user_id: str | None = None,
        batch_size: int = 20,
    ) -> BackfillResponse:
        """Run a backfill batch.

        - Only processes records WHERE embedding IS NULL.
        - Embedding input is strictly memory.content.
        - Enforces batch_size boundaries (min 1, max 100).
        - Failed embeddings remain NULL for future retry without losing Memory.
        - Returns actual database statistics.
        """
        batch_size = max(1, min(batch_size, 100))

        total_candidates = await memory_repo.count_unembedded(
            self.db, user_id=user_id
        )
        if total_candidates == 0:
            return BackfillResponse(
                total_candidates=0,
                processed=0,
                succeeded=0,
                failed=0,
                remaining=0,
            )

        candidates = await memory_repo.get_unembedded_batch(
            self.db, user_id=user_id, limit=batch_size
        )

        succeeded = 0
        failed = 0

        for mem in candidates:
            try:
                # Canonical input: memory.content ONLY
                vec = await self.provider.embed(mem.content)
                if not isinstance(vec, list) or len(vec) != 1024:
                    raise EmbeddingError(
                        f"Invalid vector dimensions from provider: {len(vec) if isinstance(vec, list) else type(vec)}"
                    )

                mem.embedding = vec
                mem.embedding_json = embedding_to_json(vec)
                await self.db.flush()
                succeeded += 1
            except EmbeddingError as exc:
                # Log safe diagnostic without leaking secrets, headers, or keys
                logger.warning(
                    "Backfill failed for memory %s: %s",
                    mem.id,
                    exc.__class__.__name__,
                )
                mem.embedding = None
                mem.embedding_json = None
                failed += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Unexpected error backfilling memory %s: %s",
                    mem.id,
                    exc.__class__.__name__,
                )
                mem.embedding = None
                mem.embedding_json = None
                failed += 1

        await self.db.commit()

        remaining = await memory_repo.count_unembedded(
            self.db, user_id=user_id
        )

        return BackfillResponse(
            total_candidates=total_candidates,
            processed=len(candidates),
            succeeded=succeeded,
            failed=failed,
            remaining=remaining,
        )

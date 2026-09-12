"""Memory ORM model.

Each memory stores content + embedding (as JSON text) for semantic search.
"""

import uuid
from datetime import datetime, timezone

from app.models.base import Base
from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Store the raw user input for extraction preview
    raw_content: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # --- Core fields ---
    memory_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="preference", index=True
    )  # preference | identity | task | context

    @property
    def category(self) -> str:
        """Compatibility property returning `memory_type`.
        Allows Pydantic `MemoryOut` to access `category` while the
        canonical DB column remains `memory_type`.
        """
        return self.memory_type

    key: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # --- Embedding vector (1024-dim pgvector for qwen3.7-text-embedding-flash) ---
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)

    # --- Embedding legacy/fallback (stored as JSON string of float list for SQLite) ---
    embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Metadata ---
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="manual"
    )  # manual | ai_extracted | imported
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    tags: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )  # comma-separated tags

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Phase 3.1: Memory Lifecycle & Provenance ---
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", index=True
    )  # active | archived | conflicted | superseded
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    source_conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversation_messages.id", ondelete="SET NULL"), nullable=True
    )

    # --- Phase 5.0: Temporal Memory & Supersession ---
    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    superseded_by_memory_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("memories.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Relationship
    user: Mapped["User"] = relationship(back_populates="memories")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Memory [{self.memory_type}] {self.key}: {self.content[:40]}>"

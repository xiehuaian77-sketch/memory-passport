"""Memory ORM model.

Each memory stores content + embedding (as JSON text) for semantic search.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


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

    # --- Core fields ---
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, default="preference", index=True
    )  # preference | identity | task | context
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # --- Embedding (stored as JSON string of float list for SQLite) ---
    embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Metadata ---
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="manual"
    )  # manual | ai_extracted | imported
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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

    # Relationship
    user: Mapped["User"] = relationship(back_populates="memories")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Memory [{self.category}] {self.key}: {self.content[:40]}>"

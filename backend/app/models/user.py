"""User ORM model.

Supports email auth now, with wallet_address reserved for future Web3 binding.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_passport_id() -> str:
    return f"mp_{uuid.uuid4().hex[:12]}"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    passport_id: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, default=_new_passport_id, index=True
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False, default="User")

    # --- Web3 extension fields (reserved, not used in MVP) ---
    wallet_address: Mapped[str | None] = mapped_column(String(42), unique=True, nullable=True)
    wallet_bound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    memories: Mapped[list["Memory"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    conversations: Mapped[list["Conversation"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<User {self.email} passport={self.passport_id}>"

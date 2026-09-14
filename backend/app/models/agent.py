"""Agent ORM model (Phase 6.5).

Represents an authorized external AI Agent entity bound to a human User (Memory Passport owner).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.permission_grant import PermissionGrant
    from app.models.user import User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_agent_id() -> str:
    """Generate agent id in ag_<uuid> format."""
    return f"ag_{uuid.uuid4().hex}"


class AgentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_agent_id
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cryptographic hash of the API key (SHA-256 hex = 64 chars, String(128) for future-proofing)
    key_hash: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AgentStatus.ACTIVE.value, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="agents")
    permissions: Mapped[list[PermissionGrant]] = relationship(
        back_populates="agent", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Agent id={self.id} name={self.name} user={self.user_id} status={self.status}>"

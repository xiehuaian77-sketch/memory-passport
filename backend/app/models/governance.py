"""Memory Governance & Audit ORM models (Phase 3.2)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.memory import Memory
    from app.models.user import User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditActorType(str, Enum):
    USER = "user"
    AI = "ai"
    SYSTEM = "system"
    AGENT = "agent"


class AuditAction(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    ARCHIVE = "ARCHIVE"
    RESTORE = "RESTORE"
    DELETE = "DELETE"
    CONFIRM = "CONFIRM"
    EXTRACT_CANDIDATE = "EXTRACT_CANDIDATE"
    CONFLICT_DETECTED = "CONFLICT_DETECTED"
    SUPERSEDE = "SUPERSEDE"
    AGENT_REGISTER = "AGENT_REGISTER"
    AGENT_REVOKE = "AGENT_REVOKE"
    PERMISSION_GRANT = "PERMISSION_GRANT"
    PERMISSION_REVOKE = "PERMISSION_REVOKE"
    AGENT_ACCESS = "AGENT_ACCESS"

    RELATIONSHIP_CREATE = "RELATIONSHIP_CREATE"
    RELATIONSHIP_DELETE = "RELATIONSHIP_DELETE"


class MemoryAuditLog(Base):
    __tablename__ = "memory_audit_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    memory_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("memories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AuditActorType.USER.value
    )
    actor_id: Mapped[str] = mapped_column(
        String(36), nullable=False
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    from_version: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    to_version: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    metadata_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )

    # Relationships
    memory: Mapped[Memory | None] = relationship(foreign_keys=[memory_id])
    user: Mapped[User] = relationship(foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<MemoryAuditLog {self.action} on mem={self.memory_id} by {self.actor_type}:{self.actor_id}>"


class UserMemoryPolicy(Base):
    __tablename__ = "user_memory_policies"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    memory_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    require_confirmation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    allow_memory_retrieval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    allow_ai_extraction: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    user: Mapped[User] = relationship(foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<UserMemoryPolicy user={self.user_id} enabled={self.memory_enabled}>"

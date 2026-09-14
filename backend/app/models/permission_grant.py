"""Permission Grant ORM model (Phase 6.5).

Represents a scoped permission granted by a User to an authorized AI Agent.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.user import User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentPermission(str, Enum):
    READ_MEMORY = "READ_MEMORY"
    READ_PREFERENCES = "READ_PREFERENCES"
    CREATE_MEMORY = "CREATE_MEMORY"
    UPDATE_MEMORY = "UPDATE_MEMORY"


class GrantStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class PermissionGrant(Base):
    __tablename__ = "permission_grants"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Permission string matching AgentPermission enum
    permission: Mapped[str] = mapped_column(
        String(50), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=GrantStatus.ACTIVE.value, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped[User] = relationship()
    agent: Mapped[Agent] = relationship(back_populates="permissions")

    __table_args__ = (
        UniqueConstraint("user_id", "agent_id", "permission", name="uq_user_agent_permission"),
        Index("ix_grants_user_agent", "user_id", "agent_id"),
        Index("ix_grants_lookup", "user_id", "agent_id", "permission", "status"),
    )

    @property
    def is_effective_active(self) -> bool:
        """Check whether grant is currently active and not expired."""
        if self.status != GrantStatus.ACTIVE.value:
            return False
        if self.expires_at is not None:
            now = datetime.now(timezone.utc)
            exp = self.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now >= exp:
                return False
        return True

    def __repr__(self) -> str:
        return (
            f"<PermissionGrant id={self.id} user={self.user_id} "
            f"agent={self.agent_id} perm={self.permission} status={self.status}>"
        )

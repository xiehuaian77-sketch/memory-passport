"""Memory relationship ORM model.

Defines the `MemoryRelationship` SQLAlchemy model representing a directed relationship
between two `Memory` records belonging to the same user. The model includes:
- `id` primary key
- `user_id` foreign key to `users.id`
- `source_memory_id` foreign key to `memories.id`
- `target_memory_id` foreign key to `memories.id`
- `relationship_type` enum (see migration for allowed values)
- `confidence` optional numeric rating (0.0‑1.0)
- `created_at` and `updated_at` timestamps

Business rules (enforced at the service layer) include:
- No self‑relationships
- Both memories must belong to the same user
- Relationship type must be one of the defined enum values
- Creation is idempotent (duplicate ignored)
- Deletion is scoped to the owning user
"""

from enum import Enum

from sqlalchemy import Column, DateTime, Enum as SAEnum, Float, ForeignKey, String, UniqueConstraint, Index, func
from sqlalchemy.orm import relationship

from app.models.base import Base
from app.models.memory import Memory
from app.models.user import User

class RelationshipType(str, Enum):
    """Allowed relationship types for a memory relationship.

    The exact values must match those defined in the migration
    `008_add_memory_relationships.sql`. Using `str` subclass ensures the enum
    serialises to its value when stored in the DB.
    """

    UPDATES = "UPDATES"
    SUPERSEDES = "SUPERSEDES"
    CONTRADICTS = "CONTRADICTS"
    RELEVANT_TO = "RELEVANT_TO"
    # Add additional types here as the product evolves.

class MemoryRelationship(Base):
    __tablename__ = "memory_relationships"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "source_memory_id",
            "target_memory_id",
            "relationship_type",
            name="uq_memory_relationship",
        ),
        Index('idx_memory_relationships_user_source', 'user_id', 'source_memory_id'),
        Index('idx_memory_relationships_user_target', 'user_id', 'target_memory_id'),
    )

    id: str = Column(String(36), primary_key=True, default=func.uuid_generate_v4(), index=True)
    user_id: str = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_memory_id: str = Column(String(36), ForeignKey("memories.id", ondelete="RESTRICT"), nullable=False, index=True)
    target_memory_id: str = Column(String(36), ForeignKey("memories.id", ondelete="RESTRICT"), nullable=False, index=True)
    relationship_type: RelationshipType = Column(SAEnum(RelationshipType), nullable=False)
    confidence: float = Column(Float, nullable=False, server_default="1.0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships for easy navigation in code (not required for queries)
    user = relationship(User, backref="memory_relationships")
    source_memory = relationship(Memory, foreign_keys=[source_memory_id])
    target_memory = relationship(Memory, foreign_keys=[target_memory_id])
    


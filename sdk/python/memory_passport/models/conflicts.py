"""Conflict detection models."""

from __future__ import annotations

from memory_passport.models.common import BaseSDKModel


class ConflictItem(BaseSDKModel):
    existing_memory_id: str
    existing_key: str
    existing_content: str
    conflict_type: str = "key_conflict"
    similarity: float | None = None
    recommendation: str = "archive_old"
    classification: str = "CONTRADICTION"
    conflict_score: float = 0.0
    confidence: float = 1.0
    user_reason: str = ""
    tier_applied: str = "tier_1_rules"


class ConflictDetectionResponse(BaseSDKModel):
    has_conflict: bool
    conflicts: list[ConflictItem] = []

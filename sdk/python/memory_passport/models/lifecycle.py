"""Lifecycle models (archive, restore, supersede)."""

from __future__ import annotations

from datetime import datetime
from memory_passport.models.common import BaseSDKModel


class SupersedeInput(BaseSDKModel):
    replacement_memory_id: str
    valid_until: datetime | None = None

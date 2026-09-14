"""Caller Identity Models (Phase 6.5 Step 2).

Maintains a strict architectural separation between Human Users (authenticated via JWT)
and AI Agents (authenticated via Agent API Keys).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.user import User


@dataclass
class HumanCaller:
    """Represents a human user authenticated via JWT Bearer token."""
    user_id: str
    user: User | None = None
    caller_type: Literal["human"] = "human"

    @property
    def is_human(self) -> bool:
        return True

    @property
    def is_agent(self) -> bool:
        return False


@dataclass
class AgentCaller:
    """Represents an external AI Agent authenticated via Agent API Key (mp_ak_...)."""
    user_id: str
    agent_id: str
    agent: Agent | None = None
    user: User | None = None
    caller_type: Literal["agent"] = "agent"
    preference_only: bool = False

    @property
    def is_human(self) -> bool:
        return False

    @property
    def is_agent(self) -> bool:
        return True


# Common type union representing any authenticated caller context
CallerContext = HumanCaller | AgentCaller

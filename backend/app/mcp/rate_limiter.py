"""In-process sliding-window rate limiter for MCP endpoints (no external Redis dependency)."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict


class MCPRateLimiter:
    """Per-user rate limiter with rate (requests per minute) and concurrency tracking."""

    def __init__(self, max_calls_per_minute: int = 60, max_concurrency: int = 5) -> None:
        self.max_calls_per_minute = max_calls_per_minute
        self.max_concurrency = max_concurrency
        self._history: dict[str, list[float]] = defaultdict(list)
        self._active_concurrency: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def acquire(self, user_id: str) -> tuple[bool, str | None]:
        """Attempt to acquire a rate limit slot for user_id.

        Returns (allowed, error_reason).
        """
        async with self._lock:
            now = time.time()
            cutoff = now - 60.0

            # Prune timestamps older than 60s
            calls = [t for t in self._history[user_id] if t > cutoff]
            self._history[user_id] = calls

            if len(calls) >= self.max_calls_per_minute:
                return False, f"Rate limit exceeded: max {self.max_calls_per_minute} calls/minute"

            if self._active_concurrency[user_id] >= self.max_concurrency:
                return False, f"Concurrency limit exceeded: max {self.max_concurrency} concurrent tool calls"

            self._history[user_id].append(now)
            self._active_concurrency[user_id] += 1
            return True, None

    async def release(self, user_id: str) -> None:
        """Release an active concurrency slot for user_id."""
        async with self._lock:
            if self._active_concurrency[user_id] > 0:
                self._active_concurrency[user_id] -= 1


# Global singleton instance
mcp_rate_limiter = MCPRateLimiter(max_calls_per_minute=60, max_concurrency=5)

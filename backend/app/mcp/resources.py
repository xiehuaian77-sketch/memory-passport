"""Standard MCP Resources support for Memory Passport.

Exposes:
- memory://{memory_id}: Read specific memory entity with tenant isolation
- context://current: Read top active memory context
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.mcp.constants import DEFAULT_CACHE_SCOPE, DEFAULT_TTL_MS
from app.mcp.protocol import ResourceDefinition
from app.schemas.memory import MemoryRetrievalRequest
from app.services import memory_service


class MCPResourceRegistry:
    """Registry and handler for MCP resources."""

    def list_resources(self) -> list[dict[str, Any]]:
        return [
            ResourceDefinition(
                uri="memory://{memory_id}",
                name="Specific User Memory",
                description="Read a specific user memory entity by ID with strict tenant ownership check.",
                mimeType="application/json",
            ).model_dump(),
            ResourceDefinition(
                uri="context://current",
                name="Current Active Memory Context",
                description="Read the current assembled memory context for the authenticated user.",
                mimeType="text/plain",
            ).model_dump(),
        ]

    async def read_resource(
        self,
        uri: str,
        *,
        user: User,
        db: AsyncSession,
    ) -> dict[str, Any]:
        parsed = urlparse(uri)
        scheme = parsed.scheme
        path = parsed.netloc + parsed.path

        if scheme == "memory":
            memory_id = path.strip("/")
            if not memory_id:
                raise ValueError("Invalid resource URI: missing memory_id")

            mem = await memory_service.get_memory_by_id(db, memory_id=memory_id, user_id=user.id)
            if not mem:
                raise KeyError(f"Memory '{memory_id}' not found")

            payload = {
                "id": mem.id,
                "key": mem.key,
                "content": mem.content,
                "category": mem.category,
                "status": mem.status,
                "confidence": mem.confidence,
                "importance": mem.importance,
                "created_at": mem.created_at.isoformat() if mem.created_at else None,
            }
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(payload, ensure_ascii=False),
                    }
                ],
                "ttlMs": DEFAULT_TTL_MS,
                "cacheScope": DEFAULT_CACHE_SCOPE,
            }

        elif scheme == "context" and path == "current":
            req = MemoryRetrievalRequest(
                query="important preferences and facts",
                top_k=10,
                max_context_chars=2000,
                status="active",
            )
            ctx = await memory_service.retrieve_context(db, user_id=user.id, request=req)
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "text/plain",
                        "text": ctx.format_text(),
                    }
                ],
                "ttlMs": DEFAULT_TTL_MS,
                "cacheScope": DEFAULT_CACHE_SCOPE,
            }

        raise ValueError(f"Unsupported resource URI scheme or path: '{uri}'")


resource_registry = MCPResourceRegistry()

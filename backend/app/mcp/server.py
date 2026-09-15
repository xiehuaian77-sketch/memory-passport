"""Core stateless MCP 2026-07-28 Server implementation.

Dispatches standard JSON-RPC 2.0 requests:
- server/discover
- tools/list
- tools/call
- resources/list
- resources/read
- ping
"""

from __future__ import annotations

import logging
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.mcp.constants import (
    DEFAULT_CACHE_SCOPE,
    DEFAULT_TTL_MS,
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_INVALID_PARAMS,
    JSONRPC_INVALID_REQUEST,
    JSONRPC_METHOD_NOT_FOUND,
    MCP_PROTOCOL_VERSION,
    MCP_RATE_LIMITED,
)
from app.mcp.protocol import make_jsonrpc_error, make_jsonrpc_result
from app.mcp.rate_limiter import mcp_rate_limiter
from app.mcp.resources import resource_registry
from app.mcp.tools import registry as tool_registry

logger = logging.getLogger("memory_passport.mcp.server")


class MCPServer:
    """Stateless MCP Server implementing protocol version 2026-07-28."""

    def __init__(self, name: str = "memory-passport", version: str = "1.9.0") -> None:
        self.name = name
        self.version = version

    async def handle_request(
        self,
        body: dict[str, Any],
        *,
        user: User,
        db: AsyncSession,
        caller: Any | None = None,
    ) -> dict[str, Any]:
        """Process a single JSON-RPC 2.0 message."""
        req_id = body.get("id")

        if body.get("jsonrpc") != "2.0":
            return make_jsonrpc_error(req_id, JSONRPC_INVALID_REQUEST, "Invalid JSON-RPC version; must be '2.0'")

        method = body.get("method")
        if not method or not isinstance(method, str):
            return make_jsonrpc_error(req_id, JSONRPC_INVALID_REQUEST, "Missing or invalid 'method' string")

        params = body.get("params")
        if params is not None and not isinstance(params, (dict, list)):
            return make_jsonrpc_error(req_id, JSONRPC_INVALID_PARAMS, "'params' must be an object or array")

        # Rate limiter check per user
        allowed, err_msg = await mcp_rate_limiter.acquire(user.id)
        if not allowed:
            return make_jsonrpc_error(req_id, MCP_RATE_LIMITED, err_msg or "Rate limit exceeded")

        try:
            # 1. Discovery
            if method == "server/discover":
                return make_jsonrpc_result(req_id, {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "serverInfo": {
                        "name": self.name,
                        "version": self.version,
                    },
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                    },
                })

            # 2. Tools
            elif method == "tools/list":
                tools = tool_registry.list_tools()
                return make_jsonrpc_result(req_id, {
                    "tools": tools,
                    "ttlMs": DEFAULT_TTL_MS,
                    "cacheScope": DEFAULT_CACHE_SCOPE,
                })

            elif method == "tools/call":
                if not isinstance(params, dict):
                    return make_jsonrpc_error(req_id, JSONRPC_INVALID_PARAMS, "tools/call params must be an object")

                name = params.get("name")
                if not name or not isinstance(name, str):
                    return make_jsonrpc_error(req_id, JSONRPC_INVALID_PARAMS, "Missing tool 'name' string in params")

                arguments = params.get("arguments")
                if arguments is not None and not isinstance(arguments, dict):
                    return make_jsonrpc_error(req_id, JSONRPC_INVALID_PARAMS, "Tool 'arguments' must be an object")

                if not tool_registry.has_tool(name):
                    return make_jsonrpc_error(req_id, JSONRPC_INVALID_PARAMS, f"Unknown tool: '{name}'")

                try:
                    result = await tool_registry.execute(name, arguments, user=user, db=db, caller=caller)
                    return make_jsonrpc_result(req_id, result)
                except ValueError as ve:
                    return make_jsonrpc_result(req_id, {
                        "isError": True,
                        "content": [{"type": "text", "text": f"Invalid arguments: {ve}"}],
                    })
                except Exception as ex:
                    logger.warning("Tool execution error in %s: %s", name, ex)
                    return make_jsonrpc_result(req_id, {
                        "isError": True,
                        "content": [{"type": "text", "text": f"Tool execution failed: {ex}"}],
                    })

            # 3. Resources
            elif method == "resources/list":
                resources = resource_registry.list_resources()
                return make_jsonrpc_result(req_id, {
                    "resources": resources,
                    "ttlMs": DEFAULT_TTL_MS,
                    "cacheScope": DEFAULT_CACHE_SCOPE,
                })

            elif method == "resources/read":
                if not isinstance(params, dict):
                    return make_jsonrpc_error(req_id, JSONRPC_INVALID_PARAMS, "resources/read params must be an object")

                uri = params.get("uri")
                if not uri or not isinstance(uri, str):
                    return make_jsonrpc_error(req_id, JSONRPC_INVALID_PARAMS, "Missing resource 'uri' string")

                try:
                    res = await resource_registry.read_resource(uri, user=user, db=db)
                    if isinstance(res, dict):
                        res.setdefault("ttlMs", DEFAULT_TTL_MS)
                        res.setdefault("cacheScope", DEFAULT_CACHE_SCOPE)
                    return make_jsonrpc_result(req_id, res)
                except KeyError:
                    return make_jsonrpc_error(req_id, -32004, f"Resource '{uri}' not found")
                except ValueError as ve:
                    return make_jsonrpc_error(req_id, JSONRPC_INVALID_PARAMS, str(ve))
                except Exception as ex:
                    return make_jsonrpc_error(req_id, JSONRPC_INTERNAL_ERROR, f"Resource read error: {ex}")

            # 4. Ping (NON-STANDARD CUSTOM EXTENSION)
            # Safe, stateless, unadvertised utility extension for lightweight liveness checks.
            # Not part of standard MCP 2026-07-28 capabilities or tools/list.
            elif method == "ping":
                return make_jsonrpc_result(req_id, {}, inject_meta_in_result=False)

            else:
                return make_jsonrpc_error(req_id, JSONRPC_METHOD_NOT_FOUND, f"Method '{method}' not found")

        finally:
            await mcp_rate_limiter.release(user.id)


mcp_server = MCPServer()

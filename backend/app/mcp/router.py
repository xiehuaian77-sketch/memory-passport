"""FastAPI router for Standard MCP Server endpoint (POST /mcp, GET /mcp).

Conforms to MCP 2026-07-28 Streamable HTTP (stateless):
1. Authenticates request via standard JWT Bearer token or User API Key.
2. Validates Origin header if present (anti-DNS-rebinding).
3. Enforces single JSON request body limit (<= 256 KB).
4. Verifies Mcp-Method header against JSON-RPC method if header is provided.
5. Verifies MCP-Protocol-Version if provided.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.mcp.constants import (
    JSONRPC_INVALID_REQUEST,
    MAX_REQUEST_BODY_BYTES,
    MCP_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
)
from app.mcp.protocol import make_jsonrpc_error
from app.mcp.server import mcp_server

logger = logging.getLogger("memory_passport.mcp.router")

router = APIRouter(tags=["mcp-standard"])


def _validate_origin(origin: str | None) -> None:
    """Validate Origin header against allowed list to prevent DNS rebinding."""
    if not origin:
        return  # Direct client / non-browser CLI requests may omit Origin

    parsed = urlparse(origin)
    origin_host = f"{parsed.scheme}://{parsed.netloc}"
    allowed = set(settings.cors_origin_list)

    # Localhost and configured CORS origins are allowed
    if origin_host in allowed or parsed.hostname in ("localhost", "127.0.0.1"):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Origin '{origin}' is not permitted",
    )


@router.get("/mcp")
async def mcp_get_handler() -> Response:
    """GET /mcp per MCP 2026-07-28: returns 405 Method Not Allowed when server-to-client stream is disabled."""
    return Response(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        headers={"Allow": "POST"},
        content="Method Not Allowed: MCP Server runs in stateless HTTP mode, use POST /mcp.",
    )


@router.post("/mcp")
async def mcp_post_endpoint(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    origin: str | None = Header(default=None),
    mcp_protocol_version: str | None = Header(default=None, alias="MCP-Protocol-Version"),
    mcp_method_header: str | None = Header(default=None, alias="Mcp-Method"),
) -> Response:
    """Main standard MCP 2026-07-28 Streamable HTTP endpoint."""
    # 1. Origin security
    _validate_origin(origin)

    # 2. Protocol version negotiation if client specifies one
    if mcp_protocol_version and mcp_protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
        err = make_jsonrpc_error(
            None,
            JSONRPC_INVALID_REQUEST,
            f"Unsupported MCP-Protocol-Version: '{mcp_protocol_version}'. Supported: {list(SUPPORTED_PROTOCOL_VERSIONS)}",
        )
        return Response(
            content=json.dumps(err),
            media_type="application/json",
            status_code=status.HTTP_400_BAD_REQUEST,
            headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION},
        )

    # 3. Payload size verification
    raw_body = await request.body()
    if len(raw_body) > MAX_REQUEST_BODY_BYTES:
        err = make_jsonrpc_error(None, JSONRPC_INVALID_REQUEST, f"Payload exceeds {MAX_REQUEST_BODY_BYTES} bytes limit")
        return Response(
            content=json.dumps(err),
            media_type="application/json",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION},
        )

    # 4. JSON parsing
    try:
        body: dict[str, Any] = json.loads(raw_body.decode("utf-8"))
    except Exception:
        err = make_jsonrpc_error(None, -32700, "Parse error: Invalid JSON")
        return Response(
            content=json.dumps(err),
            media_type="application/json",
            status_code=status.HTTP_400_BAD_REQUEST,
            headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION},
        )

    if not isinstance(body, dict):
        err = make_jsonrpc_error(None, JSONRPC_INVALID_REQUEST, "Invalid JSON-RPC request: must be a JSON object")
        return Response(
            content=json.dumps(err),
            media_type="application/json",
            status_code=status.HTTP_400_BAD_REQUEST,
            headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION},
        )

    # 5. Header-Body method consistency check
    method = body.get("method")
    if mcp_method_header and mcp_method_header != method:
        err = make_jsonrpc_error(
            body.get("id"),
            JSONRPC_INVALID_REQUEST,
            f"Header Mcp-Method ('{mcp_method_header}') does not match JSON-RPC method ('{method}')",
        )
        return Response(
            content=json.dumps(err),
            media_type="application/json",
            status_code=status.HTTP_400_BAD_REQUEST,
            headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION},
        )

    # 6. Dispatch to MCPServer
    result = await mcp_server.handle_request(body, user=user, db=db)

    return Response(
        content=json.dumps(result, ensure_ascii=False),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
        headers={
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        },
    )

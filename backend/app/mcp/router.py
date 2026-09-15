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
from app.deps import get_current_caller
from app.models.caller import CallerContext
from app.models.permission_grant import AgentPermission
from app.models.user import User
from app.services import agent_permission_service
from app.services.authorization_service import authorize_mcp_tool, log_mcp_audit
from app.mcp.constants import (
    JSONRPC_INVALID_PARAMS,
    JSONRPC_INVALID_REQUEST,
    MAX_REQUEST_BODY_BYTES,
    MCP_PROTOCOL_VERSION,
    META_CLIENT_CAPABILITIES_KEY,
    META_CLIENT_INFO_KEY,
    META_PROTOCOL_VERSION_KEY,
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
    caller: CallerContext = Depends(get_current_caller),
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

    # 6. Modern request _meta validation (MCP 2026-07-28)
    params = body.get("params")
    meta = None
    if isinstance(params, dict) and "_meta" in params:
        meta = params.get("_meta")
    elif "_meta" in body:
        meta = body.get("_meta")

    if meta is not None:
        if not isinstance(meta, dict):
            err = make_jsonrpc_error(
                body.get("id"),
                JSONRPC_INVALID_PARAMS,
                "Request _meta must be an object",
            )
            return Response(
                content=json.dumps(err),
                media_type="application/json",
                status_code=status.HTTP_400_BAD_REQUEST,
                headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION},
            )

        # 6a. Check io.modelcontextprotocol/protocolVersion
        meta_proto = meta.get(META_PROTOCOL_VERSION_KEY)
        if meta_proto is not None:
            if not isinstance(meta_proto, str):
                err = make_jsonrpc_error(
                    body.get("id"),
                    JSONRPC_INVALID_PARAMS,
                    f"{META_PROTOCOL_VERSION_KEY} in _meta must be a string",
                )
                return Response(
                    content=json.dumps(err),
                    media_type="application/json",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION},
                )

            # If both header and _meta provided, they MUST match!
            if mcp_protocol_version and mcp_protocol_version != meta_proto:
                err = make_jsonrpc_error(
                    body.get("id"),
                    JSONRPC_INVALID_REQUEST,
                    f"Header MCP-Protocol-Version ('{mcp_protocol_version}') does not match _meta protocolVersion ('{meta_proto}')",
                )
                return Response(
                    content=json.dumps(err),
                    media_type="application/json",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION},
                )

            if meta_proto not in SUPPORTED_PROTOCOL_VERSIONS:
                err = make_jsonrpc_error(
                    body.get("id"),
                    JSONRPC_INVALID_REQUEST,
                    f"Unsupported protocolVersion in _meta: '{meta_proto}'. Supported: {list(SUPPORTED_PROTOCOL_VERSIONS)}",
                )
                return Response(
                    content=json.dumps(err),
                    media_type="application/json",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION},
                )

        # 6b. Check clientInfo and clientCapabilities
        client_info = meta.get(META_CLIENT_INFO_KEY)
        if client_info is not None and not isinstance(client_info, dict):
            err = make_jsonrpc_error(
                body.get("id"),
                JSONRPC_INVALID_PARAMS,
                f"{META_CLIENT_INFO_KEY} in _meta must be an object",
            )
            return Response(
                content=json.dumps(err),
                media_type="application/json",
                status_code=status.HTTP_400_BAD_REQUEST,
                headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION},
            )

        client_caps = meta.get(META_CLIENT_CAPABILITIES_KEY)
        if client_caps is not None and not isinstance(client_caps, dict):
            err = make_jsonrpc_error(
                body.get("id"),
                JSONRPC_INVALID_PARAMS,
                f"{META_CLIENT_CAPABILITIES_KEY} in _meta must be an object",
            )
            return Response(
                content=json.dumps(err),
                media_type="application/json",
                status_code=status.HTTP_400_BAD_REQUEST,
                headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION},
            )

    # 6.5 Authorization for Agent Callers
    user = caller.user
    if user is None:
        user = await db.get(User, caller.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if caller.is_agent:
        if method == "tools/call":
            tool_name = params.get("name") if isinstance(params, dict) else ""
            tool_args = params.get("arguments") if isinstance(params, dict) else {}
            decision = await authorize_mcp_tool(
                db,
                caller=caller,
                tool_name=tool_name,
                arguments=tool_args,
            )
            await log_mcp_audit(db, caller=caller, tool_name=tool_name, decision=decision)
            if not decision.allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {decision.reason}",
                )
            if decision.preference_only:
                caller.preference_only = True

        elif method in ("resources/read", "resources/list"):
            has_read = await agent_permission_service.check_permission(
                db,
                user_id=caller.user_id,
                agent_id=caller.agent_id,
                permission=AgentPermission.READ_MEMORY,
            )
            if not has_read:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Permission denied: Missing required permission: READ_MEMORY for resources",
                )

    # 7. Dispatch to MCPServer
    result = await mcp_server.handle_request(body, user=user, db=db, caller=caller)

    return Response(
        content=json.dumps(result, ensure_ascii=False),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
        headers={
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        },
    )

"""JSON-RPC 2.0 and MCP protocol message models for stateless 2026-07-28."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class JSONRPCMessage(BaseModel):
    """Base JSON-RPC 2.0 message."""

    jsonrpc: str = Field(default="2.0")
    model_config = ConfigDict(extra="ignore")


class JSONRPCRequest(JSONRPCMessage):
    """JSON-RPC 2.0 Request."""

    id: str | int | None = None
    method: str
    params: dict[str, Any] | list[Any] | None = None


class JSONRPCErrorData(BaseModel):
    """JSON-RPC 2.0 Error object."""

    code: int
    message: str
    data: Any | None = None
    model_config = ConfigDict(extra="ignore")


class JSONRPCResponse(JSONRPCMessage):
    """JSON-RPC 2.0 Response."""

    id: str | int | None = None
    result: Any | None = None
    error: JSONRPCErrorData | None = None


class ToolDefinition(BaseModel):
    """MCP Tool definition model conforming to MCP 2026-07-28."""

    name: str
    description: str
    inputSchema: dict[str, Any]
    model_config = ConfigDict(extra="ignore")


class ResourceDefinition(BaseModel):
    """MCP Resource definition model."""

    uri: str
    name: str
    description: str | None = None
    mimeType: str | None = "application/json"
    model_config = ConfigDict(extra="ignore")


def make_jsonrpc_error(
    req_id: str | int | None,
    code: int,
    message: str,
    data: Any | None = None,
) -> dict[str, Any]:
    """Helper to build a compliant JSON-RPC 2.0 error dict."""
    err_obj: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err_obj["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": err_obj,
    }


from app.mcp.constants import META_SERVER_INFO_KEY, SERVER_INFO


def make_jsonrpc_result(
    req_id: str | int | None,
    result: Any,
    *,
    server_info: dict[str, Any] | None = None,
    inject_meta_in_result: bool = True,
) -> dict[str, Any]:
    """Helper to build a compliant JSON-RPC 2.0 success dict with modern MCP _meta."""
    meta = {
        META_SERVER_INFO_KEY: server_info or SERVER_INFO,
    }
    if inject_meta_in_result and isinstance(result, dict):
        if "_meta" in result and isinstance(result["_meta"], dict):
            result["_meta"].update(meta)
        else:
            result["_meta"] = meta

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": result,
        "_meta": meta,
    }

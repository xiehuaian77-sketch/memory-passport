"""Standard MCP 2026-07-28 Server Package."""

from app.mcp.constants import MCP_PROTOCOL_VERSION
from app.mcp.router import router as mcp_standard_router
from app.mcp.server import mcp_server

__all__ = [
    "MCP_PROTOCOL_VERSION",
    "mcp_standard_router",
    "mcp_server",
]

"""
MCP (Model Context Protocol) server for MedInsight.

Exposes medical lab analysis tools via the MCP protocol.
"""
from __future__ import annotations

from app.mcp.server import create_mcp_server, MCPTool

__all__ = ["create_mcp_server", "MCPTool"]

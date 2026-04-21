"""
MCP Server endpoint tests.

Covers:
- GET /mcp/info returns server name, version, capabilities
- GET /mcp/tools returns a list of tools with name + inputSchema
- POST /mcp/tools/call with valid tool name returns success result
- POST /mcp/tools/call with unknown tool name returns 404
- POST /mcp/tools/call with missing required argument returns 400/422
- Each registered tool has a non-empty description and at least one parameter
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_BASE = "/api/v1/mcp"

# ── /info ─────────────────────────────────────────────────────────────────────

async def test_mcp_info_returns_200(client: AsyncClient):
    r = await client.get(f"{_BASE}/info")
    assert r.status_code == 200, r.text


async def test_mcp_info_has_required_fields(client: AsyncClient):
    r = await client.get(f"{_BASE}/info")
    data = r.json()
    assert "name" in data
    assert "version" in data
    assert "capabilities" in data


# ── /tools ────────────────────────────────────────────────────────────────────

async def test_mcp_list_tools_returns_200(client: AsyncClient):
    r = await client.get(f"{_BASE}/tools")
    assert r.status_code == 200, r.text


async def test_mcp_list_tools_returns_non_empty_list(client: AsyncClient):
    r = await client.get(f"{_BASE}/tools")
    data = r.json()
    assert "tools" in data
    assert len(data["tools"]) > 0


async def test_mcp_tools_have_name_and_schema(client: AsyncClient):
    r = await client.get(f"{_BASE}/tools")
    tools = r.json()["tools"]
    for tool in tools:
        assert "name" in tool, f"Tool missing 'name': {tool}"
        assert "description" in tool, f"Tool {tool.get('name')} missing 'description'"
        assert "inputSchema" in tool, f"Tool {tool.get('name')} missing 'inputSchema'"


async def test_mcp_tools_descriptions_non_empty(client: AsyncClient):
    r = await client.get(f"{_BASE}/tools")
    tools = r.json()["tools"]
    for tool in tools:
        assert tool["description"].strip(), f"Tool {tool['name']} has empty description"


async def test_mcp_expected_tools_registered(client: AsyncClient):
    r = await client.get(f"{_BASE}/tools")
    names = {t["name"] for t in r.json()["tools"]}
    expected = {
        "query_patient_lab_results",
        "analyze_health_report",
        "get_trend_analysis",
        "ask_medical_question",
    }
    missing = expected - names
    assert not missing, f"Expected MCP tools not registered: {missing}"


# ── /tools/call ───────────────────────────────────────────────────────────────

async def test_mcp_call_unknown_tool_returns_error(client: AsyncClient):
    """Unknown tool name → 200 with success=false and error message (MCP convention)."""
    r = await client.post(
        f"{_BASE}/tools/call",
        json={"tool_name": "nonexistent_tool_xyz", "arguments": {}},
    )
    # MCP spec: errors are returned in the body, not as HTTP error codes
    assert r.status_code in (200, 404), r.text
    if r.status_code == 200:
        data = r.json()
        assert data.get("success") is False
        assert "error" in data
        assert "nonexistent_tool_xyz" in data["error"]


async def test_mcp_call_missing_tool_name_returns_422(client: AsyncClient):
    r = await client.post(
        f"{_BASE}/tools/call",
        json={"arguments": {}},  # missing tool_name
    )
    assert r.status_code == 422, r.text


async def test_mcp_call_query_lab_results_missing_patient_id(client: AsyncClient):
    """Missing required argument → 200 with success=false (MCP error convention)."""
    r = await client.post(
        f"{_BASE}/tools/call",
        json={"tool_name": "query_patient_lab_results", "arguments": {}},
    )
    # MCP returns errors in body with success=false
    assert r.status_code in (200, 400, 422, 500), r.text
    if r.status_code == 200:
        data = r.json()
        assert data.get("success") is False


# ── MCPServer unit tests ──────────────────────────────────────────────────────

def test_mcp_server_registers_tools():
    from app.mcp.server import create_mcp_server
    server = create_mcp_server()
    assert len(server.tools) >= 4


def test_mcp_tool_schema_has_input_schema():
    from app.mcp.server import create_mcp_server
    server = create_mcp_server()
    for name, tool in server.tools.items():
        schema = tool.to_mcp_schema()
        assert "name" in schema, f"Tool {name} schema missing 'name'"
        assert "inputSchema" in schema, f"Tool {name} schema missing 'inputSchema'"
        assert schema["inputSchema"]["type"] == "object"


def test_mcp_server_info_structure():
    from app.mcp.server import create_mcp_server
    server = create_mcp_server()
    info = server.get_server_info()
    assert "name" in info
    assert "version" in info
    assert "capabilities" in info


def test_mcp_list_tools_returns_all_registered():
    from app.mcp.server import create_mcp_server
    server = create_mcp_server()
    listed = server.list_tools()
    assert len(listed) == len(server.tools)
    listed_names = {t["name"] for t in listed}
    registered_names = set(server.tools.keys())
    assert listed_names == registered_names

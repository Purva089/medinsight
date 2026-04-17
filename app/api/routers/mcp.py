"""
MCP (Model Context Protocol) API router.

Exposes MCP-compatible endpoints for external AI systems to interact with MedInsight.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.mcp.server import create_mcp_server

log = get_logger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


# ── Request/Response Models ────────────────────────────────────────────────────

class MCPToolCallRequest(BaseModel):
    """Request to call an MCP tool."""
    tool_name: str = Field(..., description="Name of the tool to call")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class MCPToolCallResponse(BaseModel):
    """Response from an MCP tool call."""
    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None


class MCPListToolsResponse(BaseModel):
    """Response listing all available MCP tools."""
    tools: list[dict[str, Any]]
    count: int


class MCPServerInfoResponse(BaseModel):
    """MCP server information."""
    name: str
    version: str
    description: str
    protocol_version: str
    capabilities: dict[str, bool]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/info", response_model=MCPServerInfoResponse)
async def get_server_info() -> MCPServerInfoResponse:
    """
    Get MCP server information.
    
    Returns server name, version, and capabilities.
    """
    server = create_mcp_server()
    info = server.get_server_info()
    return MCPServerInfoResponse(**info)


@router.get("/tools", response_model=MCPListToolsResponse)
async def list_tools() -> MCPListToolsResponse:
    """
    List all available MCP tools.
    
    Returns tool names, descriptions, and parameter schemas.
    """
    server = create_mcp_server()
    tools = server.list_tools()
    
    log.info("mcp_list_tools", tool_count=len(tools))
    
    return MCPListToolsResponse(tools=tools, count=len(tools))


@router.post("/tools/call", response_model=MCPToolCallResponse)
async def call_tool(request: MCPToolCallRequest) -> MCPToolCallResponse:
    """
    Call an MCP tool.
    
    Execute a tool with the provided arguments and return the result.
    """
    server = create_mcp_server()
    
    log.info(
        "mcp_tool_call_request",
        tool=request.tool_name,
        arg_keys=list(request.arguments.keys()),
    )
    
    result = await server.call_tool(request.tool_name, request.arguments)
    
    if result.get("success"):
        return MCPToolCallResponse(success=True, result=result)
    else:
        return MCPToolCallResponse(
            success=False,
            error=result.get("error", "Unknown error"),
        )


# ── Individual Tool Endpoints (convenience) ────────────────────────────────────

class QueryLabResultsRequest(BaseModel):
    """Request to query lab results."""
    patient_id: str
    test_name: str | None = None
    status: str | None = None
    limit: int = 50


@router.post("/tools/query_lab_results")
async def query_lab_results(request: QueryLabResultsRequest) -> dict[str, Any]:
    """
    Query patient lab results.
    
    Convenience endpoint for the query_patient_lab_results MCP tool.
    """
    server = create_mcp_server()
    return await server.call_tool(
        "query_patient_lab_results",
        request.model_dump(exclude_none=True),
    )


class AnalyzeReportRequest(BaseModel):
    """Request to analyze a health report."""
    patient_id: str
    report_id: str | None = None
    focus_areas: str | None = None


@router.post("/tools/analyze_report")
async def analyze_report(request: AnalyzeReportRequest) -> dict[str, Any]:
    """
    Analyze a health report.
    
    Convenience endpoint for the analyze_health_report MCP tool.
    """
    server = create_mcp_server()
    return await server.call_tool(
        "analyze_health_report",
        request.model_dump(exclude_none=True),
    )


class GetTrendsRequest(BaseModel):
    """Request to get trend analysis."""
    patient_id: str
    test_names: str | None = None


@router.post("/tools/get_trends")
async def get_trends(request: GetTrendsRequest) -> dict[str, Any]:
    """
    Get trend analysis for lab tests.
    
    Convenience endpoint for the get_trend_analysis MCP tool.
    """
    server = create_mcp_server()
    return await server.call_tool(
        "get_trend_analysis",
        request.model_dump(exclude_none=True),
    )


class AskQuestionRequest(BaseModel):
    """Request to ask a medical question."""
    patient_id: str
    question: str


@router.post("/tools/ask_question")
async def ask_question(request: AskQuestionRequest) -> dict[str, Any]:
    """
    Ask a medical question.
    
    Convenience endpoint for the ask_medical_question MCP tool.
    """
    server = create_mcp_server()
    return await server.call_tool(
        "ask_medical_question",
        request.model_dump(),
    )


class GetReferencesRequest(BaseModel):
    """Request to get reference ranges."""
    test_names: str | None = None


@router.post("/tools/get_references")
async def get_references(request: GetReferencesRequest) -> dict[str, Any]:
    """
    Get lab test reference ranges.
    
    Convenience endpoint for the get_reference_ranges MCP tool.
    """
    server = create_mcp_server()
    return await server.call_tool(
        "get_reference_ranges",
        request.model_dump(exclude_none=True),
    )

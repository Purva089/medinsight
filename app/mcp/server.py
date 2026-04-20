"""
MCP Server implementation for MedInsight.

This module exposes key medical analysis functionality as MCP-compatible tools:
- query_patient_lab_results: Query lab results with filters
- analyze_health_report: Get AI analysis of uploaded reports  
- get_trend_analysis: Get trend data for specific lab tests
- ask_medical_question: Ask questions about patient health data

The MCP server can be started standalone or integrated with FastAPI.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.lab_result import LabResult
from app.models.lab_reference import LabReference
from app.models.patient import Patient
from app.models.uploaded_report import UploadedReport
from app.schemas.chat import TrendResult
from app.services.llm_service import LLMService

log = get_logger(__name__)


# ── MCP Tool Definition ────────────────────────────────────────────────────────

@dataclass
class MCPToolParameter:
    """MCP tool parameter definition."""
    name: str
    type: str
    description: str
    required: bool = True
    enum: list[str] | None = None


@dataclass
class MCPTool:
    """MCP tool definition following MCP protocol spec."""
    name: str
    description: str
    parameters: list[MCPToolParameter] = field(default_factory=list)
    handler: Callable[..., Awaitable[dict[str, Any]]] | None = None
    
    def to_mcp_schema(self) -> dict[str, Any]:
        """Convert to MCP-compatible JSON schema."""
        properties = {}
        required = []
        
        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop
            
            if param.required:
                required.append(param.name)
        
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required,
            }
        }


# ── MCP Server ─────────────────────────────────────────────────────────────────

class MCPServer:
    """
    MCP Server for MedInsight medical analysis.
    
    Implements the Model Context Protocol to expose medical analysis
    capabilities to external AI systems.
    """
    
    def __init__(self) -> None:
        self.tools: dict[str, MCPTool] = {}
        self._llm = LLMService()
        self._register_tools()
    
    def _register_tools(self) -> None:
        """Register all MCP tools."""
        
        # Tool 1: Query Patient Lab Results
        self.tools["query_patient_lab_results"] = MCPTool(
            name="query_patient_lab_results",
            description="Query laboratory test results for a patient. Can filter by test name, date range, and status (normal/abnormal).",
            parameters=[
                MCPToolParameter(
                    name="patient_id",
                    type="string",
                    description="The UUID of the patient",
                    required=True,
                ),
                MCPToolParameter(
                    name="test_name",
                    type="string",
                    description="Filter by specific test name (e.g., 'Hemoglobin', 'Glucose')",
                    required=False,
                ),
                MCPToolParameter(
                    name="status",
                    type="string",
                    description="Filter by result status",
                    required=False,
                    enum=["normal", "high", "low", "critical", "all"],
                ),
                MCPToolParameter(
                    name="limit",
                    type="integer",
                    description="Maximum number of results to return (default: 50)",
                    required=False,
                ),
            ],
            handler=self._handle_query_lab_results,
        )
        
        # Tool 2: Analyze Health Report
        self.tools["analyze_health_report"] = MCPTool(
            name="analyze_health_report",
            description="Get AI-powered analysis of a patient's uploaded health report, including abnormal values, recommendations, and health insights.",
            parameters=[
                MCPToolParameter(
                    name="patient_id",
                    type="string",
                    description="The UUID of the patient",
                    required=True,
                ),
                MCPToolParameter(
                    name="report_id",
                    type="string",
                    description="Specific report UUID to analyze (optional - uses latest if not provided)",
                    required=False,
                ),
                MCPToolParameter(
                    name="focus_areas",
                    type="string",
                    description="Comma-separated focus areas (e.g., 'diet,exercise,medications')",
                    required=False,
                ),
            ],
            handler=self._handle_analyze_report,
        )
        
        # Tool 3: Get Trend Analysis
        self.tools["get_trend_analysis"] = MCPTool(
            name="get_trend_analysis",
            description="Get trend analysis for specific lab tests over time, including direction, rate of change, and health implications.",
            parameters=[
                MCPToolParameter(
                    name="patient_id",
                    type="string",
                    description="The UUID of the patient",
                    required=True,
                ),
                MCPToolParameter(
                    name="test_names",
                    type="string",
                    description="Comma-separated list of test names to analyze (e.g., 'Hemoglobin,Glucose')",
                    required=False,
                ),
            ],
            handler=self._handle_get_trends,
        )
        
        # Tool 4: Ask Medical Question
        self.tools["ask_medical_question"] = MCPTool(
            name="ask_medical_question",
            description="Ask a natural language question about a patient's health data. The AI will analyze relevant lab results and provide medical insights.",
            parameters=[
                MCPToolParameter(
                    name="patient_id",
                    type="string",
                    description="The UUID of the patient",
                    required=True,
                ),
                MCPToolParameter(
                    name="question",
                    type="string",
                    description="The medical question to ask (e.g., 'What are the implications of my glucose levels?')",
                    required=True,
                ),
            ],
            handler=self._handle_ask_question,
        )
        
        # Tool 5: Get Reference Ranges
        self.tools["get_reference_ranges"] = MCPTool(
            name="get_reference_ranges",
            description="Get standard reference ranges for laboratory tests to understand normal vs abnormal values.",
            parameters=[
                MCPToolParameter(
                    name="test_names",
                    type="string",
                    description="Comma-separated test names (e.g., 'Hemoglobin,WBC,Platelets')",
                    required=False,
                ),
            ],
            handler=self._handle_get_references,
        )
    
    # ── Tool Handlers ───────────────────────────────────────────────────────────
    
    async def _handle_query_lab_results(
        self,
        patient_id: str,
        test_name: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Query patient lab results with filters."""
        log.info("mcp_query_lab_results", patient_id=patient_id, test_name=test_name, status=status)
        
        try:
            async with AsyncSessionLocal() as session:
                query = select(LabResult).where(
                    LabResult.patient_id == uuid.UUID(patient_id)
                )
                
                if test_name:
                    query = query.where(LabResult.test_name.ilike(f"%{test_name}%"))
                
                if status and status != "all":
                    query = query.where(LabResult.status == status)
                
                query = query.order_by(LabResult.report_date.desc()).limit(limit)
                
                results = (await session.execute(query)).scalars().all()
                
                return {
                    "success": True,
                    "patient_id": patient_id,
                    "count": len(results),
                    "results": [
                        {
                            "test_name": r.test_name,
                            "value": r.value,
                            "unit": r.unit,
                            "status": r.status,
                            "reference_low": r.reference_range_low,
                            "reference_high": r.reference_range_high,
                            "report_date": str(r.report_date),
                        }
                        for r in results
                    ],
                }
        except Exception as exc:
            log.error("mcp_query_lab_results_error", error=str(exc))
            return {"success": False, "error": str(exc)}
    
    async def _handle_analyze_report(
        self,
        patient_id: str,
        report_id: str | None = None,
        focus_areas: str | None = None,
    ) -> dict[str, Any]:
        """Analyze a patient's health report."""
        log.info("mcp_analyze_report", patient_id=patient_id, report_id=report_id)
        
        try:
            async with AsyncSessionLocal() as session:
                # Get report
                if report_id:
                    report = (await session.execute(
                        select(UploadedReport).where(
                            UploadedReport.report_id == uuid.UUID(report_id)
                        )
                    )).scalar_one_or_none()
                else:
                    report = (await session.execute(
                        select(UploadedReport)
                        .where(UploadedReport.patient_id == uuid.UUID(patient_id))
                        .order_by(UploadedReport.created_at.desc())
                        .limit(1)
                    )).scalar_one_or_none()
                
                if not report:
                    return {"success": False, "error": "No report found"}
                
                # Get lab results for report
                results = (await session.execute(
                    select(LabResult).where(LabResult.report_id == report.report_id)
                )).scalars().all()
                
                abnormal = [r for r in results if r.status in ("high", "low", "critical")]
                normal = [r for r in results if r.status == "normal"]
                
                # Build analysis
                analysis = {
                    "report_id": str(report.report_id),
                    "report_date": str(report.created_at.date()),
                    "total_tests": len(results),
                    "abnormal_count": len(abnormal),
                    "normal_count": len(normal),
                    "abnormal_tests": [
                        {
                            "test_name": r.test_name,
                            "value": r.value,
                            "unit": r.unit,
                            "status": r.status,
                            "reference": f"{r.reference_range_low}-{r.reference_range_high}",
                        }
                        for r in abnormal
                    ],
                    "summary": self._generate_report_summary(abnormal, normal),
                }
                
                # Add AI insights if requested
                if focus_areas or abnormal:
                    prompt = self._build_analysis_prompt(abnormal, normal, focus_areas)
                    try:
                        ai_analysis = await self._llm.call_reasoning(prompt, "report")
                        analysis["ai_insights"] = ai_analysis
                    except Exception as e:
                        analysis["ai_insights"] = f"AI analysis unavailable: {e}"
                
                return {"success": True, **analysis}
                
        except Exception as exc:
            log.error("mcp_analyze_report_error", error=str(exc))
            return {"success": False, "error": str(exc)}
    
    async def _handle_get_trends(
        self,
        patient_id: str,
        test_names: str | None = None,
    ) -> dict[str, Any]:
        """Get trend analysis for lab tests."""
        log.info("mcp_get_trends", patient_id=patient_id, test_names=test_names)
        
        try:
            async with AsyncSessionLocal() as session:
                # Get reference ranges
                ref_rows = (await session.execute(select(LabReference))).scalars().all()
                ref_map = {r.test_name: (r.range_low, r.range_high) for r in ref_rows}
                
                # Get test names to analyze
                if test_names:
                    names = [n.strip() for n in test_names.split(",")]
                else:
                    # Get all tests for patient
                    rows = await session.execute(
                        select(LabResult.test_name)
                        .where(LabResult.patient_id == uuid.UUID(patient_id))
                        .distinct()
                    )
                    names = [r[0] for r in rows.all()]
                
                trends = []
                for name in names:
                    # Get history for this test
                    history = (await session.execute(
                        select(LabResult)
                        .where(
                            LabResult.patient_id == uuid.UUID(patient_id),
                            LabResult.test_name == name,
                        )
                        .order_by(LabResult.report_date.asc())
                    )).scalars().all()
                    
                    if len(history) < 2:
                        continue
                    
                    first_val = history[0].value
                    last_val = history[-1].value
                    pct_change = ((last_val - first_val) / first_val * 100) if first_val else 0
                    
                    direction = "stable"
                    if pct_change > 5:
                        direction = "rising"
                    elif pct_change < -5:
                        direction = "falling"
                    
                    ref_low, ref_high = ref_map.get(name, (None, None))
                    
                    trends.append({
                        "test_name": name,
                        "data_points": len(history),
                        "first_value": first_val,
                        "latest_value": last_val,
                        "direction": direction,
                        "change_percent": round(pct_change, 2),
                        "reference_range": f"{ref_low}-{ref_high}" if ref_low else "N/A",
                        "first_date": str(history[0].report_date),
                        "latest_date": str(history[-1].report_date),
                    })
                
                return {
                    "success": True,
                    "patient_id": patient_id,
                    "trends_count": len(trends),
                    "trends": trends,
                }
                
        except Exception as exc:
            log.error("mcp_get_trends_error", error=str(exc))
            return {"success": False, "error": str(exc)}
    
    async def _handle_ask_question(
        self,
        patient_id: str,
        question: str,
    ) -> dict[str, Any]:
        """Answer a medical question about patient data."""
        log.info("mcp_ask_question", patient_id=patient_id, question=question[:100])
        
        try:
            # Import graph and invoke
            from app.agents.graph import compiled_graph
            from app.agents.state import MedInsightState
            
            async with AsyncSessionLocal() as session:
                # Get patient
                patient = (await session.execute(
                    select(Patient).where(Patient.patient_id == uuid.UUID(patient_id))
                )).scalar_one_or_none()
                
                if not patient:
                    return {"success": False, "error": "Patient not found"}
                
                # Get latest report tests
                report = (await session.execute(
                    select(UploadedReport)
                    .where(UploadedReport.patient_id == uuid.UUID(patient_id))
                    .order_by(UploadedReport.created_at.desc())
                    .limit(1)
                )).scalar_one_or_none()
                
                extracted_tests = []
                if report:
                    results = (await session.execute(
                        select(LabResult).where(LabResult.report_id == report.report_id)
                    )).scalars().all()
                    
                    extracted_tests = [
                        {
                            "test_name": r.test_name,
                            "value": r.value,
                            "unit": r.unit or "",
                            "reference_range_low": r.reference_range_low,
                            "reference_range_high": r.reference_range_high,
                            "status": r.status or "normal",
                        }
                        for r in results
                    ]
                
                # Build state
                initial_state: MedInsightState = {
                    "patient_id": patient_id,
                    "patient_profile": {
                        "patient_id": patient_id,
                        "name": patient.name,
                        "age": patient.age,
                        "gender": patient.gender,
                    },
                    "ltm_summary": "",
                    "stm_messages": [],
                    "current_question": question,
                    "intent": "general",
                    "request_id": str(uuid.uuid4()),
                    "current_report_id": str(report.report_id) if report else None,
                    "extracted_tests": extracted_tests,
                    "extraction_confidence": 0.8,
                    "rag_chunks": [],
                    "rag_context": "",
                    "disclaimer_required": True,
                    "needs_rag":   False,
                    "needs_sql":   False,
                    "needs_trend": False,
                    "needs_report_generation": False,
                    "trend_results": [],
                    "mentioned_tests": [], 
                    "sql_query_generated": None,
                    "sql_results": [],
                    "final_response": {},
                    "errors": [],
                    "a2a_messages": [],
                    "others_tests": [],
                }
                
                # Invoke graph
                final_state = await compiled_graph.ainvoke(initial_state)  # type: ignore[assignment]
                
                response = final_state.get("final_response", {})
                
                return {
                    "success": True,
                    "question": question,
                    "answer": response.get("direct_answer", "Unable to generate answer"),
                    "confidence": response.get("confidence", "low"),
                    "disclaimer": response.get("disclaimer", "This is not medical advice."),
                    "sources": response.get("sources", []),
                }
                
        except Exception as exc:
            log.error("mcp_ask_question_error", error=str(exc))
            return {"success": False, "error": str(exc)}
    
    async def _handle_get_references(
        self,
        test_names: str | None = None,
    ) -> dict[str, Any]:
        """Get reference ranges for lab tests."""
        log.info("mcp_get_references", test_names=test_names)
        
        try:
            async with AsyncSessionLocal() as session:
                query = select(LabReference)
                
                if test_names:
                    names = [n.strip() for n in test_names.split(",")]
                    query = query.where(LabReference.test_name.in_(names))
                
                refs = (await session.execute(query)).scalars().all()
                
                return {
                    "success": True,
                    "count": len(refs),
                    "references": [
                        {
                            "test_name": r.test_name,
                            "range_low": r.range_low,
                            "range_high": r.range_high,
                            "source_url": r.source_url,
                            "description": r.description,
                        }
                        for r in refs
                    ],
                }
                
        except Exception as exc:
            log.error("mcp_get_references_error", error=str(exc))
            return {"success": False, "error": str(exc)}
    
    # ── Helper Methods ──────────────────────────────────────────────────────────
    
    def _generate_report_summary(
        self,
        abnormal: list[LabResult],
        normal: list[LabResult],
    ) -> str:
        """Generate a text summary of the report."""
        if not abnormal:
            return f"All {len(normal)} tested values are within normal ranges."
        
        abnormal_names = ", ".join(r.test_name for r in abnormal[:3])
        if len(abnormal) > 3:
            abnormal_names += f" and {len(abnormal) - 3} more"
        
        return f"Found {len(abnormal)} abnormal value(s) ({abnormal_names}). {len(normal)} values are normal."
    
    def _build_analysis_prompt(
        self,
        abnormal: list[LabResult],
        normal: list[LabResult],
        focus_areas: str | None,
    ) -> str:
        """Build prompt for AI analysis."""
        prompt = "Analyze these lab results and provide medical insights:\n\n"
        
        if abnormal:
            prompt += "ABNORMAL VALUES:\n"
            for r in abnormal:
                prompt += f"- {r.test_name}: {r.value} {r.unit or ''} (ref: {r.reference_range_low}-{r.reference_range_high}) [{r.status}]\n"
        
        prompt += f"\nNORMAL VALUES: {len(normal)} tests within range\n"
        
        if focus_areas:
            prompt += f"\nFocus on: {focus_areas}\n"
        
        prompt += "\nProvide: 1) Key findings 2) Health implications 3) Recommendations"
        
        return prompt
    
    # ── MCP Protocol Methods ────────────────────────────────────────────────────
    
    def list_tools(self) -> list[dict[str, Any]]:
        """Return MCP-formatted tool list."""
        return [tool.to_mcp_schema() for tool in self.tools.values()]
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute an MCP tool."""
        if tool_name not in self.tools:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        
        tool = self.tools[tool_name]
        if not tool.handler:
            return {"success": False, "error": f"Tool {tool_name} has no handler"}
        
        log.info("mcp_tool_call", tool=tool_name, arguments=arguments)
        
        try:
            result = await tool.handler(**arguments)
            log.info("mcp_tool_result", tool=tool_name, success=result.get("success", False))
            return result
        except Exception as exc:
            log.error("mcp_tool_error", tool=tool_name, error=str(exc))
            return {"success": False, "error": str(exc)}
    
    def get_server_info(self) -> dict[str, Any]:
        """Return MCP server information."""
        return {
            "name": "medinsight-mcp",
            "version": "1.0.0",
            "description": "MedInsight Medical Analysis MCP Server",
            "protocol_version": "2024-11-05",
            "capabilities": {
                "tools": True,
                "resources": False,
                "prompts": False,
            },
        }


# ── Factory function ────────────────────────────────────────────────────────────

_mcp_server: MCPServer | None = None


def create_mcp_server() -> MCPServer:
    """Create or return singleton MCP server instance."""
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = MCPServer()
    return _mcp_server

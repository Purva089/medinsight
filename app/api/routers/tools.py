"""
Function/Tool Calling API Router.

Exposes LLM tool definitions and invocation endpoints for external clients
to use MedInsight's AI capabilities through structured function calls.

This implements the "Function Calling" pattern where:
1. External clients can discover available tools/functions
2. Clients can invoke tools with structured parameters
3. Tools execute with full AI capabilities and return structured results
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_patient, get_db, get_llm
from app.core.logging import get_logger
from app.models.lab_result import LabResult
from app.models.patient import Patient
from app.models.uploaded_report import UploadedReport
from app.services.llm_service import LLMService
from app.services.safeguards import get_safeguards

log = get_logger(__name__)

router = APIRouter(prefix="/tools", tags=["function-calling"])


# ── Tool Definitions ───────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "analyze_lab_report",
        "description": "Analyze a patient's lab report and provide medical insights, including abnormal values, health implications, and recommendations.",
        "parameters": {
            "type": "object",
            "properties": {
                "report_id": {
                    "type": "string",
                    "description": "UUID of the specific report to analyze (optional, uses latest if not provided)",
                },
                "focus": {
                    "type": "string",
                    "description": "Specific aspect to focus on (e.g., 'diet', 'exercise', 'medications', 'overall')",
                    "enum": ["diet", "exercise", "medications", "lifestyle", "overall"],
                },
                "detail_level": {
                    "type": "string",
                    "description": "Level of detail in the analysis",
                    "enum": ["brief", "standard", "comprehensive"],
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_health_recommendations",
        "description": "Get personalized health recommendations based on lab results and patient profile.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category of recommendations",
                    "enum": ["nutrition", "exercise", "lifestyle", "supplements", "general"],
                },
                "conditions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific health conditions to address (e.g., ['anemia', 'high_cholesterol'])",
                },
            },
            "required": ["category"],
        },
    },
    {
        "name": "interpret_lab_value",
        "description": "Get detailed interpretation of a specific lab test value.",
        "parameters": {
            "type": "object",
            "properties": {
                "test_name": {
                    "type": "string",
                    "description": "Name of the lab test (e.g., 'Hemoglobin', 'Glucose', 'TSH')",
                },
                "value": {
                    "type": "number",
                    "description": "The measured value",
                },
                "unit": {
                    "type": "string",
                    "description": "Unit of measurement (e.g., 'g/dL', 'mg/dL')",
                },
            },
            "required": ["test_name", "value"],
        },
    },
    {
        "name": "compare_reports",
        "description": "Compare two lab reports and identify changes over time.",
        "parameters": {
            "type": "object",
            "properties": {
                "report_id_1": {
                    "type": "string",
                    "description": "UUID of the first (older) report",
                },
                "report_id_2": {
                    "type": "string",
                    "description": "UUID of the second (newer) report",
                },
                "test_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific tests to compare (optional, compares all if not provided)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_trend_analysis",
        "description": "Get trend analysis for specific lab tests over time.",
        "parameters": {
            "type": "object",
            "properties": {
                "test_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lab tests to analyze (e.g., ['Hemoglobin', 'Glucose'])",
                },
                "time_range": {
                    "type": "string",
                    "description": "Time range for analysis",
                    "enum": ["3_months", "6_months", "1_year", "all"],
                },
            },
            "required": [],
        },
    },
    {
        "name": "ask_medical_question",
        "description": "Ask a natural language question about health, lab results, or medical topics.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The medical question to ask",
                },
                "context": {
                    "type": "string",
                    "description": "Additional context for the question",
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "get_reference_ranges",
        "description": "Get standard reference ranges for lab tests.",
        "parameters": {
            "type": "object",
            "properties": {
                "test_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lab tests to get reference ranges for",
                },
                "demographic": {
                    "type": "object",
                    "properties": {
                        "age": {"type": "integer"},
                        "gender": {"type": "string", "enum": ["male", "female"]},
                    },
                    "description": "Patient demographics for adjusted ranges",
                },
            },
            "required": [],
        },
    },
    {
        "name": "generate_report_summary",
        "description": "Generate a summary of lab results suitable for sharing with healthcare providers.",
        "parameters": {
            "type": "object",
            "properties": {
                "report_id": {
                    "type": "string",
                    "description": "UUID of the report to summarize",
                },
                "format": {
                    "type": "string",
                    "description": "Output format",
                    "enum": ["text", "markdown", "structured"],
                },
                "include_recommendations": {
                    "type": "boolean",
                    "description": "Whether to include AI recommendations",
                },
            },
            "required": [],
        },
    },
]


# ── Request/Response Models ────────────────────────────────────────────────────

class ToolCallRequest(BaseModel):
    """Request to call a tool/function."""
    name: str = Field(..., description="Name of the tool to call")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class ToolCallResponse(BaseModel):
    """Response from a tool call."""
    tool_name: str
    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None
    execution_time_ms: int
    disclaimer: str = "This is not medical advice. Consult a qualified healthcare professional."


class ToolListResponse(BaseModel):
    """List of available tools."""
    tools: list[dict[str, Any]]
    count: int
    version: str = "1.0"


class ToolDefinition(BaseModel):
    """Single tool definition."""
    name: str
    description: str
    parameters: dict[str, Any]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", response_model=ToolListResponse)
async def list_available_tools() -> ToolListResponse:
    """
    List all available tools/functions.
    
    Returns tool names, descriptions, and parameter schemas that can be
    used for function calling with AI systems.
    """
    return ToolListResponse(
        tools=TOOL_DEFINITIONS,
        count=len(TOOL_DEFINITIONS),
    )


@router.get("/{tool_name}", response_model=ToolDefinition)
async def get_tool_definition(tool_name: str) -> ToolDefinition:
    """
    Get definition for a specific tool.
    
    Returns the tool's description and parameter schema.
    """
    for tool in TOOL_DEFINITIONS:
        if tool["name"] == tool_name:
            return ToolDefinition(**tool)
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Tool '{tool_name}' not found",
    )


@router.post("/call", response_model=ToolCallResponse)
async def call_tool(
    request: ToolCallRequest,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
    llm: LLMService = Depends(get_llm),
) -> ToolCallResponse:
    """
    Call a tool/function with the provided arguments.
    
    Executes the tool and returns structured results.
    """
    import time
    start_time = time.perf_counter()
    
    log.info(
        "tool_call_request",
        tool=request.name,
        patient_id=str(patient.patient_id),
        arguments=list(request.arguments.keys()),
    )
    
    try:
        result = await _execute_tool(
            request.name,
            request.arguments,
            patient,
            db,
            llm,
        )
        
        execution_time = int((time.perf_counter() - start_time) * 1000)
        
        return ToolCallResponse(
            tool_name=request.name,
            success=True,
            result=result,
            execution_time_ms=execution_time,
        )
    
    except ValueError as exc:
        execution_time = int((time.perf_counter() - start_time) * 1000)
        return ToolCallResponse(
            tool_name=request.name,
            success=False,
            error=str(exc),
            execution_time_ms=execution_time,
        )
    
    except Exception as exc:
        execution_time = int((time.perf_counter() - start_time) * 1000)
        log.error("tool_call_error", tool=request.name, error=str(exc))
        return ToolCallResponse(
            tool_name=request.name,
            success=False,
            error=f"Tool execution failed: {str(exc)[:200]}",
            execution_time_ms=execution_time,
        )


# ── Individual Tool Execution Endpoints ────────────────────────────────────────

@router.post("/analyze_lab_report")
async def tool_analyze_lab_report(
    report_id: str | None = None,
    focus: str = "overall",
    detail_level: str = "standard",
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
    llm: LLMService = Depends(get_llm),
) -> dict[str, Any]:
    """
    Analyze a lab report with AI insights.
    """
    return await _execute_tool(
        "analyze_lab_report",
        {"report_id": report_id, "focus": focus, "detail_level": detail_level},
        patient,
        db,
        llm,
    )


@router.post("/interpret_lab_value")
async def tool_interpret_lab_value(
    test_name: str,
    value: float,
    unit: str | None = None,
    patient: Patient = Depends(get_current_patient),
    llm: LLMService = Depends(get_llm),
) -> dict[str, Any]:
    """
    Get interpretation of a specific lab value.
    """
    return await _execute_tool(
        "interpret_lab_value",
        {"test_name": test_name, "value": value, "unit": unit},
        patient,
        None,
        llm,
    )


@router.post("/ask_medical_question")
async def tool_ask_medical_question(
    question: str,
    context: str | None = None,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
    llm: LLMService = Depends(get_llm),
) -> dict[str, Any]:
    """
    Ask a natural language medical question.
    """
    return await _execute_tool(
        "ask_medical_question",
        {"question": question, "context": context},
        patient,
        db,
        llm,
    )


# ── Tool Execution Logic ───────────────────────────────────────────────────────

async def _execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    patient: Patient,
    db: AsyncSession | None,
    llm: LLMService,
) -> dict[str, Any]:
    """Execute a tool and return results."""
    
    # Check if tool exists
    tool_names = [t["name"] for t in TOOL_DEFINITIONS]
    if tool_name not in tool_names:
        raise ValueError(f"Unknown tool: {tool_name}")
    
    # Route to appropriate handler
    handlers = {
        "analyze_lab_report": _handle_analyze_lab_report,
        "get_health_recommendations": _handle_get_recommendations,
        "interpret_lab_value": _handle_interpret_lab_value,
        "compare_reports": _handle_compare_reports,
        "get_trend_analysis": _handle_get_trend_analysis,
        "ask_medical_question": _handle_ask_medical_question,
        "get_reference_ranges": _handle_get_reference_ranges,
        "generate_report_summary": _handle_generate_report_summary,
    }
    
    handler = handlers.get(tool_name)
    if not handler:
        raise ValueError(f"Tool '{tool_name}' has no handler")
    
    return await handler(arguments, patient, db, llm)


async def _handle_analyze_lab_report(
    args: dict[str, Any],
    patient: Patient,
    db: AsyncSession,
    llm: LLMService,
) -> dict[str, Any]:
    """Handle analyze_lab_report tool."""
    report_id = args.get("report_id")
    focus = args.get("focus", "overall")
    detail_level = args.get("detail_level", "standard")
    
    # Get report
    if report_id:
        report = (await db.execute(
            select(UploadedReport).where(UploadedReport.report_id == uuid.UUID(report_id))
        )).scalar_one_or_none()
    else:
        report = (await db.execute(
            select(UploadedReport)
            .where(UploadedReport.patient_id == patient.patient_id)
            .order_by(UploadedReport.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()
    
    if not report:
        return {"error": "No report found", "success": False}
    
    # Get lab results
    results = (await db.execute(
        select(LabResult).where(LabResult.report_id == report.report_id)
    )).scalars().all()
    
    abnormal = [r for r in results if r.status in ("high", "low", "critical")]
    normal = [r for r in results if r.status == "normal"]
    
    # Build analysis prompt
    prompt = f"""Analyze these lab results for a {patient.age}-year-old {patient.gender} patient.
Focus area: {focus}
Detail level: {detail_level}

ABNORMAL VALUES:
{chr(10).join(f"- {r.test_name}: {r.value} {r.unit or ''} (ref: {r.reference_range_low}-{r.reference_range_high}) [{r.status}]" for r in abnormal) or "None"}

NORMAL VALUES: {len(normal)} tests within normal range

Provide a {detail_level} analysis focusing on {focus}. Include:
1. Key findings
2. Health implications  
3. Specific recommendations for {focus}
"""
    
    try:
        analysis = await llm.call_reasoning(prompt, "report")
    except Exception as e:
        analysis = f"AI analysis unavailable: {e}"
    
    return {
        "report_id": str(report.report_id),
        "report_date": str(report.created_at.date()),
        "total_tests": len(results),
        "abnormal_count": len(abnormal),
        "normal_count": len(normal),
        "focus": focus,
        "detail_level": detail_level,
        "abnormal_tests": [
            {
                "test_name": r.test_name,
                "value": r.value,
                "unit": r.unit,
                "status": r.status,
            }
            for r in abnormal
        ],
        "analysis": analysis,
    }


async def _handle_get_recommendations(
    args: dict[str, Any],
    patient: Patient,
    db: AsyncSession,
    llm: LLMService,
) -> dict[str, Any]:
    """Handle get_health_recommendations tool."""
    category = args.get("category", "general")
    conditions = args.get("conditions", [])
    
    prompt = f"""Provide {category} recommendations for a {patient.age}-year-old {patient.gender} patient.
{"Specific conditions to address: " + ", ".join(conditions) if conditions else "General health maintenance."}

Provide specific, actionable recommendations. Format as a numbered list.
"""
    
    try:
        recommendations = await llm.call_reasoning(prompt, "report")
    except Exception as e:
        recommendations = f"Unable to generate recommendations: {e}"
    
    return {
        "category": category,
        "conditions": conditions,
        "recommendations": recommendations,
    }


async def _handle_interpret_lab_value(
    args: dict[str, Any],
    patient: Patient,
    db: AsyncSession | None,
    llm: LLMService,
) -> dict[str, Any]:
    """Handle interpret_lab_value tool."""
    test_name = args["test_name"]
    value = args["value"]
    unit = args.get("unit", "")
    
    prompt = f"""Interpret this lab value for a {patient.age}-year-old {patient.gender} patient:
Test: {test_name}
Value: {value} {unit}

Provide:
1. What this test measures
2. Whether this value is normal, high, or low
3. Potential implications
4. Recommended follow-up actions
"""
    
    try:
        interpretation = await llm.call_reasoning(prompt, "report")
    except Exception as e:
        interpretation = f"Unable to interpret: {e}"
    
    return {
        "test_name": test_name,
        "value": value,
        "unit": unit,
        "interpretation": interpretation,
    }


async def _handle_compare_reports(
    args: dict[str, Any],
    patient: Patient,
    db: AsyncSession,
    llm: LLMService,
) -> dict[str, Any]:
    """Handle compare_reports tool."""
    report_id_1 = args.get("report_id_1")
    report_id_2 = args.get("report_id_2")
    test_names = args.get("test_names")
    
    # Get two most recent reports if not specified
    if not report_id_1 or not report_id_2:
        reports = (await db.execute(
            select(UploadedReport)
            .where(UploadedReport.patient_id == patient.patient_id)
            .order_by(UploadedReport.created_at.desc())
            .limit(2)
        )).scalars().all()
        
        if len(reports) < 2:
            return {"error": "Need at least 2 reports to compare", "success": False}
        
        report_id_2 = reports[0].report_id
        report_id_1 = reports[1].report_id
    
    # Get results from both reports
    results_1 = (await db.execute(
        select(LabResult).where(LabResult.report_id == uuid.UUID(str(report_id_1)))
    )).scalars().all()
    
    results_2 = (await db.execute(
        select(LabResult).where(LabResult.report_id == uuid.UUID(str(report_id_2)))
    )).scalars().all()
    
    # Compare
    comparison = []
    results_1_dict = {r.test_name: r for r in results_1}
    results_2_dict = {r.test_name: r for r in results_2}
    
    all_tests = set(results_1_dict.keys()) | set(results_2_dict.keys())
    if test_names:
        all_tests = all_tests & set(test_names)
    
    for test in all_tests:
        r1 = results_1_dict.get(test)
        r2 = results_2_dict.get(test)
        
        if r1 and r2:
            change = r2.value - r1.value
            pct_change = (change / r1.value * 100) if r1.value else 0
            comparison.append({
                "test_name": test,
                "old_value": r1.value,
                "new_value": r2.value,
                "change": round(change, 2),
                "change_percent": round(pct_change, 1),
                "old_status": r1.status,
                "new_status": r2.status,
                "improved": (r1.status in ("high", "low") and r2.status == "normal"),
                "worsened": (r1.status == "normal" and r2.status in ("high", "low")),
            })
    
    return {
        "report_1_id": str(report_id_1),
        "report_2_id": str(report_id_2),
        "tests_compared": len(comparison),
        "comparison": comparison,
    }


async def _handle_get_trend_analysis(
    args: dict[str, Any],
    patient: Patient,
    db: AsyncSession,
    llm: LLMService,
) -> dict[str, Any]:
    """Handle get_trend_analysis tool."""
    test_names = args.get("test_names")
    time_range = args.get("time_range", "all")
    
    # Use the trend agent via A2A protocol
    from app.agents.a2a_protocol import request_trend_data
    from app.agents.state import MedInsightState
    
    # Build minimal state
    state: MedInsightState = {
        "patient_id": str(patient.patient_id),
        "patient_profile": {},
        "ltm_summary": "",
        "stm_messages": [],
        "current_question": "",
        "intent": "trend",
        "request_id": str(uuid.uuid4()),
        "current_report_id": None,
        "extracted_tests": [{"test_name": n} for n in test_names] if test_names else [],
        "extraction_confidence": 0.0,
        "rag_chunks": [],
        "rag_context": "",
        "others_tests": [],
        "disclaimer_required": False,
        "needs_rag": False,
        "needs_sql": False,
        "needs_trend": True,
        "trend_results": [],
        "sql_query_generated": None,
        "sql_results": [],
        "final_response": {},
        "errors": [],
        "a2a_messages": [],
    }
    
    trend_data = await request_trend_data(
        source_agent="tools_api",
        state=state,
        test_names=test_names,
    )
    
    return {
        "time_range": time_range,
        "trends": trend_data.get("trend_results", []),
        "trend_count": trend_data.get("trend_count", 0),
    }


async def _handle_ask_medical_question(
    args: dict[str, Any],
    patient: Patient,
    db: AsyncSession,
    llm: LLMService,
) -> dict[str, Any]:
    """Handle ask_medical_question tool."""
    question = args["question"]
    context = args.get("context", "")
    
    # Apply ethical safeguards
    safeguards = get_safeguards()
    check_result = safeguards.check_input(question)
    
    if not check_result.allowed:
        return {
            "question": question,
            "answer": safeguards.get_blocked_response(check_result),
            "blocked": True,
            "reason": check_result.reason,
        }
    
    prompt = f"""Answer this medical question for a {patient.age}-year-old {patient.gender} patient:

Question: {question}
{"Additional context: " + context if context else ""}

Provide a helpful, accurate answer while emphasizing the importance of consulting healthcare professionals.
"""
    
    try:
        answer = await llm.call_reasoning(prompt, "report")
    except Exception as e:
        answer = f"Unable to generate answer: {e}"
    
    response = {
        "question": question,
        "answer": answer,
        "blocked": False,
    }
    
    if check_result.warning:
        response["warning"] = check_result.warning
    
    return response


async def _handle_get_reference_ranges(
    args: dict[str, Any],
    patient: Patient,
    db: AsyncSession,
    llm: LLMService,
) -> dict[str, Any]:
    """Handle get_reference_ranges tool."""
    test_names = args.get("test_names", [])
    demographic = args.get("demographic", {})
    
    from app.models.lab_reference import LabReference
    
    query = select(LabReference)
    if test_names:
        query = query.where(LabReference.test_name.in_(test_names))
    
    refs = (await db.execute(query)).scalars().all()
    
    return {
        "test_count": len(refs),
        "demographic": demographic,
        "reference_ranges": [
            {
                "test_name": r.test_name,
                "range_low": r.range_low,
                "range_high": r.range_high,
                "unit": r.unit,
                "category": r.category,
            }
            for r in refs
        ],
    }


async def _handle_generate_report_summary(
    args: dict[str, Any],
    patient: Patient,
    db: AsyncSession,
    llm: LLMService,
) -> dict[str, Any]:
    """Handle generate_report_summary tool."""
    report_id = args.get("report_id")
    output_format = args.get("format", "text")
    include_recommendations = args.get("include_recommendations", True)
    
    # Get report
    if report_id:
        report = (await db.execute(
            select(UploadedReport).where(UploadedReport.report_id == uuid.UUID(report_id))
        )).scalar_one_or_none()
    else:
        report = (await db.execute(
            select(UploadedReport)
            .where(UploadedReport.patient_id == patient.patient_id)
            .order_by(UploadedReport.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()
    
    if not report:
        return {"error": "No report found", "success": False}
    
    # Get results
    results = (await db.execute(
        select(LabResult).where(LabResult.report_id == report.report_id)
    )).scalars().all()
    
    abnormal = [r for r in results if r.status in ("high", "low", "critical")]
    
    summary = {
        "report_id": str(report.report_id),
        "report_date": str(report.created_at.date()),
        "patient_info": {
            "name": patient.name,
            "age": patient.age,
            "gender": patient.gender,
        },
        "total_tests": len(results),
        "abnormal_count": len(abnormal),
        "abnormal_values": [
            {
                "test": r.test_name,
                "value": f"{r.value} {r.unit or ''}",
                "reference": f"{r.reference_range_low}-{r.reference_range_high}",
                "status": r.status,
            }
            for r in abnormal
        ],
    }
    
    if include_recommendations and abnormal:
        prompt = f"""Generate brief recommendations for these abnormal lab values:
{chr(10).join(f"- {r.test_name}: {r.value} [{r.status}]" for r in abnormal)}

Provide 3-5 concise recommendations.
"""
        try:
            summary["recommendations"] = await llm.call_reasoning(prompt, "report")
        except Exception:
            summary["recommendations"] = "Unable to generate recommendations"
    
    return summary

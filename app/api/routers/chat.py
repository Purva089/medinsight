"""
Chat router – ask endpoint with LangGraph graph invocation.

Main features:
- Question processing through multi-agent pipeline
- Short-term memory (STM) for session continuity
- Long-term memory (LTM) with patient summaries
- Audit logging for healthcare compliance
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import compiled_graph
from app.agents.state import MedInsightState
from app.api.dependencies import get_current_patient, get_db, get_llm
from app.core.prompts import PROMPT_LTM_SUMMARY
from app.core.logging import get_logger, audit_log, log_metric, log_performance
from app.models.consultation import Consultation
from app.models.patient import Patient
from app.models.patient_summary import PatientSummary
from app.models.lab_result import LabResult
from app.models.uploaded_report import UploadedReport
from app.schemas.chat import ReportResponse, TrendResult
from app.services.llm_service import LLMService

log = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# ── Short-term memory store (in-process) ─────────────────────────────────────
# Maps session_id (str) → list of recent MedInsightState dicts
_session_store: dict[str, list[dict[str, Any]]] = {}
_STM_MAX_TURNS = 10


# ── Request / response models ─────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None          # client supplies to continue a session
    report_id: str | None = None           # optional: context for a specific report


class AskResponse(BaseModel):
    session_id: str
    request_id: str
    response: ReportResponse
    trend_data: list[TrendResult] = Field(default_factory=list)
    pdf_data: dict | None = None  # PDF filename + base64 bytes for download


# ── LTM helpers ───────────────────────────────────────────────────────────────

async def _get_or_generate_ltm_summary(
    patient_id: uuid.UUID,
    db: AsyncSession,
    llm: LLMService,
) -> str:
    """
    Return the cached LTM summary, or regenerate it from the last 5 consultations
    if it is stale (older than the most recent consultation).
    """
    # Latest consultation timestamp for this patient
    latest_consult_ts: datetime | None = (
        await db.execute(
            select(func.max(Consultation.created_at)).where(
                Consultation.patient_id == patient_id
            )
        )
    ).scalar_one_or_none()

    summary_row = (
        await db.execute(
            select(PatientSummary).where(PatientSummary.patient_id == patient_id)
        )
    ).scalar_one_or_none()

    # Return cached if still fresh
    if (
        summary_row is not None
        and latest_consult_ts is not None
        and summary_row.generated_at >= latest_consult_ts
    ):
        return summary_row.summary_text

    # Build summary from last 5 consultations
    recent_consultations = (
        await db.execute(
            select(Consultation)
            .where(Consultation.patient_id == patient_id)
            .order_by(Consultation.created_at.desc())
            .limit(5)
        )
    ).scalars().all()

    if not recent_consultations:
        return ""

    history_text = "\n\n".join(
        f"Q: {c.question}\nA: {c.answer[:300]}" for c in reversed(recent_consultations)
    )

    try:
        prompt = PROMPT_LTM_SUMMARY.format(history=history_text)
    except KeyError:
        prompt = f"Summarise the following patient consultation history in 3-4 sentences for future context:\n\n{history_text}"

    try:
        summary_text = await llm.call_reasoning(prompt, "ltm_summary")
    except Exception as exc:
        log.warning("ltm_summary_generation_failed", error=str(exc))
        return ""

    now = datetime.now(timezone.utc)

    if summary_row is None:
        summary_row = PatientSummary(
            patient_id=patient_id,
            summary_text=summary_text,
            generated_at=now,
            updated_at=now,
        )
        db.add(summary_row)
    else:
        summary_row.summary_text = summary_text
        summary_row.generated_at = now
        summary_row.updated_at = now

    await db.commit()
    log.info("ltm_summary_regenerated", patient_id=str(patient_id))
    return summary_text


# ── Ask endpoint ──────────────────────────────────────────────────────────────

@router.post("/ask", response_model=AskResponse)
async def ask(
    body: AskRequest,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
    llm: LLMService = Depends(get_llm),
) -> AskResponse:
    """Send a question to the MedInsight agent graph."""
    session_id = body.session_id or str(uuid.uuid4())
    request_id = str(uuid.uuid4())

    structlog.contextvars.bind_contextvars(
        session_id=session_id, patient_id=str(patient.patient_id)
    )

    log.info(
        "chat_ask_received",
        patient_id=str(patient.patient_id),
        patient_name=patient.name,
        question_preview=body.question[:80],
        session_id=session_id,
        report_id=body.report_id,
    )

    # STM: load previous turns
    stm_messages = list(_session_store.get(session_id, []))
    log.debug(
        "chat_stm_loaded",
        session_id=session_id,
        stm_turns=len(stm_messages) // 2,
    )

    # LTM: get or regenerate summary
    ltm_summary = await _get_or_generate_ltm_summary(patient.patient_id, db, llm)
    log.debug(
        "chat_ltm_loaded",
        patient_id=str(patient.patient_id),
        ltm_summary_len=len(ltm_summary),
    )

    # Build patient profile dict
    patient_profile: dict[str, Any] = {
        "patient_id": str(patient.patient_id),
        "name": patient.name,
        "age": patient.age,
        "gender": patient.gender,
        "blood_type": patient.blood_type,
        "medical_condition": patient.medical_condition,
        "medication": patient.medication,
    }

    # Fetch Lab Results for the active report, or fall back to the latest uploaded report.
    extracted_tests: list[dict[str, Any]] = []
    extraction_confidence = 0.0
    active_report_id: str | None = body.report_id

    try:
        report_uuid: uuid.UUID | None = uuid.UUID(body.report_id) if body.report_id else None
        log.debug("chat_report_uuid_initial", report_uuid=str(report_uuid) if report_uuid else None)

        if report_uuid is None:
            latest_report = (
                await db.execute(
                    select(UploadedReport)
                    .where(UploadedReport.patient_id == patient.patient_id)
                    .order_by(UploadedReport.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            log.debug("chat_latest_report_lookup", found=latest_report is not None, report_id=str(latest_report.report_id) if latest_report else None)
            if latest_report is not None:
                report_uuid = latest_report.report_id
                active_report_id = str(latest_report.report_id)
                extraction_confidence = latest_report.extraction_confidence or 0.0

        log.debug("chat_report_uuid_final", report_uuid=str(report_uuid) if report_uuid else None)
        if report_uuid is not None:
            if body.report_id:
                report = (
                    await db.execute(
                        select(UploadedReport).where(UploadedReport.report_id == report_uuid)
                    )
                ).scalar_one_or_none()
                if report is not None:
                    extraction_confidence = report.extraction_confidence or 0.0

            results = (
                await db.execute(
                    select(LabResult)
                    .where(LabResult.report_id == report_uuid)
                    .order_by(LabResult.created_at.asc())
                )
            ).scalars().all()

            for r in results:
                extracted_tests.append({
                    "test_name": r.test_name,
                    "value": r.value,
                    "unit": r.unit or "",
                    "reference_range_low": r.reference_range_low,
                    "reference_range_high": r.reference_range_high,
                    "status": r.status or "normal"
                })

            log.info(
                "chat_fetched_report_tests",
                report_id=active_report_id,
                count=len(extracted_tests),
                used_fallback=not bool(body.report_id),
            )
    except Exception as e:
        log.error("failed_to_fetch_report_tests", error=str(e), report_id=body.report_id)

    # Build initial state
    initial_state: MedInsightState = {
        "patient_id": str(patient.patient_id),
        "patient_profile": patient_profile,
        "ltm_summary": ltm_summary,
        "stm_messages": stm_messages,
        "current_question": body.question,
        "intent": "general",
        "request_id": request_id,
        "current_report_id": active_report_id,
        "extracted_tests": extracted_tests,
        "extraction_confidence": extraction_confidence,
        "rag_chunks": [],
        "rag_context": "",
        "others_tests": [],
        "disclaimer_required": False,
        "needs_rag":   False,
        "needs_sql":   False,
        "needs_trend": False,
        "needs_report_generation": False,  # Required by MedInsightState
        "mentioned_tests": [],  # Required by MedInsightState
        "trend_results": [],
        "sql_query_generated": None,
        "sql_results": [],
        "final_response": {},
        "errors": [],
        "a2a_messages": [],  # A2A communication log
    }

    import time as _time
    log.info(
        "chat_graph_invoking",
        session_id=session_id,
        patient_id=str(patient.patient_id),
        question_preview=body.question[:80],
    )
    _t0 = _time.perf_counter()

    try:
        with log_performance(log, "langgraph_pipeline", warn_threshold_ms=30000):
            final_state: MedInsightState = await compiled_graph.ainvoke(initial_state)  # type: ignore[assignment]
    except Exception as exc:
        log.error(
            "graph_invocation_failed",
            session_id=session_id,
            error=str(exc),
            request_id=request_id,
            exc_info=True,
        )
        # Log error metric
        log_metric(
            "chat_error",
            value=1,
            unit="count",
            tags={"error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent pipeline failed. Please try again.",
        )

    _graph_ms = round((_time.perf_counter() - _t0) * 1000)
    
    # Log performance metric
    log_metric(
        "chat_pipeline_duration",
        value=_graph_ms,
        unit="ms",
        tags={"intent": final_state.get("intent", "unknown")},
    )
    
    log.info(
        "chat_graph_complete",
        session_id=session_id,
        patient_id=str(patient.patient_id),
        intent=final_state.get("intent"),
        graph_duration_ms=_graph_ms,
        errors=final_state.get("errors") or None,
    )

    # Parse final response
    raw_response = final_state.get("final_response", {})
    try:
        report_response = ReportResponse.model_validate(raw_response)
    except Exception:
        report_response = ReportResponse(
            direct_answer=raw_response.get("direct_answer", "Unable to generate a response."),
            guideline_context=raw_response.get("guideline_context", ""),
            trend_summary=raw_response.get("trend_summary", ""),
            watch_for=raw_response.get("watch_for", ""),
            sources=raw_response.get("sources", []),
            confidence=raw_response.get("confidence", "low"),
            intent_handled=raw_response.get("intent_handled", "general"),
        )

    # Parse trend results
    trend_data: list[TrendResult] = []
    for t in final_state.get("trend_results", []):
        try:
            trend_data.append(TrendResult.model_validate(t))
        except Exception:
            pass

    # Update STM (append current turn)
    stm_messages.append({"role": "user", "content": body.question})
    stm_messages.append({"role": "assistant", "content": report_response.direct_answer})
    _session_store[session_id] = stm_messages[-(_STM_MAX_TURNS * 2):]  # keep last N turns

    log.info(
        "chat_ask_complete",
        session_id=session_id,
        patient_id=str(patient.patient_id),
        intent=final_state.get("intent"),
        confidence=report_response.confidence,
        answer_len=len(report_response.direct_answer),
        trend_count=len(trend_data),
        errors=final_state.get("errors") or None,
        graph_duration_ms=_graph_ms,
    )

    # Audit log for healthcare compliance (HIPAA)
    audit_log(
        action="medical_query_processed",
        resource_type="chat",
        resource_id=request_id,
        user_id=str(patient.patient_id),
        details={
            "session_id": session_id,
            "intent": final_state.get("intent"),
            "question_length": len(body.question),
            "response_confidence": report_response.confidence,
            "duration_ms": _graph_ms,
        },
    )

    # Extract PDF data if present (for report generation)
    pdf_data = raw_response.get("pdf_data")
    
    return AskResponse(
        session_id=session_id,
        request_id=request_id,
        response=report_response,
        trend_data=trend_data,
        pdf_data=pdf_data,
    )

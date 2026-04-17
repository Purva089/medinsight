"""
Report agent -- synthesises all context into a final structured response.

Receives (from state):
    rag_context      : retrieved medical knowledge (supported tests only)
    others_tests     : tests with category="others" (no RAG data available)
    trend_results    : list[dict] from trend_node  (may be empty)
    sql_results      : list[dict] from text_to_sql_node  (may be empty)
    extracted_tests  : list[dict] parsed from the uploaded PDF
    patient_profile  : dict with patient demographics
    ltm_summary      : long-term memory summary from patient_summaries table
    current_question : the user's question

What it does:
    1. Runs ethical safeguard check -- blocks off-topic queries
    2. Builds a single LLM prompt that contains ALL context
    3. LLM returns a structured JSON response (ReportResponse shape)
    4. One self-heal retry if JSON parse fails
    5. Minimal plain-text fallback if self-heal also fails
    6. Appends safeguard warnings as plain text (not HTML injection)
    7. Saves consultation to DB
    8. Updates patient_summaries (LTM) with refreshed summary
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.agents.state import MedInsightState
from app.agents.a2a_protocol import get_a2a_hub
from app.core.database import AsyncSessionLocal
from app.core.prompts import PROMPT_REPORT, PROMPT_LTM_SUMMARY
from app.core.logging import get_logger
from app.models.consultation import Consultation
from app.models.patient_summary import PatientSummary
from app.schemas.chat import ReportResponse, compute_confidence
from app.services.llm_service import llm_service as _llm
from app.services.safeguards import get_safeguards, SafetyLevel
from sqlalchemy import select

log = get_logger(__name__)

_DISCLAIMER = "This is not medical advice. Consult a qualified healthcare professional."

_SELF_HEAL_PREFIX = (
    "The JSON you returned was invalid. Fix it and return ONLY valid JSON "
    'matching this schema: {"direct_answer":...,"guideline_context":...,'
    '"trend_summary":...,"watch_for":...,"sources":[...],'
    '"disclaimer":"...","confidence":"...","intent_handled":"..."}\n\n'
    "Bad JSON:\n"
)


# -- small helpers -------------------------------------------------------------

def _fmt_test_value(test: dict) -> str:
    value = test.get("value", "-")
    unit = test.get("unit", "") or ""
    return f"{value} {unit}".strip()


def _fmt_test_range(test: dict) -> str:
    low = test.get("reference_range_low")
    high = test.get("reference_range_high")
    unit = test.get("unit", "") or ""
    if low is None and high is None:
        return unit or "not provided"
    if low is None:
        return f"<= {high} {unit}".strip()
    if high is None:
        return f">= {low} {unit}".strip()
    return f"{low}-{high} {unit}".strip()


def _summarise_tests_for_prompt(extracted_tests: list[dict]) -> str:
    """Produce a compact text summary of extracted tests to include in the prompt."""
    if not extracted_tests:
        return "No extracted test data available."
    lines: list[str] = []
    for t in extracted_tests:
        name = t.get("test_name", "Unknown")
        value = _fmt_test_value(t)
        ref = _fmt_test_range(t)
        status = (t.get("status") or "unknown").lower()
        cat = t.get("category", "others")
        lines.append(f"  - {name} [{cat}]: {value} (ref {ref}, status: {status})")
    return "\n".join(lines)


def _summarise_others_tests(others_tests: list[dict]) -> str:
    """Build the notice block for unsupported-category tests."""
    if not others_tests:
        return ""
    lines = [
        "The following tests are outside our supported categories. "
        "Our knowledge base does not contain interpretation data for them. "
        "Please consult your doctor for guidance:\n"
    ]
    for t in others_tests:
        name = t.get("test_name", "Unknown")
        value = _fmt_test_value(t)
        lines.append(f"  - {name}: {value}")
    return "\n".join(lines)


def _parse_report_response(raw: str, confidence: str, intent: str) -> ReportResponse | None:
    """Parse LLM output into ReportResponse. Returns None on failure."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(ln for ln in lines if not ln.startswith("```")).strip()
    try:
        data = json.loads(cleaned)
        data["confidence"] = confidence           # Python computes, LLM does not
        data["disclaimer"] = _DISCLAIMER
        if not data.get("intent_handled"):
            data["intent_handled"] = intent
        return ReportResponse.model_validate(data)
    except Exception:
        return None


def _plain_fallback(
    *,
    question: str,
    intent: str,
    extracted_tests: list[dict],
    trend_summary: str,
    confidence: str,
) -> ReportResponse:
    """
    Minimal plain-text fallback used only when the LLM fails completely
    AND self-heal also fails.  No hardcoded medical advice.
    """
    test_lines = _summarise_tests_for_prompt(extracted_tests)
    direct_answer = (
        f"Unable to generate a full AI analysis at this time.\n\n"
        f"Your question: {question}\n\n"
        f"Extracted test data from your report:\n{test_lines}\n\n"
        "Please consult your healthcare provider for interpretation."
    )
    return ReportResponse(
        direct_answer=direct_answer,
        guideline_context="",
        trend_summary=trend_summary,
        watch_for="Consult your healthcare provider.",
        sources=[],
        disclaimer=_DISCLAIMER,
        confidence=confidence,
        intent_handled=intent,
    )


def _is_uuid(val: str) -> bool:
    try:
        uuid.UUID(val)
        return True
    except ValueError:
        return False


# -- main node -----------------------------------------------------------------

async def report_node(state: MedInsightState) -> MedInsightState:
    """
    Synthesise RAG, trend, SQL context and extracted tests into a final
    structured ReportResponse via LLM.

    Flow:
        1. Safeguard check  -- block off-topic queries
        2. Build single LLM prompt with ALL context
        3. Parse JSON response
        4. One self-heal retry on parse failure
        5. Plain-text fallback as last resort
        6. Append safeguard notices as plain text
        7. Save consultation to DB
    """
    patient_id = state["patient_id"]
    question = state["current_question"]
    intent = state.get("intent", "general")
    rag_chunks = state.get("rag_chunks", [])
    trend_results = state.get("trend_results", [])
    sql_results = state.get("sql_results", [])
    rag_context = state.get("rag_context", "")
    patient_profile = state.get("patient_profile", {})
    extracted_tests = state.get("extracted_tests", [])
    others_tests = state.get("others_tests", [])
    ltm_summary = state.get("ltm_summary", "")
    session_id = state.get("request_id", str(uuid.uuid4()))

    # -- 1. Safeguard check ----------------------------------------------------
    safeguards = get_safeguards()
    safeguard_result = safeguards.check_input(question)

    if not safeguard_result.allowed:
        log.info(
            "report_safeguard_blocked",
            patient_id=patient_id,
            category=safeguard_result.category.value,
            reason=safeguard_result.reason,
        )
        response = ReportResponse(
            direct_answer=safeguards.get_blocked_response(safeguard_result),
            guideline_context="",
            trend_summary="",
            watch_for="",
            sources=[],
            disclaimer=_DISCLAIMER,
            confidence="high",
            intent_handled="blocked",
        )
        state["final_response"] = response.model_dump()
        return state

    if safeguard_result.safety_level in (SafetyLevel.EMERGENCY, SafetyLevel.CAUTION):
        log.info(
            "report_safeguard_warning",
            patient_id=patient_id,
            safety_level=safeguard_result.safety_level.value,
            category=safeguard_result.category.value,
        )

    # -- 2. Compute confidence (Python only) -----------------------------------
    if not rag_chunks:
        state["disclaimer_required"] = True

    confidence = compute_confidence(rag_chunks, trend_results)

    trend_summary = (
        "\n".join(t.get("trend_description", "") for t in trend_results)
        if trend_results
        else "No trend data available."
    )

    # -- 3. Build LLM prompt ---------------------------------------------------
    others_notice = _summarise_others_tests(others_tests)
    prompt = PROMPT_REPORT.format(
        patient_name=patient_profile.get("name", "Patient"),
        patient_profile=json.dumps(patient_profile, default=str),
        ltm_summary=ltm_summary or "No prior consultation history.",
        extracted_tests=_summarise_tests_for_prompt(extracted_tests),
        rag_context=rag_context or "No medical guidelines retrieved.",
        trend_summary=trend_summary,
        sql_results=json.dumps(sql_results, default=str),
        question=question,
        others_notice=others_notice or "None.",
    )

    log.info(
        "report_agent_start",
        patient_id=patient_id,
        intent=intent,
        rag_chunks=len(rag_chunks),
        trend_results=len(trend_results),
        sql_results=len(sql_results),
        extracted_tests=len(extracted_tests),
        confidence=confidence,
        prompt_len=len(prompt),
    )

    # -- 4. LLM call + parse ---------------------------------------------------
    response: ReportResponse | None = None

    try:
        raw = await _llm.call_reasoning(prompt, max_tokens_key="report")
        response = _parse_report_response(raw, confidence, intent)

        if response is None:
            log.warning(
                "report_parse_failed_self_healing",
                patient_id=patient_id,
                raw_preview=raw[:200],
            )
            heal_raw = await _llm.call_reasoning(
                _SELF_HEAL_PREFIX + raw, max_tokens_key="report"
            )
            response = _parse_report_response(heal_raw, confidence, intent)
            if response is not None:
                log.info("report_self_heal_succeeded", patient_id=patient_id)

        if response is None:
            log.error("report_self_heal_failed", patient_id=patient_id)
            response = _plain_fallback(
                question=question,
                intent=intent,
                extracted_tests=extracted_tests,
                trend_summary=trend_summary,
                confidence=confidence,
            )
            state["errors"] = state.get("errors", []) + ["LLM failed; returned plain fallback."]

    except Exception as exc:
        error_msg = str(exc)
        log.error("report_llm_error", error=error_msg[:200])
        state["disclaimer_required"] = True
        is_rate_limit = "429" in error_msg or "rate limit" in error_msg.lower()
        response = _plain_fallback(
            question=question,
            intent=intent,
            extracted_tests=extracted_tests,
            trend_summary=trend_summary,
            confidence="low",
        )
        if is_rate_limit:
            response.direct_answer = (
                "AI service rate limit reached. Please try again in a few minutes.\n\n"
                + response.direct_answer
            )
            state["errors"] = state.get("errors", []) + ["LLM rate limit exceeded."]
        else:
            state["errors"] = state.get("errors", []) + [f"Report LLM error: {error_msg[:100]}"]

    # -- 5. Always enforce disclaimer ------------------------------------------
    response.disclaimer = _DISCLAIMER

    # -- 6. Append safeguard notices as plain text -----------------------------
    if safeguard_result.safety_level == SafetyLevel.EMERGENCY:
        response.direct_answer = (
            "EMERGENCY NOTICE: If you are experiencing a medical emergency, "
            "call emergency services (911) immediately. Do not rely on this AI.\n\n"
            + response.direct_answer
        )

    if safeguard_result.warning:
        response.direct_answer = (
            f"NOTICE: {safeguard_result.warning}\n\n" + response.direct_answer
        )

    state["final_response"] = response.model_dump()

    # Store A2A message log for auditing
    a2a_hub = get_a2a_hub()
    state["a2a_messages"] = a2a_hub.get_message_log()

    # -- 7. Persist consultation + update LTM ──────────────────────────────────
    try:
        async with AsyncSessionLocal() as db_session:
            # Save consultation record
            consult = Consultation(
                patient_id=uuid.UUID(patient_id),
                session_id=(
                    uuid.UUID(session_id) if _is_uuid(session_id) else uuid.uuid4()
                ),
                question=question,
                answer=response.direct_answer,
                intent_handled=intent,
                confidence_level=response.confidence,
                sources_cited=[],
                trend_data={"trend_results": trend_results} if trend_results else None,
                sql_query_generated=state.get("sql_query_generated"),
            )
            db_session.add(consult)
            await db_session.flush()

            # Update (or create) LTM summary in patient_summaries
            now = datetime.now(timezone.utc)
            summary_row = (
                await db_session.execute(
                    select(PatientSummary).where(
                        PatientSummary.patient_id == uuid.UUID(patient_id)
                    )
                )
            ).scalar_one_or_none()

            # Build a short new summary from the current interaction
            new_context = (
                f"Q: {question[:200]}\nA: {response.direct_answer[:300]}"
            )
            ltm_prompt = PROMPT_LTM_SUMMARY.format(history=new_context)
            try:
                new_summary = await _llm.call_reasoning(ltm_prompt, "ltm_summary")
            except Exception:
                new_summary = (
                    f"Patient asked about {question[:100]}. "
                    f"Response confidence: {response.confidence}."
                )

            if summary_row is None:
                summary_row = PatientSummary(
                    patient_id=uuid.UUID(patient_id),
                    summary_text=new_summary,
                    generated_at=now,
                    updated_at=now,
                )
                db_session.add(summary_row)
            else:
                summary_row.summary_text = new_summary
                summary_row.generated_at = now
                summary_row.updated_at = now

            await db_session.commit()
            log.info(
                "consultation_saved",
                patient_id=patient_id,
                session_id=session_id,
                intent=intent,
                confidence=response.confidence,
                ltm_updated=True,
            )
    except Exception as exc:
        log.error("consultation_save_error", error=str(exc)[:200], exc_info=True)
        state["errors"] = state.get("errors", []) + [f"DB save error: {exc!s:.100}"]

    log.info(
        "report_complete",
        patient_id=patient_id,
        confidence=response.confidence,
        intent=intent,
        answer_len=len(response.direct_answer),
        has_guideline_context=bool(response.guideline_context),
        sources_count=len(response.sources),
    )
    return state

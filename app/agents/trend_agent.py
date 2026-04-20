"""
Trend agent — pure Python + SQL, no LLM calls.

Computes TrendResult for each lab test in the patient's history.

Direction logic:
  - "improving"         : value moving toward the normal reference range
  - "worsening"         : value moving away from the normal reference range
  - "stable"            : < 5% change
  - "insufficient_data" : fewer than 2 data points
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.agents.state import MedInsightState
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.lab_reference import LabReference
from app.models.lab_result import LabResult
from app.schemas.chat import TrendResult

log = get_logger(__name__)


def _compute_direction(
    first_val: float,
    last_val: float,
    ref_low: float | None,
    ref_high: float | None,
    pct_diff: float,
) -> str:
    """
    Return "improving", "worsening", or "stable" based on movement
    relative to the reference range.

    - "stable"    : abs(pct_diff) <= 5
    - "improving" : value moved closer to the reference range
    - "worsening" : value moved further from the reference range
    """
    if abs(pct_diff) <= 5:
        return "stable"

    if ref_low is None or ref_high is None:
        # No reference range — use raw direction as proxy
        return "stable"   # can't determine without a target

    ref_mid = (ref_low + ref_high) / 2

    dist_first = abs(first_val - ref_mid)
    dist_last  = abs(last_val  - ref_mid)

    if dist_last < dist_first:
        return "improving"
    return "worsening"


def _significant_change(history) -> bool:
    """True if any two consecutive readings differ by > 20%."""
    for i in range(1, len(history)):
        prev = history[i - 1].value
        curr = history[i].value
        if prev and abs(curr - prev) / prev > 0.20:
            return True
    return False


async def trend_node(state: MedInsightState) -> MedInsightState:
    """
    Compute trends for lab tests.

    1. Identify tests from state["mentioned_tests"] (from question), then extracted_tests (from PDF), then all tests.
    2. For each test: load history, compute stats, build TrendResult.
    3. Cache per (patient, test, latest_date).
    """
    patient_id = state["patient_id"]
    
    # Priority 1: Tests mentioned in question (for specific queries like "Show hemoglobin trend")
    mentioned_tests = state.get("mentioned_tests", [])
    
    # Priority 2: Tests extracted from uploaded PDF
    extracted = state.get("extracted_tests", [])
    extracted_test_names = [t.get("test_name", "") for t in extracted if t.get("test_name")]
    
    # Determine which tests to analyze
    if mentioned_tests:
        # User asked about specific test(s) - ONLY analyze those
        test_names = list(set(mentioned_tests))  # Deduplicate
    elif extracted_test_names:
        # No specific tests mentioned - analyze up to 4 tests from most recent report
        test_names = list(set(extracted_test_names))[:4]  # Deduplicate and limit
    else:
        # Fallback: will query all patient tests
        test_names = []

    trend_results: list[dict] = []

    log.info(
        "trend_node_start",
        patient_id=patient_id,
        requested_tests=test_names or "<all>",
        source="mentioned" if mentioned_tests else ("extracted" if extracted_test_names else "all"),
    )

    try:
        async with AsyncSessionLocal() as session:
            # Load reference ranges once
            ref_rows = (await session.execute(select(LabReference))).scalars().all()
            ref_map: dict[str, tuple[float | None, float | None]] = {
                r.test_name: (r.range_low, r.range_high) for r in ref_rows
            }
            log.debug("trend_reference_ranges_loaded", count=len(ref_map))

            # If no test names extracted, query all tests for patient
            if not test_names:
                rows_q = await session.execute(
                    select(LabResult.test_name)
                    .where(LabResult.patient_id == patient_id)
                    .distinct()
                )
                test_names = [r[0] for r in rows_q.all()]
                log.debug("trend_discovered_tests", tests=test_names)

            for test_name in test_names:
                # Check trend cache first
                cache_key_base = f"{patient_id}:{test_name}"
                # We'll compute latest_date below; pre-check with a temporary key
                history_q = await session.execute(
                    select(LabResult)
                    .where(
                        LabResult.patient_id == patient_id,
                        LabResult.test_name == test_name,
                    )
                    .order_by(LabResult.report_date.asc())
                )
                history = history_q.scalars().all()

                if len(history) < 2:
                    log.debug(
                        "trend_insufficient_data",
                        test_name=test_name,
                        data_points=len(history),
                    )
                    continue

                latest_date = str(history[-1].report_date)

                data_points = [
                    {"date": str(r.report_date), "value": r.value}
                    for r in history
                ]

                first_val = history[0].value
                last_val = history[-1].value

                # ── direction ─────────────────────────────────────────────────
                pct_diff = (last_val - first_val) / first_val * 100 if first_val else 0.0
                if pct_diff > 5:
                    direction = "rising"
                elif pct_diff < -5:
                    direction = "falling"
                else:
                    direction = "stable"

                # ── months elapsed ────────────────────────────────────────────
                d0: date = history[0].report_date
                d1: date = history[-1].report_date
                months = max(((d1.year - d0.year) * 12 + d1.month - d0.month), 1)
                delta_per_month = (last_val - first_val) / months

                # ── velocity concern ──────────────────────────────────────────
                ref_low, ref_high = ref_map.get(test_name, (None, None))
                velocity_concern = False
                if ref_low is not None and ref_high is not None and (ref_high - ref_low) > 0:
                    velocity_concern = abs(delta_per_month) > 0.20 * (ref_high - ref_low)

                # ── threshold crossed ─────────────────────────────────────────
                threshold_crossed = False
                if ref_low is not None and ref_high is not None:
                    first_in = ref_low <= first_val <= ref_high
                    last_in = ref_low <= last_val <= ref_high
                    threshold_crossed = first_in != last_in

                # ── trend description ─────────────────────────────────────────
                sig_change = _significant_change(history)
                
                # Build concise, informative trend description
                status_emoji = "📈" if direction == "rising" else "📉" if direction == "falling" else "➡️"
                trend_description = (
                    f"{status_emoji} {test_name}: {direction} by {abs(pct_diff):.1f}% "
                    f"over {months} month{'s' if months != 1 else ''} "
                    f"(from {first_val:.1f} to {last_val:.1f})."
                )
                
                # Check if latest value is currently outside reference range (regardless of crossing)
                if ref_low is not None and ref_high is not None:
                    if last_val < ref_low:
                        trend_description += f" ⚠️ Currently LOW (your value: {last_val}, normal: {ref_low}-{ref_high})."
                    elif last_val > ref_high:
                        trend_description += f" ⚠️ Currently HIGH (your value: {last_val}, normal: {ref_low}-{ref_high})."
                    elif velocity_concern and sig_change:
                        trend_description += " Rapid change detected - monitor closely."

                trend = TrendResult(
                    test_name=test_name,
                    data_points=data_points,
                    direction=direction,
                    change_percent=round(pct_diff, 2),
                    delta_per_month=round(delta_per_month, 4),
                    velocity_concern=velocity_concern,
                    threshold_crossed=threshold_crossed,
                    significant_change=sig_change,
                    trend_description=trend_description,
                    reference_low=ref_low,
                    reference_high=ref_high,
                )
                trend_dict = trend.model_dump()
                trend_results.append(trend_dict)

                log.debug(
                    "trend_test_computed",
                    test_name=test_name,
                    direction=direction,
                    change_percent=round(pct_diff, 2),
                    data_points=len(history),
                    velocity_concern=velocity_concern,
                    threshold_crossed=threshold_crossed,
                )

    except Exception as exc:
        log.error("trend_node_error", error=str(exc)[:200], exc_info=True)
        state["errors"] = state.get("errors", []) + [f"Trend error: {exc!s:.100}"]

    state["trend_results"] = trend_results
    
    # Trend agent's job is done - synthesis_agent will format the response
    log.info(
        "trend_agent_complete",
        patient_id=patient_id,
        test_count=len(trend_results),
        tests=[t["test_name"] for t in trend_results],
    )
    return state

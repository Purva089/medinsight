"""
Tests for the trend agent node (app/agents/trend_agent.py).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import MedInsightState
from app.agents.trend_agent import trend_node
from app.models.lab_reference import LabReference
from app.models.lab_result import LabResult


def _base_state(patient_id: str, test_names: list[str] | None = None) -> MedInsightState:
    extracted = [{"test_name": n} for n in (test_names or [])]
    return {
        "patient_id": patient_id,
        "patient_profile": {},
        "ltm_summary": "",
        "stm_messages": [],
        "current_question": "Show my trends",
        "intent": "trend",
        "request_id": "req-trend-test",
        "current_report_id": None,
        "extracted_tests": extracted,
        "extraction_confidence": 0.0,
        "rag_chunks": [],
        "rag_context": "",
        "disclaimer_required": False,
        "trend_results": [],
        "sql_query_generated": None,
        "sql_results": [],
        "final_response": {},
        "response_cached": False,
        "parallel_complete": False,
        "errors": [],
    }


async def _insert_results(
    db: AsyncSession,
    patient_id: str,
    test_name: str,
    rows: list[tuple[date, float]],
    report_id: uuid.UUID | None = None,
) -> None:
    """Helper: insert LabResult rows for a patient/test."""
    for report_date, value in rows:
        lr = LabResult(
            patient_id=uuid.UUID(patient_id),
            report_id=report_id,
            test_name=test_name,
            value=value,
            unit="units",
            report_date=report_date,
        )
        db.add(lr)
    await db.commit()


async def _cleanup(db: AsyncSession, patient_id: str, test_name: str) -> None:
    await db.execute(
        delete(LabResult).where(
            LabResult.patient_id == uuid.UUID(patient_id),
            LabResult.test_name == test_name,
        )
    )
    await db.commit()


# ── test_direction_rising ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_direction_rising(test_patient: str, db_session: AsyncSession, mock_cache):
    test_name = f"TEST_RISE_{uuid.uuid4().hex[:6]}"
    today = date.today()
    d0, d1 = today - timedelta(days=60), today

    await _insert_results(db_session, test_patient, test_name, [(d0, 1.0), (d1, 2.0)])

    result = await trend_node(_base_state(test_patient, [test_name]))

    assert result["trend_results"], "Expected at least one trend result"
    tr = result["trend_results"][0]
    assert tr["direction"] == "rising", f"Expected 'rising', got {tr['direction']}"

    await _cleanup(db_session, test_patient, test_name)


# ── test_threshold_crossed ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_threshold_crossed(test_patient: str, db_session: AsyncSession, mock_cache):
    test_name = f"TEST_THRESH_{uuid.uuid4().hex[:6]}"
    today = date.today()
    d0, d1 = today - timedelta(days=30), today

    # Ensure a reference range exists for this test name
    ref = LabReference(test_name=test_name, range_low=1.0, range_high=3.0, source_url="http://test")
    db_session.add(ref)
    await db_session.commit()

    # First value inside range, second outside range (above high)
    await _insert_results(db_session, test_patient, test_name, [(d0, 2.0), (d1, 5.0)])

    result = await trend_node(_base_state(test_patient, [test_name]))

    assert result["trend_results"], "Expected at least one trend result"
    tr = result["trend_results"][0]
    assert tr["threshold_crossed"] is True, f"Expected threshold_crossed True, got {tr}"

    await _cleanup(db_session, test_patient, test_name)
    await db_session.execute(
        delete(LabReference).where(LabReference.test_name == test_name)
    )
    await db_session.commit()


# ── test_delta_per_month_correct ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delta_per_month_correct(test_patient: str, db_session: AsyncSession, mock_cache):
    test_name = f"TEST_DELTA_{uuid.uuid4().hex[:6]}"
    today = date.today()
    # Exactly 2 months apart (approximate via year/month arithmetic)
    d0 = date(today.year, today.month - 2 if today.month > 2 else today.month + 10, today.day)
    d1 = today

    v0, v1 = 4.0, 8.0
    await _insert_results(db_session, test_patient, test_name, [(d0, v0), (d1, v1)])

    result = await trend_node(_base_state(test_patient, [test_name]))

    assert result["trend_results"], "Expected trend result"
    tr = result["trend_results"][0]
    expected_delta = (v1 - v0) / 2  # 2 months
    assert abs(tr["delta_per_month"] - expected_delta) < 0.01, (
        f"Expected delta_per_month ≈ {expected_delta}, got {tr['delta_per_month']}"
    )

    await _cleanup(db_session, test_patient, test_name)


# ── test_insufficient_data_skipped ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_insufficient_data_skipped(test_patient: str, db_session: AsyncSession, mock_cache):
    test_name = f"TEST_SINGLE_{uuid.uuid4().hex[:6]}"
    today = date.today()

    # Insert only ONE data point
    await _insert_results(db_session, test_patient, test_name, [(today, 3.5)])

    result = await trend_node(_base_state(test_patient, [test_name]))

    trend_names = [tr["test_name"] for tr in result["trend_results"]]
    assert test_name not in trend_names, (
        f"Expected {test_name} to be skipped (only 1 data point), but it appeared in results"
    )

    await _cleanup(db_session, test_patient, test_name)

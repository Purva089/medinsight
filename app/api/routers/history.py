"""
History and trends router.

GET  /history                    – last N consultations (default 20, max 100)
GET  /history/{session_id}       – all consultations in a session
GET  /trends/{test_name}         – trend computation for a single test
"""
from __future__ import annotations

import uuid
from statistics import mean

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_patient, get_db
from app.core.logging import get_logger
from app.models.consultation import Consultation
from app.models.lab_reference import LabReference
from app.models.lab_result import LabResult
from app.models.patient import Patient
from app.schemas.chat import TrendResult

log = get_logger(__name__)

router = APIRouter(tags=["history"])


# ── Schema helpers ────────────────────────────────────────────────────────────

class ConsultationSummary:
    """Thin dict-style representation for history list items."""

    def __init__(self, c: Consultation) -> None:
        self.consult_id = str(c.consult_id)
        self.session_id = str(c.session_id)
        self.question = c.question
        self.answer = c.answer
        self.intent_handled = c.intent_handled
        self.confidence_level = c.confidence_level
        self.sources_cited = c.sources_cited or []
        self.created_at = c.created_at.isoformat()

    def to_dict(self) -> dict:
        return self.__dict__


# ── GET /history ──────────────────────────────────────────────────────────────

@router.get("/history", response_model=list[dict])
async def get_history(
    limit: int = Query(default=20, ge=1, le=100),
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return the most recent consultations for the authenticated patient."""
    rows = (
        await db.execute(
            select(Consultation)
            .where(Consultation.patient_id == patient.patient_id)
            .order_by(Consultation.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    return [ConsultationSummary(c).to_dict() for c in rows]


# ── GET /history/{session_id} ─────────────────────────────────────────────────

@router.get("/history/{session_id}", response_model=list[dict])
async def get_session_history(
    session_id: uuid.UUID,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return all consultations for a specific session, oldest-first."""
    rows = (
        await db.execute(
            select(Consultation)
            .where(
                Consultation.patient_id == patient.patient_id,
                Consultation.session_id == session_id,
            )
            .order_by(Consultation.created_at.asc())
        )
    ).scalars().all()

    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    return [ConsultationSummary(c).to_dict() for c in rows]


# ── GET /trends/{test_name} ───────────────────────────────────────────────────

@router.get("/trends/{test_name}", response_model=TrendResult)
async def get_trend(
    test_name: str,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> TrendResult:
    """Compute trend for a single lab test from historical results."""
    rows = (
        await db.execute(
            select(LabResult)
            .where(
                LabResult.patient_id == patient.patient_id,
                LabResult.test_name == test_name,
            )
            .order_by(LabResult.report_date.asc())
        )
    ).scalars().all()

    if len(rows) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Need at least 2 data points for test '{test_name}'. Found {len(rows)}.",
        )

    # Fetch reference range
    ref = (
        await db.execute(
            select(LabReference).where(LabReference.test_name == test_name)
        )
    ).scalar_one_or_none()

    ref_low: float | None = ref.range_low if ref else None
    ref_high: float | None = ref.range_high if ref else None

    data_points = [{"date": str(r.report_date), "value": r.value} for r in rows]
    values = [r.value for r in rows]
    first_val, last_val = values[0], values[-1]
    change = last_val - first_val
    change_percent = (change / first_val * 100) if first_val != 0 else 0.0

    # Days between first and last
    days_elapsed = (rows[-1].report_date - rows[0].report_date).days or 1
    months_elapsed = days_elapsed / 30.44
    delta_per_month = change / months_elapsed

    # Velocity concern
    velocity_concern = False
    if ref_low is not None and ref_high is not None:
        ref_range = ref_high - ref_low
        if ref_range > 0 and abs(delta_per_month) > 0.20 * ref_range:
            velocity_concern = True

    # Threshold crossed
    threshold_crossed = False
    if ref_low is not None and ref_high is not None:
        first_in = ref_low <= first_val <= ref_high
        last_in = ref_low <= last_val <= ref_high
        threshold_crossed = first_in != last_in

    # Direction
    if abs(change_percent) < 5:
        direction = "stable"
    elif change > 0:
        direction = "rising"
    else:
        direction = "falling"

    # Significant change detection (>20% change between consecutive readings)
    significant_change = False
    if len(rows) >= 2:
        for i in range(1, len(rows)):
            prev_val = rows[i - 1].value
            curr_val = rows[i].value
            if prev_val and abs((curr_val - prev_val) / prev_val) > 0.20:
                significant_change = True
                break

    description_parts = [f"{test_name} has {direction} by {abs(change_percent):.1f}% over the period."]
    if velocity_concern:
        description_parts.append("Rate of change is clinically significant.")
    if threshold_crossed:
        description_parts.append("Values have crossed the reference range boundary.")
    if significant_change:
        description_parts.append("A significant shift (>20%) was detected between readings.")

    return TrendResult(
        test_name=test_name,
        data_points=data_points,
        direction=direction,
        change_percent=round(change_percent, 2),
        delta_per_month=round(delta_per_month, 4),
        velocity_concern=velocity_concern,
        threshold_crossed=threshold_crossed,
        significant_change=significant_change,
        trend_description=" ".join(description_parts),
        reference_low=ref_low,
        reference_high=ref_high,
    )

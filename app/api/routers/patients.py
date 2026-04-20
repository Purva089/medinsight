"""
Patients router — profile and lab results endpoints.

GET  /patients/me                    – authenticated patient's full profile
GET  /patients/me/lab-results        – all lab results (filterable by test_name, status, date range)
GET  /patients/me/lab-results/latest – most recent value per test (summary view)
GET  /patients/me/reports            – list of uploaded reports with extraction status
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_patient, get_db
from app.core.logging import get_logger
from app.models.lab_result import LabResult
from app.models.patient import Patient
from app.models.uploaded_report import UploadedReport

log = get_logger(__name__)

router = APIRouter(prefix="/patients", tags=["patients"])


# ── GET /patients/me ──────────────────────────────────────────────────────────

@router.get("/me", response_model=dict)
async def get_my_profile(
    patient: Patient = Depends(get_current_patient),
) -> dict:
    """Return the authenticated patient's demographic profile."""
    return {
        "patient_id":        str(patient.patient_id),
        "name":              patient.name,
        "full_name":         patient.name,          # alias for frontend
        "age":               patient.age,
        "gender":            patient.gender,
        "blood_type":        patient.blood_type,
        "medical_condition": patient.medical_condition,
        "medication":        patient.medication,
    }


# ── GET /patients/me/lab-results ──────────────────────────────────────────────

@router.get("/me/lab-results", response_model=list[dict])
async def get_my_lab_results(
    test_name:  Optional[str]  = Query(default=None, description="Filter by test name (partial match)"),
    status:     Optional[str]  = Query(default=None, description="Filter by status: normal / high / low / critical"),
    date_from:  Optional[date] = Query(default=None, description="Include results on or after this date (YYYY-MM-DD)"),
    date_to:    Optional[date] = Query(default=None, description="Include results on or before this date (YYYY-MM-DD)"),
    limit:      int            = Query(default=100, ge=1, le=500),
    patient:    Patient        = Depends(get_current_patient),
    db:         AsyncSession   = Depends(get_db),
) -> list[dict]:
    """
    Return lab results for the authenticated patient.
    Supports optional filters: test_name (partial), status, date range.
    """
    q = (
        select(LabResult)
        .where(LabResult.patient_id == patient.patient_id)
        .order_by(LabResult.report_date.desc(), LabResult.test_name)
    )

    if test_name:
        q = q.where(LabResult.test_name.ilike(f"%{test_name}%"))
    if status:
        q = q.where(LabResult.status == status)
    if date_from:
        q = q.where(LabResult.report_date >= date_from)
    if date_to:
        q = q.where(LabResult.report_date <= date_to)

    q = q.limit(limit)
    rows = (await db.execute(q)).scalars().all()

    return [
        {
            "result_id":           str(r.result_id),
            "test_name":           r.test_name,
            "value":               r.value,
            "unit":                r.unit,
            "status":              r.status,
            "reference_range_low": r.reference_range_low,
            "reference_range_high":r.reference_range_high,
            "report_date":         str(r.report_date),
            "report_id":           str(r.report_id) if r.report_id else None,
        }
        for r in rows
    ]


# ── GET /patients/me/lab-results/latest ───────────────────────────────────────

@router.get("/me/lab-results/latest", response_model=list[dict])
async def get_my_latest_results(
    patient: Patient       = Depends(get_current_patient),
    db:      AsyncSession  = Depends(get_db),
) -> list[dict]:
    """
    Return all lab tests from the single latest uploaded report only.
    Useful for a dashboard overview card.
    """
    from sqlalchemy import func
    # Subquery: find the report_id with the most recent report_date for this patient
    latest_report_subq = (
        select(LabResult.report_id)
        .where(LabResult.patient_id == patient.patient_id)
        .group_by(LabResult.report_id)
        .order_by(func.max(LabResult.report_date).desc())
        .limit(1)
        .scalar_subquery()
    )

    rows = (
        await db.execute(
            select(LabResult)
            .where(
                LabResult.patient_id == patient.patient_id,
                LabResult.report_id == latest_report_subq,
            )
            .order_by(LabResult.test_name)
        )
    ).scalars().all()

    return [
        {
            "test_name":           r.test_name,
            "value":               r.value,
            "unit":                r.unit,
            "status":              r.status,
            "reference_range_low": r.reference_range_low,
            "reference_range_high":r.reference_range_high,
            "report_date":         str(r.report_date),
        }
        for r in rows
    ]


# ── GET /patients/me/reports ──────────────────────────────────────────────────

@router.get("/me/reports", response_model=list[dict])
async def get_my_reports(
    patient: Patient       = Depends(get_current_patient),
    db:      AsyncSession  = Depends(get_db),
) -> list[dict]:
    """Return all uploaded reports for the authenticated patient, newest first."""
    rows = (
        await db.execute(
            select(UploadedReport)
            .where(UploadedReport.patient_id == patient.patient_id)
            .order_by(UploadedReport.created_at.desc())
        )
    ).scalars().all()

    return [
        {
            "report_id":             str(r.report_id),
            "file_name":             r.file_name,
            "extraction_status":     r.extraction_status,
            "tests_extracted":       r.tests_extracted,
            "extraction_confidence": r.extraction_confidence,
            "error_message":         r.error_message,
            "uploaded_at":           r.created_at.isoformat(),
        }
        for r in rows
    ]


# ── GET /patients/me/lab-results/history ──────────────────────────────────────

@router.get("/me/lab-results/history", response_model=list[dict])
async def get_test_history(
    test_name: str         = Query(..., description="Exact test name to get history for"),
    limit:     int         = Query(default=10, ge=1, le=50),
    patient:   Patient     = Depends(get_current_patient),
    db:        AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    Return historical values for a specific test, ordered by date.
    Used for rendering trend charts.
    """
    rows = (
        await db.execute(
            select(LabResult)
            .where(LabResult.patient_id == patient.patient_id)
            .where(LabResult.test_name == test_name)
            .order_by(LabResult.report_date.asc())
            .limit(limit)
        )
    ).scalars().all()

    return [
        {
            "date":                str(r.report_date),
            "value":               r.value,
            "unit":                r.unit,
            "status":              r.status,
            "reference_range_low": r.reference_range_low,
            "reference_range_high": r.reference_range_high,
        }
        for r in rows
    ]

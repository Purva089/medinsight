"""
Report upload and results schemas.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class UploadResponse(BaseModel):
    report_id: str
    status: str
    message: str


class ReportStatusResponse(BaseModel):
    report_id: str
    extraction_status: str
    tests_extracted: int | None = None
    extraction_confidence: float | None = None
    error_message: str | None = None


class LabResultResponse(BaseModel):
    test_name: str
    value: float
    unit: str | None = None
    reference_range_low: float | None = None
    reference_range_high: float | None = None
    status: str | None = None
    report_date: date

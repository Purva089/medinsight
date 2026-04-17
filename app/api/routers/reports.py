"""
Reports router – upload, status, and results endpoints.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import date
from pathlib import Path

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_patient, get_db
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.lab_result import LabResult
from app.models.patient import Patient
from app.models.uploaded_report import UploadedReport
from app.schemas.report import LabResultResponse, ReportStatusResponse, UploadResponse
from app.services.pdf_extractor import PDFExtractor

log = get_logger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_UPLOAD_DIR = _PROJECT_ROOT / "data" / "synthetic_reports" / "uploads"


# ── Background task ───────────────────────────────────────────────────────────

async def _process_report(report_id: uuid.UUID, pdf_bytes: bytes, patient_id: uuid.UUID) -> None:
    """Run PDF extraction and persist results. Called in background."""
    import time as _time
    t0 = _time.perf_counter()
    log.info(
        "report_extraction_started",
        report_id=str(report_id),
        patient_id=str(patient_id),
        size_kb=round(len(pdf_bytes) / 1024, 1),
    )
    async with AsyncSessionLocal() as db:
        report = (
            await db.execute(select(UploadedReport).where(UploadedReport.report_id == report_id))
        ).scalar_one_or_none()

        if report is None:
            log.error("background_report_not_found", report_id=str(report_id))
            return

        report.extraction_status = "processing"
        await db.commit()

        try:
            extractor = PDFExtractor()
            result = await extractor.extract(pdf_bytes, str(report_id), str(patient_id))
            report_date = date.today()

            # Upsert lab results
            inserted = 0
            for test in result.extracted_tests:
                existing = (
                    await db.execute(
                        select(LabResult).where(
                            LabResult.patient_id == patient_id,
                            LabResult.test_name == test.test_name,
                            LabResult.report_date == report_date,
                        )
                    )
                ).scalar_one_or_none()

                if existing is None:
                    lr = LabResult(
                        patient_id=patient_id,
                        report_id=report_id,
                        test_name=test.test_name,
                        value=test.value,
                        unit=test.unit,
                        reference_range_low=test.reference_range_low,
                        reference_range_high=test.reference_range_high,
                        status=test.status,
                        report_date=report_date,
                    )
                    db.add(lr)
                    inserted += 1

            report.extraction_status = "completed"
            report.tests_extracted = inserted
            report.extraction_confidence = result.overall_confidence
            await db.commit()

            duration_ms = round((_time.perf_counter() - t0) * 1000)
            log.info(
                "report_extraction_complete",
                report_id=str(report_id),
                patient_id=str(patient_id),
                tests_inserted=inserted,
                confidence=result.overall_confidence,
                duration_ms=duration_ms,
            )

        except Exception as exc:
            report.extraction_status = "failed"
            report.error_message = str(exc)[:500]
            await db.commit()
            log.error(
                "report_extraction_failed",
                report_id=str(report_id),
                patient_id=str(patient_id),
                error=str(exc),
                exc_info=True,
            )


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_report(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """Upload a PDF lab report for extraction."""
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        # Allow octet-stream so curl uploads without content-type work
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files are accepted.")

    pdf_bytes = await file.read()
    log.info("upload_received", patient=patient.name, filename=file.filename, size_kb=round(len(pdf_bytes)/1024, 1))
    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    file_hash = hashlib.md5(pdf_bytes).hexdigest()

    # Idempotency check – return existing if same file already uploaded
    existing = (
        await db.execute(
            select(UploadedReport).where(
                UploadedReport.patient_id == patient.patient_id,
                UploadedReport.file_hash == file_hash,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        log.info(
            "report_duplicate_detected",
            patient_id=str(patient.patient_id),
            existing_report_id=str(existing.report_id),
            file_hash=file_hash,
        )
        return UploadResponse(
            report_id=str(existing.report_id),
            status=existing.extraction_status,
            message="Duplicate file – returning existing report.",
        )

    # Persist file to disk
    upload_dir = _UPLOAD_DIR / str(patient.patient_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{file_hash[:8]}_{Path(file.filename or 'report.pdf').name}"
    dest = upload_dir / safe_name

    async with aiofiles.open(dest, "wb") as fp:
        await fp.write(pdf_bytes)

    report = UploadedReport(
        patient_id=patient.patient_id,
        file_name=file.filename or "report.pdf",
        file_hash=file_hash,
        storage_path=str(dest.relative_to(_PROJECT_ROOT)),
        extraction_status="pending",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    background_tasks.add_task(_process_report, report.report_id, pdf_bytes, patient.patient_id)

    log.info(
        "report_upload_accepted",
        report_id=str(report.report_id),
        patient_id=str(patient.patient_id),
        patient_name=patient.name,
        filename=file.filename,
        size_kb=round(len(pdf_bytes) / 1024, 1),
        file_hash=file_hash[:12],
        storage_path=str(dest.relative_to(_PROJECT_ROOT)),
    )
    return UploadResponse(
        report_id=str(report.report_id),
        status="pending",
        message="Report accepted and queued for extraction.",
    )


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/{report_id}/status", response_model=ReportStatusResponse)
async def get_report_status(
    report_id: uuid.UUID,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> ReportStatusResponse:
    report = (
        await db.execute(
            select(UploadedReport).where(
                UploadedReport.report_id == report_id,
                UploadedReport.patient_id == patient.patient_id,
            )
        )
    ).scalar_one_or_none()

    if report is None:
        log.warning(
            "report_status_not_found",
            report_id=str(report_id),
            patient_id=str(patient.patient_id),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")

    log.info(
        "report_status_fetched",
        report_id=str(report_id),
        extraction_status=report.extraction_status,
        tests_extracted=report.tests_extracted,
    )
    return ReportStatusResponse(
        report_id=str(report.report_id),
        extraction_status=report.extraction_status,
        tests_extracted=report.tests_extracted,
        extraction_confidence=report.extraction_confidence,
        error_message=report.error_message,
    )


# ── Results ───────────────────────────────────────────────────────────────────

@router.get("/{report_id}/results", response_model=list[LabResultResponse])
async def get_report_results(
    report_id: uuid.UUID,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> list[LabResultResponse]:
    # Verify the report belongs to this patient
    report = (
        await db.execute(
            select(UploadedReport).where(
                UploadedReport.report_id == report_id,
                UploadedReport.patient_id == patient.patient_id,
            )
        )
    ).scalar_one_or_none()

    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")

    results = (
        await db.execute(
            select(LabResult)
            .where(LabResult.report_id == report_id)
            .order_by(LabResult.test_name)
        )
    ).scalars().all()

    log.info(
        "report_results_fetched",
        report_id=str(report_id),
        patient_id=str(patient.patient_id),
        result_count=len(results),
    )

    return [
        LabResultResponse(
            test_name=r.test_name,
            value=r.value,
            unit=r.unit,
            reference_range_low=r.reference_range_low,
            reference_range_high=r.reference_range_high,
            status=r.status,
            report_date=r.report_date,
        )
        for r in results
    ]

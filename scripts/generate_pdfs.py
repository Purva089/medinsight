"""
Synthetic PDF lab report generator for MedInsight Stage 3.

Generates exactly 20 PDFs for 10 specific patients.
Features:
  - Custom randomized test dates for each patient.
  - "Before" and "After" correlation: Initial reports show severe spikes,
    while follow-up reports show significant improvements due to simulated medication.

Usage:
    python scripts/generate_pdfs.py
"""
from __future__ import annotations

import asyncio
import random
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from dataclasses import dataclass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.lab_reference import LabReference
from app.models.lab_result import LabResult
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

log = get_logger(__name__)

# ── output directories ────────────────────────────────────────────────────────
_HIST_DIR = _ROOT / "data" / "synthetic_reports" / "historical"
_CURR_DIR = _ROOT / "data" / "synthetic_reports" / "current"
_HIST_DIR.mkdir(parents=True, exist_ok=True)
_CURR_DIR.mkdir(parents=True, exist_ok=True)

# ── fallback reference ranges ─────────────────────────────────────────────────
_FALLBACK_RANGES: dict[str, tuple[float, float, str]] = {
    "Hemoglobin":          (12.0,  17.5,  "g/dL"),
    "Hematocrit":          (36.0,  50.0,  "%"),
    "RBC Count":           (4.2,   5.9,   "million/µL"),
    "WBC Count":           (4.5,   11.0,  "thousand/µL"),
    "Platelet Count":      (150.0, 400.0, "thousand/µL"),
    "Fasting Blood Glucose": (70.0, 100.0, "mg/dL"),
    "HbA1c":               (4.0,   5.7,   "%"),
    "Creatinine":          (0.6,   1.2,   "mg/dL"),
    "SGPT":                (7.0,   56.0,  "U/L"),
    "Total Cholesterol":   (0.0,   200.0, "mg/dL"),
    "LDL Cholesterol":     (0.0,   100.0, "mg/dL"),
    "HDL Cholesterol":     (40.0,  60.0,  "mg/dL"),
    "Triglycerides":       (0.0,   150.0, "mg/dL"),
    "Vitamin D":           (20.0,  50.0,  "ng/mL"),
    "Calcium":             (8.5,   10.5,  "mg/dL"),
    "TSH":                 (0.4,   4.0,   "mIU/L"),
}

@dataclass
class MockPatient:
    """Mock patient structure to bypass the DB requirement for these 10 specific people."""
    patient_id: str | uuid.UUID
    name: str
    age: int
    gender: str
    blood_type: str
    medical_condition: str

def _get_all_test_names() -> list[str]:
    # If settings.lab_tests_categories isn't available, we fallback to the keys above
    try:
        tests = []
        for names in settings.lab_tests_categories.values():
            tests.extend(names)
        return tests if tests else list(_FALLBACK_RANGES.keys())
    except Exception:
        return list(_FALLBACK_RANGES.keys())


def _compute_status(value: float, low: float, high: float) -> str:
    spread = high - low
    critical_margin = spread * 0.5
    if value < low - critical_margin or value > high + critical_margin:
        return "critical"
    if value < low:
        return "low"
    if value > high:
        return "high"
    return "normal"


def _generate_value(
    test_name: str,
    low: float,
    high: float,
    is_abnormal_target: bool,
    phase: str,
    historical_value: float | None = None,
) -> float:
    """
    Generate values showing significant spikes in 'before' phase, 
    and strong medication improvements in 'after' phase.
    """
    spread = high - low
    rng = random.Random()

    if not is_abnormal_target:
        # Keep non-targeted tests in normal ranges
        val = rng.uniform(low + spread * 0.1, high - spread * 0.1)
    else:
        if phase == "before":
            # Generate a massive spike (either high or low)
            if rng.random() > 0.5:
                val = high * rng.uniform(1.25, 1.70)  # Severe high
            else:
                val = low * rng.uniform(0.40, 0.75) if low > 0 else -abs(low * 0.5) # Severe low
                
        elif phase == "after":
            # Medication effect: massive improvement bridging 70% to 110% of the gap back to normal
            if historical_value is not None:
                if historical_value > high:
                    gap = historical_value - high
                    # Recovers drastically, often returning to normal range
                    val = historical_value - (gap * rng.uniform(0.75, 1.10))
                else:
                    gap = low - historical_value
                    val = historical_value + (gap * rng.uniform(0.75, 1.10))
            else:
                val = rng.uniform(low + spread * 0.1, high - spread * 0.1)

    # Round to 2 decimals and prevent negative biological values
    val = round(val, 2)
    if low >= 0:
        val = max(0.0, val)
    return val


def _build_report_values(
    test_names: list[str],
    ranges: dict[str, tuple[float, float, str]],
    phase: str,
    abnormal_targets: set[str],
    historical_values: dict[str, float] | None = None,
) -> list[dict]:
    
    rows = []
    for name in test_names:
        if name not in ranges:
            continue
            
        low, high, unit = ranges[name]
        hist_val = (historical_values or {}).get(name)
        is_target = name in abnormal_targets
        
        val = _generate_value(name, low, high, is_target, phase, hist_val)
        status = _compute_status(val, low, high)
        
        rows.append({
            "test_name": name,
            "value": val,
            "unit": unit,
            "low": low,
            "high": high,
            "status": status,
        })
    return rows


# ── PDF rendering ─────────────────────────────────────────────────────────────

def _render_pdf(
    path: Path,
    patient: MockPatient,
    report_date: date,
    rows: list[dict],
) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("<b>MedInsight — Laboratory Report</b>", styles["Title"]))
    story.append(Spacer(1, 0.3 * cm))

    header_data = [
        ["Patient Name:", patient.name.title(), "Report Date:", str(report_date)],
        ["Patient ID:", str(patient.patient_id)[:8].upper(), "Age / Gender:", f"{patient.age} / {patient.gender}"],
        ["Blood Type:", patient.blood_type, "Medical Condition:", patient.medical_condition],
    ]
    header_table = Table(header_data, colWidths=[3.5 * cm, 5.5 * cm, 3.5 * cm, 5 * cm])
    header_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.5 * cm))

    table_data = [["Test Name", "Value", "Unit", "Reference Range", "Status"]]
    for row in rows:
        table_data.append([
            row["test_name"], str(row["value"]), row["unit"],
            f"{row['low']} – {row['high']}", row["status"].upper()
        ])

    results_table = Table(table_data, colWidths=[5.5 * cm, 2.5 * cm, 3.5 * cm, 4.0 * cm, 2.5 * cm], repeatRows=1)
    
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("ALIGN", (4, 0), (4, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F3F4")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BDC3C7")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]
    
    for i, row in enumerate(rows, start=1):
        if row["status"] == "critical":
            style_cmds.extend([
                ("BACKGROUND", (4, i), (4, i), colors.HexColor("#E74C3C")),
                ("TEXTCOLOR", (4, i), (4, i), colors.white),
                ("FONTNAME", (4, i), (4, i), "Helvetica-Bold")
            ])
        elif row["status"] in ("high", "low"):
            style_cmds.extend([
                ("BACKGROUND", (4, i), (4, i), colors.HexColor("#F39C12")),
                ("TEXTCOLOR", (4, i), (4, i), colors.white)
            ])

    results_table.setStyle(TableStyle(style_cmds))
    story.append(results_table)
    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph("<i>This is a synthetic report generated for demonstration purposes. Not for clinical use.</i>", styles["Normal"]))
    
    doc.build(story)


# ── database helpers ──────────────────────────────────────────────────────────

async def _load_lab_references() -> dict[str, tuple[float, float, str]]:
    ranges = dict(_FALLBACK_RANGES)
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(LabReference))
            for ref in result.scalars().all():
                if ref.range_low is not None and ref.range_high is not None:
                    _, _, unit = ranges.get(ref.test_name, (None, None, ""))
                    ranges[ref.test_name] = (ref.range_low, ref.range_high, unit)
    except Exception as exc:
        log.warning(f"Could not load DB references, using fallbacks. Error: {exc}")
    return ranges


async def _upsert_lab_results(patient_id: str, rows: list[dict], report_date: date) -> None:
    # NOTE: Since we are mocking patients, inserting these into the DB might fail due to Foreign Key constraints
    # If you want them in the DB, uncomment the logic below AFTER ensuring the UUIDs exist in your patients table.
    pass 
    """
    async with AsyncSessionLocal() as session:
        for row in rows:
            stmt = pg_insert(LabResult).values(...)
            stmt = stmt.on_conflict_do_update(...)
            await session.execute(stmt)
        await session.commit()
    """


# ── main ──────────────────────────────────────────────────────────────────────

def _get_mock_patients() -> list[MockPatient]:
    """Return 10 specific people to generate reports for."""
    return [
        MockPatient(uuid.uuid4(), "Aayush Kumar Bhat", 32, "Male", "O+", "Hyperlipidemia"),
        MockPatient(uuid.uuid4(), "Sarah Jenkins", 45, "Female", "A-", "Type 2 Diabetes"),
        MockPatient(uuid.uuid4(), "David Chen", 28, "Male", "B+", "Vitamin D Deficiency"),
        MockPatient(uuid.uuid4(), "Maria Garcia", 55, "Female", "O-", "Hypothyroidism"),
        MockPatient(uuid.uuid4(), "James Wilson", 61, "Male", "AB+", "Chronic Kidney Disease"),
        MockPatient(uuid.uuid4(), "Priya Sharma", 38, "Female", "A+", "Anemia"),
        MockPatient(uuid.uuid4(), "Robert Taylor", 50, "Male", "O+", "Hypertension"),
        MockPatient(uuid.uuid4(), "Emily Davis", 29, "Female", "B-", "PCOS"),
        MockPatient(uuid.uuid4(), "Michael Brown", 42, "Male", "O+", "Liver Steatosis"),
        MockPatient(uuid.uuid4(), "Sophia Martinez", 34, "Female", "A+", "Hyperthyroidism"),
    ]


async def generate() -> None:
    log.info("loading_data")
    patients = _get_mock_patients()
    ranges = await _load_lab_references()

    all_tests = _get_all_test_names()
    valid_tests = [t for t in all_tests if t in ranges]

    log.info("generation_started", patient_count=len(patients), test_count=len(valid_tests))

    rng = random.Random()
    pdf_count = 0

    for patient in patients:
        pid = str(patient.patient_id)
        
        # 1. Create randomized dates per patient
        # "Before" date: Randomly anywhere from 60 to 180 days ago
        hist_date = date.today() - timedelta(days=rng.randint(60, 180))
        # "After" date: Randomly anywhere from 2 to 30 days ago
        curr_date = date.today() - timedelta(days=rng.randint(2, 30))

        # Randomly select 3-5 tests to "spike" for this specific patient
        abnormal_count = rng.randint(3, 5)
        abnormal_targets = set(rng.sample(valid_tests, min(abnormal_count, len(valid_tests))))

        # ── historical report (BEFORE - Spikes) ──
        hist_rows = _build_report_values(valid_tests, ranges, "before", abnormal_targets)
        hist_path = _HIST_DIR / f"{patient.name.replace(' ', '_')}_{pid[:8]}_before.pdf"
        _render_pdf(hist_path, patient, hist_date, hist_rows)
        pdf_count += 1

        # (Optional) Seed historical lab_results into DB
        await _upsert_lab_results(pid, hist_rows, hist_date)

        # ── current report (AFTER - Medication Improvements) ──
        hist_value_map = {r["test_name"]: r["value"] for r in hist_rows}
        curr_rows = _build_report_values(
            valid_tests, ranges, "after", abnormal_targets, historical_values=hist_value_map
        )
        curr_path = _CURR_DIR / f"{patient.name.replace(' ', '_')}_{pid[:8]}_after.pdf"
        _render_pdf(curr_path, patient, curr_date, curr_rows)
        pdf_count += 1

        log.info(
            "patient_processed",
            name=patient.name,
            hist_date=str(hist_date),
            curr_date=str(curr_date),
            spiked_tests=list(abnormal_targets)
        )

    log.info("generation_complete", pdfs_created=pdf_count)


if __name__ == "__main__":
    asyncio.run(generate())
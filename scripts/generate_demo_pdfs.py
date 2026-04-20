"""
Generate realistic PDF lab reports for demo patients.

Creates test PDFs that can be uploaded via the frontend to test
the full extraction → analysis → report pipeline.

Usage:
    python scripts/generate_demo_pdfs.py                # Generate for all demo patients
    python scripts/generate_demo_pdfs.py --patient 1    # Generate for patient 1 only
    python scripts/generate_demo_pdfs.py --current      # Only current reports (not historical)
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.logging import get_logger

log = get_logger(__name__)

# Output directory
OUTPUT_DIR = _ROOT / "data" / "demo_reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Patient Data (matches seed_demo_data.py) ──────────────────────────────────

DEMO_PATIENTS = [
    {
        "name": "Aarav Sharma",
        "age": 32,
        "gender": "Male",
        "condition": "Type 2 Diabetes",
        "tests": ["Hemoglobin", "Fasting Blood Glucose", "HbA1c", "SGPT (ALT)", "SGOT (AST)"],
    },
    {
        "name": "Priya Patel",
        "age": 28,
        "gender": "Female",
        "condition": "Hypothyroidism",
        "tests": ["TSH", "Free T3", "Free T4", "Hemoglobin"],
    },
    {
        "name": "Rahul Verma",
        "age": 45,
        "gender": "Male",
        "condition": "Fatty Liver",
        "tests": ["SGPT (ALT)", "SGOT (AST)", "Total Bilirubin", "Alkaline Phosphatase", "Hemoglobin"],
    },
    {
        "name": "Anjali Singh",
        "age": 35,
        "gender": "Female",
        "condition": "Anemia",
        "tests": ["Hemoglobin", "RBC Count", "WBC Count", "Platelet Count"],
    },
    {
        "name": "Vikram Reddy",
        "age": 52,
        "gender": "Male",
        "condition": "Hypertension",
        "tests": ["Hemoglobin", "Fasting Blood Glucose", "SGPT (ALT)", "SGOT (AST)"],
    },
    {
        "name": "Neha Gupta",
        "age": 29,
        "gender": "Female",
        "condition": "Healthy",
        "tests": ["Hemoglobin", "RBC Count", "WBC Count", "Fasting Blood Glucose", "SGPT (ALT)"],
    },
    {
        "name": "Arjun Nair",
        "age": 41,
        "gender": "Male",
        "condition": "Pre-diabetes",
        "tests": ["Fasting Blood Glucose", "HbA1c", "Hemoglobin", "SGPT (ALT)"],
    },
    {
        "name": "Kavya Iyer",
        "age": 38,
        "gender": "Female",
        "condition": "Thyroid nodule",
        "tests": ["TSH", "Free T3", "Free T4", "Hemoglobin"],
    },
    {
        "name": "Rohan Mehta",
        "age": 55,
        "gender": "Male",
        "condition": "Chronic liver disease",
        "tests": ["SGPT (ALT)", "SGOT (AST)", "Total Bilirubin", "Alkaline Phosphatase", "Hemoglobin"],
    },
    {
        "name": "Simran Kaur",
        "age": 25,
        "gender": "Female",
        "condition": "Healthy",
        "tests": ["Hemoglobin", "RBC Count", "WBC Count", "TSH", "Fasting Blood Glucose"],
    },
]


# Lab test reference ranges
LAB_TESTS = {
    "Hemoglobin": {"unit": "g/dL", "ref_low": 12.0, "ref_high": 16.0, "normal": (12.5, 15.5), "low": (8.0, 11.5), "high": (16.5, 18.0)},
    "RBC Count": {"unit": "million/µL", "ref_low": 4.0, "ref_high": 5.5, "normal": (4.2, 5.2), "low": (3.0, 3.9), "high": (5.6, 6.5)},
    "WBC Count": {"unit": "cells/µL", "ref_low": 4000, "ref_high": 11000, "normal": (5000, 9000), "low": (2000, 3800), "high": (11500, 15000)},
    "Platelet Count": {"unit": "lakh/µL", "ref_low": 1.5, "ref_high": 4.0, "normal": (1.8, 3.5), "low": (0.5, 1.4), "high": (4.2, 6.0)},
    "Fasting Blood Glucose": {"unit": "mg/dL", "ref_low": 70, "ref_high": 100, "normal": (75, 95), "low": (50, 68), "high": (110, 180)},
    "HbA1c": {"unit": "%", "ref_low": 4.0, "ref_high": 5.6, "normal": (4.5, 5.4), "low": (3.5, 4.3), "high": (6.0, 9.5)},
    "SGPT (ALT)": {"unit": "U/L", "ref_low": 7, "ref_high": 56, "normal": (15, 45), "low": (3, 6), "high": (65, 150)},
    "SGOT (AST)": {"unit": "U/L", "ref_low": 10, "ref_high": 40, "normal": (15, 35), "low": (5, 9), "high": (50, 120)},
    "Total Bilirubin": {"unit": "mg/dL", "ref_low": 0.1, "ref_high": 1.2, "normal": (0.3, 1.0), "low": (0.05, 0.2), "high": (1.5, 3.5)},
    "Alkaline Phosphatase": {"unit": "U/L", "ref_low": 44, "ref_high": 147, "normal": (60, 120), "low": (20, 40), "high": (160, 300)},
    "TSH": {"unit": "mIU/L", "ref_low": 0.4, "ref_high": 4.0, "normal": (1.0, 3.5), "low": (0.1, 0.35), "high": (5.0, 15.0)},
    "Free T3": {"unit": "pg/mL", "ref_low": 2.0, "ref_high": 4.4, "normal": (2.5, 4.0), "low": (1.2, 1.9), "high": (4.8, 7.0)},
    "Free T4": {"unit": "ng/dL", "ref_low": 0.8, "ref_high": 1.8, "normal": (1.0, 1.6), "low": (0.4, 0.75), "high": (2.0, 3.5)},
}

# Condition-specific abnormalities
CONDITION_ABNORMALS = {
    "Type 2 Diabetes": {"Fasting Blood Glucose": "high", "HbA1c": "high"},
    "Hypothyroidism": {"TSH": "high", "Free T3": "low", "Free T4": "low"},
    "Fatty Liver": {"SGPT (ALT)": "high", "SGOT (AST)": "high"},
    "Anemia": {"Hemoglobin": "low", "RBC Count": "low"},
    "Pre-diabetes": {"Fasting Blood Glucose": "high", "HbA1c": "high"},
    "Chronic liver disease": {"SGPT (ALT)": "high", "SGOT (AST)": "high", "Total Bilirubin": "high"},
    "Thyroid nodule": {"TSH": "high"},
}


def _generate_value(test_name: str, condition: str) -> tuple[float, str]:
    """Generate realistic value based on condition."""
    test = LAB_TESTS[test_name]
    
    # Determine if this test should be abnormal for this condition
    abnormal_type = CONDITION_ABNORMALS.get(condition, {}).get(test_name)
    
    if abnormal_type and random.random() < 0.75:  # 75% chance of showing condition
        low, high = test[abnormal_type]
        value = random.uniform(low, high)
    else:
        low, high = test["normal"]
        value = random.uniform(low, high)
    
    # Determine status
    if value < test["ref_low"]:
        status = "Low"
    elif value > test["ref_high"]:
        status = "High"
    else:
        status = "Normal"
    
    # Round appropriately
    if test["unit"] in ("cells/µL", "U/L"):
        value = round(value)
    else:
        value = round(value, 2)
    
    return value, status


def _create_pdf_report(patient: dict, report_date: date, output_path: Path) -> None:
    """Generate a PDF lab report using reportlab."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch, cm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    except ImportError:
        print("❌ reportlab not installed. Run: pip install reportlab")
        return

    doc = SimpleDocTemplate(str(output_path), pagesize=A4, topMargin=1*cm, bottomMargin=1*cm)
    styles = getSampleStyleSheet()
    elements = []

    # Header
    header_style = ParagraphStyle(
        'Header',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.darkblue,
        spaceAfter=10,
        alignment=1,  # Center
    )
    elements.append(Paragraph("MedInsight Diagnostic Center", header_style))
    elements.append(Paragraph("Laboratory Test Report", styles['Heading2']))
    elements.append(Spacer(1, 0.3*inch))

    # Patient Info
    patient_info = [
        ["Patient Name:", patient["name"], "Age/Gender:", f"{patient['age']} / {patient['gender']}"],
        ["Report Date:", report_date.strftime("%d-%b-%Y"), "Sample ID:", f"MI-{random.randint(100000, 999999)}"],
    ]
    patient_table = Table(patient_info, colWidths=[1.5*inch, 2*inch, 1.5*inch, 2*inch])
    patient_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(patient_table)
    elements.append(Spacer(1, 0.3*inch))

    # Test Results Header
    elements.append(Paragraph("Test Results", styles['Heading3']))
    elements.append(Spacer(1, 0.1*inch))

    # Test Results Table
    table_data = [["Test Name", "Result", "Unit", "Reference Range", "Status"]]
    
    for test_name in patient["tests"]:
        test = LAB_TESTS[test_name]
        value, status = _generate_value(test_name, patient["condition"])
        
        table_data.append([
            test_name,
            str(value),
            test["unit"],
            f"{test['ref_low']} - {test['ref_high']}",
            status,
        ])

    test_table = Table(table_data, colWidths=[2.2*inch, 1*inch, 1*inch, 1.5*inch, 1*inch])
    test_table.setStyle(TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        # Data rows
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        # Alternating row colors
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        # Alignment
        ('ALIGN', (1, 1), (1, -1), 'CENTER'),  # Result column
        ('ALIGN', (2, 1), (2, -1), 'CENTER'),  # Unit column
        ('ALIGN', (3, 1), (3, -1), 'CENTER'),  # Reference column
        ('ALIGN', (4, 1), (4, -1), 'CENTER'),  # Status column
    ]))
    
    # Color-code status
    for i, row in enumerate(table_data[1:], start=1):
        status = row[4]
        if status == "High":
            test_table.setStyle(TableStyle([('TEXTCOLOR', (4, i), (4, i), colors.red)]))
        elif status == "Low":
            test_table.setStyle(TableStyle([('TEXTCOLOR', (4, i), (4, i), colors.orange)]))

    elements.append(test_table)
    elements.append(Spacer(1, 0.3*inch))

    # Footer
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
        alignment=1,
    )
    elements.append(Spacer(1, 0.5*inch))
    elements.append(Paragraph("This is a computer-generated report. Please consult your physician for interpretation.", footer_style))
    elements.append(Paragraph("MedInsight Diagnostic Center | demo@medinsight.com | +91-9876543210", footer_style))

    doc.build(elements)


def generate_reports(patient_index: int | None = None, current_only: bool = False) -> None:
    """Generate PDF reports for demo patients."""
    today = date.today()
    
    # Report dates: 3 months ago, 1 month ago, current
    report_dates = [today] if current_only else [
        today - timedelta(days=90),
        today - timedelta(days=30),
        today,
    ]

    patients_to_process = (
        [DEMO_PATIENTS[patient_index - 1]] if patient_index 
        else DEMO_PATIENTS
    )

    print(f"\n📄 Generating PDF reports in: {OUTPUT_DIR}\n")

    total_generated = 0
    for patient in patients_to_process:
        for report_date in report_dates:
            date_str = report_date.strftime("%Y%m%d")
            safe_name = patient["name"].replace(" ", "_")
            filename = f"{safe_name}_{date_str}.pdf"
            output_path = OUTPUT_DIR / filename

            print(f"  Creating: {filename}")
            _create_pdf_report(patient, report_date, output_path)
            total_generated += 1

    print(f"\n✅ Generated {total_generated} PDF reports")
    print(f"📁 Location: {OUTPUT_DIR}")


def main():
    parser = argparse.ArgumentParser(description="Generate demo PDF lab reports")
    parser.add_argument(
        "--patient",
        type=int,
        choices=range(1, 11),
        help="Generate for specific patient (1-10)",
    )
    parser.add_argument(
        "--current",
        action="store_true",
        help="Only generate current date reports (not historical)",
    )
    args = parser.parse_args()

    generate_reports(patient_index=args.patient, current_only=args.current)

    print("\n" + "=" * 60)
    print("  Demo Patients Reference")
    print("=" * 60)
    for i, p in enumerate(DEMO_PATIENTS, 1):
        print(f"  {i}. {p['name']:20} | {p['condition']}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

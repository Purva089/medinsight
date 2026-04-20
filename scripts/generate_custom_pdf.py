"""
Generate a custom lab report PDF with your own patient data.

Usage:
    python scripts/generate_custom_pdf.py --name "John Doe" --age 30 --gender Male
    python scripts/generate_custom_pdf.py --name "Jane Smith" --age 28 --gender Female --tests "Hemoglobin,TSH,Glucose"
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

OUTPUT_DIR = _ROOT / "data" / "custom_reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Lab test reference ranges
LAB_TESTS = {
    "Hemoglobin": {"unit": "g/dL", "ref_low": 12.0, "ref_high": 16.0, "normal": (12.5, 15.5)},
    "RBC Count": {"unit": "million/µL", "ref_low": 4.0, "ref_high": 5.5, "normal": (4.2, 5.2)},
    "WBC Count": {"unit": "cells/µL", "ref_low": 4000, "ref_high": 11000, "normal": (5000, 9000)},
    "Platelet Count": {"unit": "lakh/µL", "ref_low": 1.5, "ref_high": 4.0, "normal": (1.8, 3.5)},
    "Fasting Blood Glucose": {"unit": "mg/dL", "ref_low": 70, "ref_high": 100, "normal": (75, 95)},
    "HbA1c": {"unit": "%", "ref_low": 4.0, "ref_high": 5.6, "normal": (4.5, 5.4)},
    "SGPT": {"unit": "U/L", "ref_low": 7, "ref_high": 56, "normal": (15, 45)},
    "ALT": {"unit": "U/L", "ref_low": 7, "ref_high": 56, "normal": (15, 45)},
    "SGOT": {"unit": "U/L", "ref_low": 10, "ref_high": 40, "normal": (15, 35)},
    "AST": {"unit": "U/L", "ref_low": 10, "ref_high": 40, "normal": (15, 35)},
    "Total Bilirubin": {"unit": "mg/dL", "ref_low": 0.1, "ref_high": 1.2, "normal": (0.3, 1.0)},
    "Alkaline Phosphatase": {"unit": "U/L", "ref_low": 44, "ref_high": 147, "normal": (60, 120)},
    "TSH": {"unit": "mIU/L", "ref_low": 0.4, "ref_high": 4.0, "normal": (1.0, 3.5)},
    "Free T3": {"unit": "pg/mL", "ref_low": 2.0, "ref_high": 4.4, "normal": (2.5, 4.0)},
    "Free T4": {"unit": "ng/dL", "ref_low": 0.8, "ref_high": 1.8, "normal": (1.0, 1.6)},
}

DEFAULT_TESTS = ["Hemoglobin", "WBC Count", "RBC Count", "Fasting Blood Glucose", "SGPT"]


def _generate_value(test_name: str) -> tuple[float, str]:
    """Generate a random normal value for the test."""
    test = LAB_TESTS[test_name]
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


def create_pdf(name: str, age: int, gender: str, tests: list[str], report_date: date, output_path: Path) -> None:
    """Generate a PDF lab report."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch, cm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    except ImportError:
        print("❌ reportlab not installed. Run: pip install reportlab")
        sys.exit(1)

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
        alignment=1,
    )
    elements.append(Paragraph("MedInsight Diagnostic Center", header_style))
    elements.append(Paragraph("Laboratory Test Report", styles['Heading2']))
    elements.append(Spacer(1, 0.3*inch))

    # Patient Info
    patient_info = [
        ["Patient Name:", name, "Age/Gender:", f"{age} / {gender}"],
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

    # Test Results
    elements.append(Paragraph("Test Results", styles['Heading3']))
    elements.append(Spacer(1, 0.1*inch))

    table_data = [["Test Name", "Result", "Unit", "Reference Range", "Status"]]
    
    for test_name in tests:
        if test_name not in LAB_TESTS:
            print(f"⚠️  Unknown test: {test_name} (skipping)")
            continue
        
        test = LAB_TESTS[test_name]
        value, status = _generate_value(test_name)
        
        table_data.append([
            test_name,
            str(value),
            test["unit"],
            f"{test['ref_low']} - {test['ref_high']}",
            status,
        ])

    test_table = Table(table_data, colWidths=[2.2*inch, 1*inch, 1*inch, 1.5*inch, 1*inch])
    test_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 1), (1, -1), 'CENTER'),
        ('ALIGN', (2, 1), (2, -1), 'CENTER'),
        ('ALIGN', (3, 1), (3, -1), 'CENTER'),
        ('ALIGN', (4, 1), (4, -1), 'CENTER'),
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
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey, alignment=1)
    elements.append(Spacer(1, 0.5*inch))
    elements.append(Paragraph("This is a computer-generated report. Please consult your physician for interpretation.", footer_style))
    elements.append(Paragraph("MedInsight Diagnostic Center | demo@medinsight.com | +91-9876543210", footer_style))

    doc.build(elements)


def main():
    parser = argparse.ArgumentParser(description="Generate custom lab report PDF")
    parser.add_argument("--name", required=True, help="Patient name (e.g., 'John Doe')")
    parser.add_argument("--age", type=int, required=True, help="Patient age")
    parser.add_argument("--gender", required=True, choices=["Male", "Female", "Other"], help="Patient gender")
    parser.add_argument(
        "--tests",
        help="Comma-separated test names (default: Hemoglobin,WBC Count,RBC Count,Glucose,SGPT)",
        default=None,
    )
    parser.add_argument(
        "--month",
        choices=["today", "1month", "2months", "3months"],
        default="today",
        help="Report date relative to today (default: today)",
    )
    parser.add_argument("--output", help="Custom output filename (without .pdf)", default=None)
    
    args = parser.parse_args()

    # Parse tests
    if args.tests:
        tests = [t.strip() for t in args.tests.split(",")]
    else:
        tests = DEFAULT_TESTS

    # Generate filename with month suffix
    if args.output:
        filename = f"{args.output}.pdf"
    else:
        safe_name = args.name.replace(" ", "_").lower()
        month_suffix = args.month
        filename = f"{safe_name}_{month_suffix}.pdf"
    
    output_path = OUTPUT_DIR / filename

    # Calculate report date based on month parameter
    today = date.today()
    month_offset = {
        "today": 0,
        "1month": 30,
        "2months": 60,
        "3months": 90,
    }
    from datetime import timedelta
    report_date = today - timedelta(days=month_offset[args.month])

    print(f"\n📄 Generating custom lab report...")
    print(f"   Name: {args.name}")
    print(f"   Age: {args.age}")
    print(f"   Gender: {args.gender}")
    print(f"   Report Date: {report_date.strftime('%d-%b-%Y')} ({args.month})")
    print(f"   Tests: {', '.join(tests)}")
    print(f"   Output: {output_path}\n")

    create_pdf(args.name, args.age, args.gender, tests, report_date, output_path)

    print(f"✅ PDF generated successfully!")
    print(f"📁 Location: {output_path}\n")

    print("Available tests:")
    print("  " + ", ".join(LAB_TESTS.keys()))
    print()


if __name__ == "__main__":
    main()

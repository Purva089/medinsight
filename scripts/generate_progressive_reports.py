"""
Generate category-specific lab reports with realistic value distributions.

Creates single-category reports (e.g., Blood Count Panel, Liver Function Test)
with mix of normal, abnormal, and borderline values.

Usage:
    # Blood Count Panel
    python scripts/generate_progressive_reports.py --name "Purva Miglani" --age 28 --gender Female --blood-group "O+" --category blood_count
    
    # Liver Function Test (abnormal)
    python scripts/generate_progressive_reports.py --name "Purva Miglani" --age 28 --gender Female --blood-group "O+" --category liver --abnormal-count 2
    
    # Multiple reports over time (same category)
    python scripts/generate_progressive_reports.py --name "Purva Miglani" --age 28 --gender Female --blood-group "O+" --category metabolic --reports 3 --interval 30
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

OUTPUT_DIR = _ROOT / "data" / "custom_reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Lab test reference ranges organized by category
TESTS_BY_CATEGORY = {
    "blood_count": {
        "Hemoglobin": {"unit": "g/dL", "ref_low": 12.0, "ref_high": 16.0},
        "RBC Count": {"unit": "million/µL", "ref_low": 4.0, "ref_high": 5.5},
        "WBC Count": {"unit": "cells/µL", "ref_low": 4000, "ref_high": 11000},
        "Platelet Count": {"unit": "lakh/µL", "ref_low": 1.5, "ref_high": 4.0},
        "Hematocrit": {"unit": "%", "ref_low": 36.0, "ref_high": 46.0},
    },
    "metabolic": {
        "Fasting Blood Glucose": {"unit": "mg/dL", "ref_low": 70, "ref_high": 100},
        "HbA1c": {"unit": "%", "ref_low": 4.0, "ref_high": 5.6},
        "Random Blood Sugar": {"unit": "mg/dL", "ref_low": 70, "ref_high": 140},
        "Creatinine": {"unit": "mg/dL", "ref_low": 0.6, "ref_high": 1.2},
    },
    "liver": {
        "SGPT (ALT)": {"unit": "U/L", "ref_low": 7, "ref_high": 56},
        "SGOT (AST)": {"unit": "U/L", "ref_low": 10, "ref_high": 40},
        "Total Bilirubin": {"unit": "mg/dL", "ref_low": 0.1, "ref_high": 1.2},
        "Alkaline Phosphatase": {"unit": "U/L", "ref_low": 44, "ref_high": 147},
        "Total Protein": {"unit": "g/dL", "ref_low": 6.0, "ref_high": 8.3},
        "Albumin": {"unit": "g/dL", "ref_low": 3.5, "ref_high": 5.0},
    },
    "thyroid": {
        "TSH": {"unit": "mIU/L", "ref_low": 0.4, "ref_high": 4.0},
        "Free T3": {"unit": "pg/mL", "ref_low": 2.0, "ref_high": 4.4},
        "Free T4": {"unit": "ng/dL", "ref_low": 0.8, "ref_high": 1.8},
        "Total T3": {"unit": "ng/dL", "ref_low": 80, "ref_high": 200},
    },
}

# Category display names
CATEGORY_NAMES = {
    "blood_count": "Complete Blood Count (CBC)",
    "metabolic": "Metabolic Panel",
    "liver": "Liver Function Test (LFT)",
    "thyroid": "Thyroid Profile",
}

# Blood group options
BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]


def get_all_tests() -> dict[str, dict]:
    """Flatten all tests into a single dictionary."""
    all_tests = {}
    for category_tests in TESTS_BY_CATEGORY.values():
        all_tests.update(category_tests)
    return all_tests


def generate_value_with_status(ref_low: float, ref_high: float, status_type: str) -> float:
    """
    Generate a test value based on desired status.
    
    Args:
        ref_low: Lower bound of reference range
        ref_high: Upper bound of reference range
        status_type: "normal", "high", "low", or "borderline"
    
    Returns:
        A value matching the status type
    """
    range_span = ref_high - ref_low
    
    if status_type == "normal":
        # Middle 60% of range
        margin = range_span * 0.2
        value = random.uniform(ref_low + margin, ref_high - margin)
    
    elif status_type == "borderline":
        # Within 10% of limits (either side)
        if random.choice([True, False]):
            # Near upper limit
            value = random.uniform(ref_high * 0.95, ref_high * 1.05)
        else:
            # Near lower limit
            value = random.uniform(ref_low * 0.95, ref_low * 1.05)
    
    elif status_type == "high":
        # 10-30% above upper limit
        overshoot = random.uniform(0.10, 0.30) * range_span
        value = ref_high + overshoot
    
    else:  # low
        # 10-30% below lower limit
        undershoot = random.uniform(0.10, 0.30) * range_span
        value = ref_low - undershoot
    
    return max(0.01, value)  # Ensure positive


def improve_value(
    current_value: float, 
    ref_low: float, 
    ref_high: float, 
    trend: str,
    improvement_factor: float = 0.3
) -> float:
    """
    Move value toward normal range but keep it abnormal.
    
    Args:
        current_value: Current test value
        ref_low: Lower bound of reference range
        ref_high: Upper bound of reference range
        trend: "high" or "low"
        improvement_factor: How much to improve (0.0-1.0)
    
    Returns:
        Improved but still abnormal value
    """
    if trend == "high":
        # Move toward upper limit but stay above it
        target = ref_high
        gap = current_value - target
        improvement = gap * improvement_factor
        new_value = current_value - improvement
        # Ensure still abnormal (at least 5% above upper limit)
        min_abnormal = ref_high * 1.05
        return max(min_abnormal, new_value)
    else:  # low
        # Move toward lower limit but stay below it
        target = ref_low
        gap = target - current_value
        improvement = gap * improvement_factor
        new_value = current_value + improvement
        # Ensure still abnormal (at least 5% below lower limit)
        max_abnormal = ref_low * 0.95
        return min(max_abnormal, new_value)


def round_value(value: float, unit: str) -> float:
    """Round value appropriately based on unit."""
    if unit in ("cells/µL", "U/L", "lakh/µL"):
        return round(value)
    else:
        return round(value, 2)


def get_status(value: float, ref_low: float, ref_high: float) -> str:
    """Determine test status."""
    if value < ref_low:
        return "Low"
    elif value > ref_high:
        return "High"
    else:
        return "Normal"


def create_pdf(
    name: str,
    age: int,
    gender: str,
    blood_group: str,
    category: str,
    tests_data: list[dict],
    report_date: date,
    output_path: Path
) -> None:
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
    category_name = CATEGORY_NAMES.get(category, "Laboratory Tests")
    patient_info = [
        ["Patient Name:", name, "Age/Gender:", f"{age} / {gender}"],
        ["Report Date:", report_date.strftime("%d-%b-%Y"), "Blood Group:", blood_group],
        ["Test Category:", category_name, "Sample ID:", f"MI-{random.randint(10000, 99999)}"],
    ]
    
    patient_table = Table(patient_info, colWidths=[3*cm, 5.5*cm, 3*cm, 3.5*cm])
    patient_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTNAME', (3, 0), (3, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.darkblue),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.darkblue),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(patient_table)
    elements.append(Spacer(1, 0.4*inch))

    # Test Results Header
    elements.append(Paragraph("Test Results", styles['Heading3']))
    elements.append(Spacer(1, 0.2*inch))

    # Test Results Table
    table_data = [["Test Name", "Result", "Unit", "Reference Range", "Status"]]
    
    for test in tests_data:
        ref_range = f"{test['ref_low']} - {test['ref_high']}"
        
        # Color-code status
        status_color = colors.green if test['status'] == "Normal" else colors.red
        
        table_data.append([
            test['name'],
            str(test['value']),
            test['unit'],
            ref_range,
            test['status']
        ])

    results_table = Table(table_data, colWidths=[5*cm, 2.5*cm, 2.5*cm, 3.5*cm, 2.5*cm])
    results_table.setStyle(TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Data rows
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
    ]))
    
    # Color status column
    for idx, test in enumerate(tests_data, start=1):
        if test['status'] != "Normal":
            results_table.setStyle(TableStyle([
                ('TEXTCOLOR', (4, idx), (4, idx), colors.red),
                ('FONTNAME', (4, idx), (4, idx), 'Helvetica-Bold'),
            ]))

    elements.append(results_table)
    elements.append(Spacer(1, 0.5*inch))

    # Footer
    footer_text = "This is a computer-generated report. Please consult your physician for interpretation."
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
        alignment=1,
    )
    elements.append(Paragraph(footer_text, footer_style))
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph("MedInsight - Your Health, Our Priority", footer_style))

    doc.build(elements)


def generate_category_reports(
    name: str,
    age: int,
    gender: str,
    blood_group: str,
    category: str,
    num_reports: int,
    interval_days: int,
    abnormal_count: int,
    borderline_count: int,
) -> None:
    """
    Generate category-specific reports with realistic value distribution.
    
    Args:
        name: Patient name
        age: Patient age
        gender: Patient gender
        blood_group: Blood group (A+, B+, O+, etc.)
        category: Test category (blood_count, liver, metabolic, thyroid)
        num_reports: Number of reports to generate
        interval_days: Days between reports
        abnormal_count: Number of abnormal tests
        borderline_count: Number of borderline tests
    """
    if category not in TESTS_BY_CATEGORY:
        print(f"❌ Unknown category: {category}")
        print(f"Available categories: {', '.join(TESTS_BY_CATEGORY.keys())}")
        sys.exit(1)
    
    category_tests = TESTS_BY_CATEGORY[category]
    test_names = list(category_tests.keys())
    
    if abnormal_count + borderline_count > len(test_names):
        print(f"❌ Total abnormal ({abnormal_count}) + borderline ({borderline_count}) exceeds available tests ({len(test_names)})")
        sys.exit(1)
    
    # Assign status to each test
    test_statuses = {}
    remaining_tests = test_names.copy()
    
    # Randomly select abnormal tests
    abnormal_tests = random.sample(remaining_tests, abnormal_count) if abnormal_count > 0 else []
    for t in abnormal_tests:
        remaining_tests.remove(t)
        # Random high or low
        test_statuses[t] = random.choice(["high", "low"])
    
    # Randomly select borderline tests
    borderline_tests = random.sample(remaining_tests, borderline_count) if borderline_count > 0 else []
    for t in borderline_tests:
        remaining_tests.remove(t)
        test_statuses[t] = "borderline"
    
    # Rest are normal
    for t in remaining_tests:
        test_statuses[t] = "normal"
    
    # Initialize test values
    test_values = {}
    for test_name in test_names:
        test_info = category_tests[test_name]
        status = test_statuses[test_name]
        initial_value = generate_value_with_status(
            test_info['ref_low'],
            test_info['ref_high'],
            status
        )
        test_values[test_name] = round_value(initial_value, test_info['unit'])
    
    # Generate reports
    start_date = date.today() - timedelta(days=interval_days * (num_reports - 1))
    
    for report_num in range(num_reports):
        report_date = start_date + timedelta(days=interval_days * report_num)
        
        # Prepare test data for this report
        tests_data = []
        for test_name in test_names:
            test_info = category_tests[test_name]
            value = test_values[test_name]
            
            tests_data.append({
                'name': test_name,
                'value': value,
                'unit': test_info['unit'],
                'ref_low': test_info['ref_low'],
                'ref_high': test_info['ref_high'],
                'status': get_status(value, test_info['ref_low'], test_info['ref_high'])
            })
        
        # Generate PDF
        category_short = category.replace("_", "")
        filename = f"{name.replace(' ', '_')}_{category_short}_{report_date.strftime('%Y%m%d')}.pdf"
        output_path = OUTPUT_DIR / filename
        
        create_pdf(name, age, gender, blood_group, category, tests_data, report_date, output_path)
        
        # Count statuses
        status_counts = {"Normal": 0, "High": 0, "Low": 0}
        for test in tests_data:
            status_counts[test['status']] = status_counts.get(test['status'], 0) + 1
        
        status_summary = ", ".join([f"{k}: {v}" for k, v in status_counts.items() if v > 0])
        print(f"✓ {filename} ({status_summary})")
        
        # Improve abnormal/borderline values for next report
        if report_num < num_reports - 1:
            for test_name in test_names:
                status = test_statuses[test_name]
                if status in ["high", "low"]:
                    test_info = category_tests[test_name]
                    current = test_values[test_name]
                    improved = improve_value(
                        current,
                        test_info['ref_low'],
                        test_info['ref_high'],
                        status,
                        improvement_factor=0.25
                    )
                    test_values[test_name] = round_value(improved, test_info['unit'])
    
    print(f"\n✅ Generated {num_reports} {CATEGORY_NAMES[category]} reports in {OUTPUT_DIR}/")
    print(f"   Patient: {name} ({blood_group})")
    print(f"   Category: {CATEGORY_NAMES[category]}")
    print(f"   Abnormal: {abnormal_count}, Borderline: {borderline_count}, Normal: {len(test_names) - abnormal_count - borderline_count}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate category-specific lab reports with realistic value distributions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List categories
  python scripts/generate_progressive_reports.py --list-categories
  
  # Blood Count Panel (all normal)
  python scripts/generate_progressive_reports.py --name "Purva Miglani" --age 28 --gender Female --blood-group "O+" --category blood_count
  
  # Liver Function Test (2 abnormal, 1 borderline)
  python scripts/generate_progressive_reports.py --name "Purva Miglani" --age 28 --gender Female --blood-group "O+" --category liver --abnormal-count 2 --borderline-count 1
  
  # Progressive improvement (3 reports over 3 months)
  python scripts/generate_progressive_reports.py --name "Purva Miglani" --age 28 --gender Female --blood-group "O+" --category metabolic --abnormal-count 2 --reports 3 --interval 30
        """
    )
    
    parser.add_argument("--list-categories", action="store_true", help="List all categories and exit")
    parser.add_argument("--name", help="Patient name")
    parser.add_argument("--age", type=int, help="Patient age")
    parser.add_argument("--gender", choices=["Male", "Female", "Other"], help="Patient gender")
    parser.add_argument("--blood-group", choices=BLOOD_GROUPS, help="Blood group (A+, B+, O+, etc.)")
    parser.add_argument("--category", choices=list(TESTS_BY_CATEGORY.keys()),
                       help="Test category: blood_count, metabolic, liver, thyroid")
    parser.add_argument("--reports", type=int, default=1, help="Number of reports to generate (default: 1)")
    parser.add_argument("--interval", type=int, default=30, help="Days between reports (default: 30)")
    parser.add_argument("--abnormal-count", type=int, default=0, help="Number of abnormal tests (default: 0)")
    parser.add_argument("--borderline-count", type=int, default=0, help="Number of borderline tests (default: 0)")
    
    args = parser.parse_args()
    
    if args.list_categories:
        print("\n📋 Available Test Categories:\n")
        for category, tests in TESTS_BY_CATEGORY.items():
            print(f"\n{category.upper()} - {CATEGORY_NAMES[category]}")
            print("=" * 60)
            for test_name, test_info in tests.items():
                print(f"  • {test_name:30} ({test_info['unit']}, {test_info['ref_low']}-{test_info['ref_high']})")
        print()
        sys.exit(0)
    
    # Validate required arguments
    if not all([args.name, args.age, args.gender, args.blood_group, args.category]):
        parser.error("--name, --age, --gender, --blood-group, and --category are required")
    
    generate_category_reports(
        name=args.name,
        age=args.age,
        gender=args.gender,
        blood_group=args.blood_group,
        category=args.category,
        num_reports=args.reports,
        interval_days=args.interval,
        abnormal_count=args.abnormal_count,
        borderline_count=args.borderline_count,
    )


if __name__ == "__main__":
    main()

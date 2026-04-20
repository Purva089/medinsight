"""
Clean seed script for MedInsight with realistic demo data.

Creates demo patients with:
  - Realistic Indian names
  - Proper demographic data
  - Historical lab results for trend analysis
  - Multiple reports per patient

Usage:
    python scripts/seed_demo_data.py           # Seed demo patients
    python scripts/seed_demo_data.py --reset   # Clear and re-seed

Does NOT depend on Kaggle CSV — all data is defined here.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import bcrypt as _bcrypt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.patient import Patient
from app.models.user import User
from app.models.lab_result import LabResult
from app.models.uploaded_report import UploadedReport

log = get_logger(__name__)


# ── Demo Patient Data ─────────────────────────────────────────────────────────

DEMO_PATIENTS = [
    {
        "name": "Aarav Sharma",
        "email": "aarav.sharma@medinsight.demo",
        "age": 32,
        "gender": "Male",
        "blood_type": "B+",
        "medical_condition": "Type 2 Diabetes",
        "medication": "Metformin 500mg",
    },
    {
        "name": "Priya Patel",
        "email": "priya.patel@medinsight.demo",
        "age": 28,
        "gender": "Female",
        "blood_type": "O+",
        "medical_condition": "Hypothyroidism",
        "medication": "Levothyroxine 50mcg",
    },
    {
        "name": "Rahul Verma",
        "email": "rahul.verma@medinsight.demo",
        "age": 45,
        "gender": "Male",
        "blood_type": "A+",
        "medical_condition": "Fatty Liver",
        "medication": "None",
    },
    {
        "name": "Anjali Singh",
        "email": "anjali.singh@medinsight.demo",
        "age": 35,
        "gender": "Female",
        "blood_type": "AB+",
        "medical_condition": "Anemia",
        "medication": "Iron supplements",
    },
    {
        "name": "Vikram Reddy",
        "email": "vikram.reddy@medinsight.demo",
        "age": 52,
        "gender": "Male",
        "blood_type": "O-",
        "medical_condition": "Hypertension",
        "medication": "Amlodipine 5mg",
    },
    {
        "name": "Neha Gupta",
        "email": "neha.gupta@medinsight.demo",
        "age": 29,
        "gender": "Female",
        "blood_type": "B+",
        "medical_condition": "None",
        "medication": "None",
    },
    {
        "name": "Arjun Nair",
        "email": "arjun.nair@medinsight.demo",
        "age": 41,
        "gender": "Male",
        "blood_type": "A-",
        "medical_condition": "Pre-diabetes",
        "medication": "Lifestyle management",
    },
    {
        "name": "Kavya Iyer",
        "email": "kavya.iyer@medinsight.demo",
        "age": 38,
        "gender": "Female",
        "blood_type": "O+",
        "medical_condition": "Thyroid nodule",
        "medication": "Under observation",
    },
    {
        "name": "Rohan Mehta",
        "email": "rohan.mehta@medinsight.demo",
        "age": 55,
        "gender": "Male",
        "blood_type": "AB-",
        "medical_condition": "Chronic liver disease",
        "medication": "Ursodeoxycholic acid",
    },
    {
        "name": "Simran Kaur",
        "email": "simran.kaur@medinsight.demo",
        "age": 25,
        "gender": "Female",
        "blood_type": "B-",
        "medical_condition": "None",
        "medication": "None",
    },
]

# Lab test reference ranges and typical values
LAB_TESTS = {
    # Blood Count
    "Hemoglobin": {
        "unit": "g/dL",
        "ref_low": 12.0,
        "ref_high": 16.0,
        "category": "blood_count",
        "normal_range": (12.5, 15.5),
        "abnormal_low": (8.0, 11.5),
        "abnormal_high": (16.5, 18.0),
    },
    "RBC Count": {
        "unit": "million/µL",
        "ref_low": 4.0,
        "ref_high": 5.5,
        "category": "blood_count",
        "normal_range": (4.2, 5.2),
        "abnormal_low": (3.0, 3.9),
        "abnormal_high": (5.6, 6.5),
    },
    "WBC Count": {
        "unit": "cells/µL",
        "ref_low": 4000,
        "ref_high": 11000,
        "category": "blood_count",
        "normal_range": (5000, 9000),
        "abnormal_low": (2000, 3800),
        "abnormal_high": (11500, 15000),
    },
    "Platelet Count": {
        "unit": "lakh/µL",
        "ref_low": 1.5,
        "ref_high": 4.0,
        "category": "blood_count",
        "normal_range": (1.8, 3.5),
        "abnormal_low": (0.5, 1.4),
        "abnormal_high": (4.2, 6.0),
    },
    # Metabolic
    "Fasting Blood Glucose": {
        "unit": "mg/dL",
        "ref_low": 70,
        "ref_high": 100,
        "category": "metabolic",
        "normal_range": (75, 95),
        "abnormal_low": (50, 68),
        "abnormal_high": (110, 180),
    },
    "HbA1c": {
        "unit": "%",
        "ref_low": 4.0,
        "ref_high": 5.6,
        "category": "metabolic",
        "normal_range": (4.5, 5.4),
        "abnormal_low": (3.5, 4.3),
        "abnormal_high": (6.0, 9.5),
    },
    # Liver
    "SGPT (ALT)": {
        "unit": "U/L",
        "ref_low": 7,
        "ref_high": 56,
        "category": "liver",
        "normal_range": (15, 45),
        "abnormal_low": (3, 6),
        "abnormal_high": (65, 150),
    },
    "SGOT (AST)": {
        "unit": "U/L",
        "ref_low": 10,
        "ref_high": 40,
        "category": "liver",
        "normal_range": (15, 35),
        "abnormal_low": (5, 9),
        "abnormal_high": (50, 120),
    },
    "Total Bilirubin": {
        "unit": "mg/dL",
        "ref_low": 0.1,
        "ref_high": 1.2,
        "category": "liver",
        "normal_range": (0.3, 1.0),
        "abnormal_low": (0.05, 0.2),
        "abnormal_high": (1.5, 3.5),
    },
    "Alkaline Phosphatase": {
        "unit": "U/L",
        "ref_low": 44,
        "ref_high": 147,
        "category": "liver",
        "normal_range": (60, 120),
        "abnormal_low": (20, 40),
        "abnormal_high": (160, 300),
    },
    # Thyroid
    "TSH": {
        "unit": "mIU/L",
        "ref_low": 0.4,
        "ref_high": 4.0,
        "category": "thyroid",
        "normal_range": (1.0, 3.5),
        "abnormal_low": (0.1, 0.35),
        "abnormal_high": (5.0, 15.0),
    },
    "Free T3": {
        "unit": "pg/mL",
        "ref_low": 2.0,
        "ref_high": 4.4,
        "category": "thyroid",
        "normal_range": (2.5, 4.0),
        "abnormal_low": (1.2, 1.9),
        "abnormal_high": (4.8, 7.0),
    },
    "Free T4": {
        "unit": "ng/dL",
        "ref_low": 0.8,
        "ref_high": 1.8,
        "category": "thyroid",
        "normal_range": (1.0, 1.6),
        "abnormal_low": (0.4, 0.75),
        "abnormal_high": (2.0, 3.5),
    },
}

# Patient-specific test profiles (which tests each patient typically gets)
PATIENT_TEST_PROFILES = {
    "Type 2 Diabetes": ["Hemoglobin", "Fasting Blood Glucose", "HbA1c", "SGPT (ALT)", "SGOT (AST)"],
    "Hypothyroidism": ["TSH", "Free T3", "Free T4", "Hemoglobin"],
    "Fatty Liver": ["SGPT (ALT)", "SGOT (AST)", "Total Bilirubin", "Alkaline Phosphatase", "Hemoglobin"],
    "Anemia": ["Hemoglobin", "RBC Count", "WBC Count", "Platelet Count"],
    "Hypertension": ["Hemoglobin", "Fasting Blood Glucose", "SGPT (ALT)", "SGOT (AST)"],
    "None": ["Hemoglobin", "RBC Count", "WBC Count", "Fasting Blood Glucose", "SGPT (ALT)"],
    "Pre-diabetes": ["Fasting Blood Glucose", "HbA1c", "Hemoglobin", "SGPT (ALT)"],
    "Thyroid nodule": ["TSH", "Free T3", "Free T4", "Hemoglobin"],
    "Chronic liver disease": ["SGPT (ALT)", "SGOT (AST)", "Total Bilirubin", "Alkaline Phosphatase", "Hemoglobin"],
}


def _hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def _generate_value(test_info: dict, status: str = "normal") -> float:
    """Generate a realistic test value based on status."""
    if status == "normal":
        low, high = test_info["normal_range"]
    elif status == "low":
        low, high = test_info["abnormal_low"]
    elif status == "high":
        low, high = test_info["abnormal_high"]
    else:
        low, high = test_info["normal_range"]
    
    value = random.uniform(low, high)
    # Round appropriately
    if test_info["unit"] in ("cells/µL", "U/L"):
        return round(value)
    return round(value, 2)


def _determine_status(value: float, ref_low: float, ref_high: float) -> str:
    """Determine status based on value and reference range."""
    if value < ref_low:
        return "low"
    elif value > ref_high:
        return "high"
    return "normal"


def _get_test_status_for_patient(condition: str, test_name: str) -> str:
    """Get appropriate status for a patient's condition."""
    # Patients with conditions tend to have certain abnormal values
    abnormal_mapping = {
        "Type 2 Diabetes": {"Fasting Blood Glucose": "high", "HbA1c": "high"},
        "Hypothyroidism": {"TSH": "high", "Free T3": "low", "Free T4": "low"},
        "Fatty Liver": {"SGPT (ALT)": "high", "SGOT (AST)": "high"},
        "Anemia": {"Hemoglobin": "low", "RBC Count": "low"},
        "Pre-diabetes": {"Fasting Blood Glucose": "high", "HbA1c": "high"},
        "Chronic liver disease": {"SGPT (ALT)": "high", "SGOT (AST)": "high", "Total Bilirubin": "high"},
    }
    
    # 70% chance of abnormal if it matches condition, otherwise mostly normal
    if condition in abnormal_mapping and test_name in abnormal_mapping[condition]:
        return abnormal_mapping[condition][test_name] if random.random() < 0.7 else "normal"
    return "normal" if random.random() < 0.85 else random.choice(["low", "high"])


async def _clear_demo_data(session: AsyncSession) -> None:
    """Clear all demo data (users with @medinsight.demo email)."""
    result = await session.execute(
        select(User).where(User.email.like("%@medinsight.demo"))
    )
    users = result.scalars().all()
    count = len(users)

    if count == 0:
        log.info("no demo data to clear")
        return

    await session.execute(
        delete(User).where(User.email.like("%@medinsight.demo"))
    )
    await session.commit()
    log.info("demo data cleared", users_deleted=count)


async def _seed_patients(session: AsyncSession) -> None:
    """Seed demo patients with historical lab results."""
    hashed_password = _hash_password(settings.seed_demo_password)
    today = date.today()

    for patient_data in DEMO_PATIENTS:
        email = patient_data["email"]
        
        # Check if already exists
        existing = await session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            log.info("patient already exists", email=email)
            continue

        # Create User
        user = User(
            email=email,
            hashed_password=hashed_password,
            full_name=patient_data["name"],
            role="patient",
            is_active=True,
        )
        session.add(user)
        await session.flush()

        # Create Patient
        patient = Patient(
            user_id=user.user_id,
            name=patient_data["name"],
            age=patient_data["age"],
            gender=patient_data["gender"],
            blood_type=patient_data["blood_type"],
            medical_condition=patient_data["medical_condition"],
            medication=patient_data["medication"],
        )
        session.add(patient)
        await session.flush()

        # Get test profile for this patient's condition
        condition = patient_data["medical_condition"]
        test_names = PATIENT_TEST_PROFILES.get(condition, PATIENT_TEST_PROFILES["None"])

        # Create 3 historical reports (3 months ago, 1 month ago, current)
        report_dates = [
            today - timedelta(days=90),  # 3 months ago
            today - timedelta(days=30),  # 1 month ago
            today,                        # Current
        ]

        for report_date in report_dates:
            # Create uploaded report
            report = UploadedReport(
                patient_id=patient.patient_id,
                file_name=f"LabReport_{patient_data['name'].replace(' ', '_')}_{report_date.isoformat()}.pdf",
                file_hash=uuid.uuid4().hex,
                storage_path=f"seed_data/{patient.patient_id}/{report_date.isoformat()}.pdf",
                extraction_status="completed",
                extraction_confidence=0.95,
                tests_extracted=len(test_names),
            )
            session.add(report)
            await session.flush()

            # Create lab results for each test
            for test_name in test_names:
                test_info = LAB_TESTS[test_name]
                status = _get_test_status_for_patient(condition, test_name)
                value = _generate_value(test_info, status)
                actual_status = _determine_status(value, test_info["ref_low"], test_info["ref_high"])

                lab_result = LabResult(
                    patient_id=patient.patient_id,
                    report_id=report.report_id,
                    test_name=test_name,
                    value=value,
                    unit=test_info["unit"],
                    reference_range_low=test_info["ref_low"],
                    reference_range_high=test_info["ref_high"],
                    status=actual_status,
                    category=test_info["category"],
                    report_date=report_date,
                )
                session.add(lab_result)

        await session.commit()
        log.info(
            "patient seeded",
            name=patient_data["name"],
            email=email,
            condition=condition,
            reports=len(report_dates),
            tests_per_report=len(test_names),
        )

    log.info("seeding complete", total_patients=len(DEMO_PATIENTS))


async def main(reset: bool = False) -> None:
    print("\n" + "=" * 60)
    print("  MedInsight Demo Data Seeder")
    print("=" * 60 + "\n")

    async with AsyncSessionLocal() as session:
        if reset:
            print("Clearing existing demo data...")
            await _clear_demo_data(session)
            print("✓ Demo data cleared\n")

        print("Seeding demo patients...")
        await _seed_patients(session)
        print("\n✓ Demo patients seeded successfully!")

    print("\n" + "=" * 60)
    print("  Demo Credentials")
    print("=" * 60)
    print(f"  Password: {settings.seed_demo_password}")
    print("\n  Emails:")
    for p in DEMO_PATIENTS:
        print(f"    - {p['email']}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo data for MedInsight")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear existing demo data before seeding",
    )
    args = parser.parse_args()
    asyncio.run(main(reset=args.reset))

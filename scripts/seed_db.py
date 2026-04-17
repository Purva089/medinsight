"""
Seed script for MedInsight Stage 1.

Usage:
    python scripts/seed_db.py           # seed N patients (idempotent)
    python scripts/seed_db.py --reset   # wipe seeded rows and re-seed

CSV location   : data/raw/healthcare_dataset.csv
Column list    : settings.patient_columns  (from config/settings.yml)
Patient count  : settings.seed_demo_patient_count
Demo password  : settings.seed_demo_password
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import sys
from pathlib import Path

# ensure project root is importable when run as a script
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import bcrypt as _bcrypt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
import app.models  # noqa: F401 — registers ALL models in SQLAlchemy's mapper registry
from app.models.patient import Patient
from app.models.user import User

log = get_logger(__name__)


def _hash_password(plain: str) -> str:
    """Return a bcrypt hash of the given plaintext password."""
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def _parse_date(val: object) -> datetime.date | None:
    """Convert a raw CSV value to a date, returning None for missing or unparseable entries."""
    try:
        if pd.isna(val):  # type: ignore[arg-type]
            return None
    except (TypeError, ValueError):
        pass
    try:
        return pd.to_datetime(str(val)).date()
    except Exception:
        return None


def _load_csv() -> pd.DataFrame:
    """
    Load the Kaggle healthcare CSV and return only the columns listed in config.

    Raises FileNotFoundError with a clear message if the file is missing so the
    operator knows exactly where to put the dataset.
    """
    csv_path = _ROOT / "data" / "raw" / "healthcare_dataset.csv"
    if not csv_path.exists():
        log.error(
            "CSV not found — place the Kaggle dataset at the path below",
            expected_path=str(csv_path),
        )
        raise FileNotFoundError(
            f"healthcare_dataset.csv not found at: {csv_path}\n"
            "Download from Kaggle and place it at data/raw/healthcare_dataset.csv"
        )

    df = pd.read_csv(csv_path, usecols=settings.patient_columns)
    log.info("CSV loaded", rows=len(df), columns=list(df.columns))
    return df


async def _reset_seeded_data(session: AsyncSession) -> None:
    """
    Delete all demo users (and their patients via CASCADE) created by this script.

    Matches users whose email follows the pattern patient{n}@medinsight.demo.
    """
    result = await session.execute(
        select(User).where(User.email.like("%@medinsight.demo"))
    )
    users = result.scalars().all()
    count = len(users)

    if count == 0:
        log.info("reset requested but no seeded users found — nothing to delete")
        return

    await session.execute(
        delete(User).where(User.email.like("%@medinsight.demo"))
    )
    await session.commit()
    log.info("seeded data cleared", users_deleted=count)


async def _seed(session: AsyncSession, df: pd.DataFrame) -> None:
    """
    Insert demo users and patients from the first N rows of the dataframe.

    Idempotent — skips rows where the email already exists.
    Individual row failures are logged as warnings and skipped; they do not
    abort the entire seed run.
    """
    n = settings.seed_demo_patient_count
    hashed = _hash_password(settings.seed_demo_password)

    seeded = 0
    skipped = 0

    for i, row in enumerate(df.head(n).itertuples(index=False), start=1):
        email = f"patient{i}@medinsight.demo"

        # idempotency check — skip if already present
        existing = await session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none() is not None:
            log.warning("already exists, skipping", email=email)
            skipped += 1
            continue

        try:
            user = User(
                email=email,
                hashed_password=hashed,
                full_name=str(getattr(row, "Name", f"Patient {i}")),
                role="patient",
                is_active=True,
            )
            session.add(user)
            await session.flush()  # resolve user_id before creating patient

            # pandas replaces spaces in column names with underscores in namedtuples
            patient = Patient(
                user_id=user.user_id,
                name=str(getattr(row, "Name", "")),
                age=(
                    int(getattr(row, "Age", 0))
                    if not pd.isna(getattr(row, "Age", None))
                    else None
                ),
                gender=str(getattr(row, "Gender", "")),
                blood_type=str(
                    getattr(row, "Blood_Type", getattr(row, "Blood Type", ""))
                ),
                medical_condition=str(
                    getattr(row, "Medical_Condition", getattr(row, "Medical Condition", ""))
                ),
                medication=str(getattr(row, "Medication", "")),
            )
            session.add(patient)
            await session.commit()

            log.info("patient seeded", index=i, email=email, name=patient.name)
            seeded += 1

        except Exception as exc:
            await session.rollback()
            log.warning("row failed, skipping", row_index=i, error=str(exc))

    log.info(
        "seeding complete",
        seeded=seeded,
        skipped=skipped,
        total_attempted=n,
    )


async def main(reset: bool = False) -> None:
    """Entry point — optionally resets, then seeds using the shared session factory."""
    df = _load_csv()  # raises FileNotFoundError with ERROR log if CSV missing

    try:
        async with AsyncSessionLocal() as session:
            if reset:
                log.info("--reset flag detected, clearing existing seeded data")
                await _reset_seeded_data(session)

            await _seed(session, df)
    except Exception as exc:
        log.critical("database connection or session error during seed", error=str(exc))
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed MedInsight demo data")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all previously seeded demo rows before re-seeding",
    )
    args = parser.parse_args()

    asyncio.run(main(reset=args.reset))

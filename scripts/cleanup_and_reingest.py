"""
Data cleanup script for MedInsight.

Run this to:
1. Delete old MedlinePlus files (outside 4 categories)
2. Clear pgvector embeddings in Neon
3. Re-ingest knowledge base (medlineplus + clinics)

Usage:
    python scripts/cleanup_and_reingest.py
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import text
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.categories import MEDLINEPLUS_CATEGORY_MAP

log = get_logger(__name__)

MEDLINEPLUS_DIR = _ROOT / "data" / "knowledge_base" / "medlineplus"

# Files to KEEP (from MEDLINEPLUS_CATEGORY_MAP)
KEEP_FILES = {f"{stem}.txt" for stem in MEDLINEPLUS_CATEGORY_MAP.keys()}


def delete_unused_medlineplus() -> list[str]:
    """Delete MedlinePlus files not in the 4-category map."""
    deleted = []
    if not MEDLINEPLUS_DIR.exists():
        log.warning("medlineplus_dir_missing", path=str(MEDLINEPLUS_DIR))
        return deleted

    for path in MEDLINEPLUS_DIR.glob("*.txt"):
        if path.name not in KEEP_FILES:
            log.info("deleting_file", file=path.name)
            path.unlink()
            deleted.append(path.name)

    return deleted


async def clear_pgvector() -> int:
    """Delete all rows from the pgvector embeddings table."""
    table_name = f"data_{settings.vector_store_collection_name}"
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(f"SELECT COUNT(*) FROM {table_name}")  # noqa: S608
        )
        count_before = result.scalar() or 0

        await session.execute(text(f"TRUNCATE TABLE {table_name}"))  # noqa: S608
        await session.commit()

        log.info("pgvector_cleared", table=table_name, rows_deleted=count_before)
        return count_before


async def clear_lab_results() -> int:
    """Delete all lab_results (optional — if you want fresh patient data)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM lab_results"))
        count = result.scalar() or 0
        if count > 0:
            await session.execute(text("TRUNCATE TABLE lab_results CASCADE"))
            await session.commit()
            log.info("lab_results_cleared", rows_deleted=count)
        return count


async def clear_uploaded_reports() -> int:
    """Delete all uploaded_reports (optional)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM uploaded_reports"))
        count = result.scalar() or 0
        if count > 0:
            await session.execute(text("TRUNCATE TABLE uploaded_reports CASCADE"))
            await session.commit()
            log.info("uploaded_reports_cleared", rows_deleted=count)
        return count


async def clear_consultations() -> int:
    """Delete all consultations (chat history)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM consultations"))
        count = result.scalar() or 0
        if count > 0:
            await session.execute(text("TRUNCATE TABLE consultations CASCADE"))
            await session.commit()
            log.info("consultations_cleared", rows_deleted=count)
        return count


async def main(args: argparse.Namespace) -> None:
    print("\n" + "=" * 60)
    print("  MedInsight Data Cleanup")
    print("=" * 60 + "\n")

    # Step 1: Delete unused MedlinePlus files
    if args.delete_files:
        print("Step 1: Deleting unused MedlinePlus files...")
        deleted = delete_unused_medlineplus()
        print(f"  ✓ Deleted {len(deleted)} files")
        for f in deleted[:10]:  # Show first 10
            print(f"    - {f}")
        if len(deleted) > 10:
            print(f"    ... and {len(deleted) - 10} more")
        print()

    # Step 2: Clear pgvector embeddings
    if args.clear_vectors:
        print("Step 2: Clearing pgvector embeddings...")
        try:
            count = await clear_pgvector()
            print(f"  ✓ Cleared {count} embedding rows")
        except Exception as e:
            print(f"  ✗ Error: {e}")
        print()

    # Step 3: Clear patient data (optional)
    if args.clear_patient_data:
        print("Step 3: Clearing patient data...")
        try:
            c1 = await clear_lab_results()
            c2 = await clear_uploaded_reports()
            c3 = await clear_consultations()
            print(f"  ✓ Cleared {c1} lab_results, {c2} reports, {c3} consultations")
        except Exception as e:
            print(f"  ✗ Error: {e}")
        print()

    print("=" * 60)
    print("  Cleanup complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Run migrations:    alembic upgrade head")
    print("  2. Re-ingest KB:      python scripts/ingest_knowledge_base.py")
    print("  3. Re-seed patients:  python scripts/seed_db.py --reset")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MedInsight data cleanup")
    parser.add_argument(
        "--delete-files",
        action="store_true",
        help="Delete unused MedlinePlus .txt files",
    )
    parser.add_argument(
        "--clear-vectors",
        action="store_true",
        help="Clear all pgvector embeddings in Neon",
    )
    parser.add_argument(
        "--clear-patient-data",
        action="store_true",
        help="Clear lab_results, uploaded_reports, consultations",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Do everything (delete files + clear vectors + clear patient data)",
    )
    args = parser.parse_args()

    if args.all:
        args.delete_files = True
        args.clear_vectors = True
        args.clear_patient_data = True

    if not (args.delete_files or args.clear_vectors or args.clear_patient_data):
        parser.print_help()
        print("\nError: Specify at least one action (--delete-files, --clear-vectors, --clear-patient-data, or --all)")
        sys.exit(1)

    asyncio.run(main(args))

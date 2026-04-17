"""Quick data inspection script — run after uploading a current PDF."""
import asyncio
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

async def check():
    async with AsyncSessionLocal() as db:

        # --- Summary counts ---
        print("=== TABLE COUNTS ===")
        for table in ["users", "patients", "lab_results", "uploaded_reports", "consultations"]:
            count = (await db.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar()
            print(f"  {table:25s}: {count} rows")

        # --- Lab results count + dates per patient ---
        print("\n=== LAB RESULTS PER PATIENT (dates show historical vs current) ===")
        q = (
            "SELECT p.name, COUNT(lr.result_id) as cnt, "
            "STRING_AGG(DISTINCT lr.report_date::text, ', ' ORDER BY lr.report_date::text) as dates "
            "FROM patients p LEFT JOIN lab_results lr ON lr.patient_id = p.patient_id "
            "GROUP BY p.patient_id, p.name ORDER BY p.name"
        )
        rows = (await db.execute(text(q))).fetchall()
        for r in rows:
            print(f"  {str(r.name):25s}: {r.cnt:3d} results on dates: {r.dates}")

        # --- Uploaded reports ---
        print("\n=== UPLOADED REPORTS ===")
        q2 = (
            "SELECT p.name, ur.file_name, ur.extraction_status, ur.tests_extracted, ur.created_at "
            "FROM uploaded_reports ur JOIN patients p ON p.patient_id = ur.patient_id "
            "ORDER BY ur.created_at DESC LIMIT 10"
        )
        reports = (await db.execute(text(q2))).fetchall()
        if not reports:
            print("  No uploaded reports yet — upload a current/ PDF via POST /api/v1/reports/upload")
        for r in reports:
            print(f"  {str(r.name):20s} | {r.file_name:50s} | {r.extraction_status} | {r.tests_extracted} tests")

        # --- Consultations ---
        print("\n=== RECENT CONSULTATIONS ===")
        q3 = (
            "SELECT p.name, c.question, c.intent_handled, c.confidence_level, c.created_at "
            "FROM consultations c JOIN patients p ON p.patient_id = c.patient_id "
            "ORDER BY c.created_at DESC LIMIT 5"
        )
        chats = (await db.execute(text(q3))).fetchall()
        if not chats:
            print("  No consultations yet — ask a question via POST /api/v1/chat/ask")
        for c in chats:
            print(f"  {str(c.name):20s} | {c.intent_handled:10s} | {c.confidence_level:6s} | Q: {str(c.question)[:60]}")

asyncio.run(check())

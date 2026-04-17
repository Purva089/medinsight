"""Delete failed uploaded_reports so the same PDF can be re-uploaded."""
import asyncio
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

async def fix():
    async with AsyncSessionLocal() as db:
        q = "DELETE FROM uploaded_reports WHERE extraction_status = 'failed' RETURNING report_id, file_name"
        result = await db.execute(text(q))
        deleted = result.fetchall()
        await db.commit()
        if deleted:
            for r in deleted:
                print(f"Deleted failed report: {r.report_id}  ({r.file_name})")
        else:
            print("No failed reports — nothing to clean up.")

asyncio.run(fix())

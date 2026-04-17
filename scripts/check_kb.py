"""Check what's actually in the pgvector knowledge base."""
import asyncio
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

async def check():
    async with AsyncSessionLocal() as conn:
        # Find all tables
        tables = (await conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        ))).fetchall()
        print("All tables:", [t[0] for t in tables])

        # Try querying the vector store table
        for tname in [t[0] for t in tables]:
            if any(k in tname for k in ['kb', 'embed', 'vector', 'node', 'medinsight', 'llama', 'data_']):
                try:
                    r = (await conn.execute(text(
                        f"SELECT metadata_->>'source_type' as src, COUNT(*) as cnt "
                        f"FROM {tname} GROUP BY src ORDER BY cnt DESC"
                    ))).fetchall()
                    print(f"\nTable '{tname}' — chunks by source_type:")
                    for row in r:
                        print(f"  {row.src}: {row.cnt} chunks")
                except Exception as e:
                    print(f"  Table '{tname}': {e}")

asyncio.run(check())


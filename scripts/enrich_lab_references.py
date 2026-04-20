#!/usr/bin/env python3
"""
Enrich lab_references table with clinical data using LLM.

This script:
1. Reads all lab_references rows with NULL enrichment columns
2. Uses LLM to extract: unit, advice, causes_high, causes_low, specialist_type, retesting_urgency
3. Updates the database with enriched data

Usage:
    python scripts/enrich_lab_references.py [--limit N] [--force]
    
    --limit N: Only process N tests (for testing)
    --force: Re-enrich all tests even if already enriched
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.categories import classify_test
from app.core.database import AsyncSessionLocal
from app.models.lab_reference import LabReference
from app.services.llm_service import llm_service

# Prompt to extract enrichment data from raw_content
ENRICHMENT_PROMPT = """
You are a medical data extraction expert. Extract structured information from this lab test description.

Test Name: {test_name}
Description: {description}
Full Content: {raw_content}

Extract the following information in JSON format:
1. unit: Common unit of measurement (e.g., "mg/dL", "mmol/L", "%", "cells/μL")
2. range_low: Lower bound of normal reference range (number only, or null if not found)
3. range_high: Upper bound of normal reference range (number only, or null if not found)
4. advice: Brief actionable advice for abnormal values (1-2 sentences)
5. causes_high: Main causes of high values (comma-separated list, max 5)
6. causes_low: Main causes of low values (comma-separated list, max 5)
7. specialist_type: Which specialist to consult (e.g., "Cardiologist", "Endocrinologist")
8. retesting_urgency: When to retest - one of: "immediate", "1-week", "1-month", "3-months", "as-needed"

Return ONLY valid JSON with these exact keys. Use null for missing data.

Example:
{{
  "unit": "mg/dL",
  "range_low": 70,
  "range_high": 100,
  "advice": "Maintain healthy diet and regular exercise. Consult doctor if persistently abnormal.",
  "causes_high": "Diabetes, Stress, Medications, Cushing's syndrome, Pancreatitis",
  "causes_low": "Insulin overdose, Liver disease, Alcohol, Prolonged fasting, Adrenal insufficiency",
  "specialist_type": "Endocrinologist",
  "retesting_urgency": "1-month"
}}

Now extract for the test above:
"""


async def enrich_single_test(
    session: AsyncSession,
    test: LabReference,
    force: bool = False
) -> tuple[str, bool, str]:
    """
    Enrich a single lab test reference.
    
    Returns: (test_name, success, message)
    """
    test_name = test.test_name
    
    # Skip if already enriched (unless force=True)
    if not force and test.unit is not None:
        return (test_name, True, "Already enriched (skipped)")
    
    # Prepare content for LLM
    description = test.description or ""
    raw_content = test.raw_content or ""
    
    if not description and not raw_content:
        return (test_name, False, "No content available")
    
    # Truncate content if too long (max 3000 chars for LLM)
    content_excerpt = (description + "\n\n" + raw_content)[:3000]
    
    prompt = ENRICHMENT_PROMPT.format(
        test_name=test_name,
        description=description[:500],
        raw_content=content_excerpt
    )
    
    try:
        # Call LLM for extraction
        response = await llm_service.call_reasoning(
            prompt,
            max_tokens_key="extraction"
        )
        
        # Strip markdown code blocks if present
        response = response.strip()
        if response.startswith("```"):
            # Remove ``` json or just ```
            lines = response.split("\n")
            # Remove first line (``` or ```json)
            lines = lines[1:]
            # Remove last line if it's ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            response = "\n".join(lines).strip()
        
        # Parse JSON response
        data = json.loads(response)
        
        # Update category using classify_test
        category = classify_test(test_name)
        
        # Update database
        stmt = (
            update(LabReference)
            .where(LabReference.reference_id == test.reference_id)
            .values(
                category=category,
                unit=data.get("unit"),
                range_low=data.get("range_low"),
                range_high=data.get("range_high"),
                advice=data.get("advice"),
                causes_high=data.get("causes_high"),
                causes_low=data.get("causes_low"),
                specialist_type=data.get("specialist_type"),
                retesting_urgency=data.get("retesting_urgency"),
            )
        )
        await session.execute(stmt)
        await session.commit()
        
        return (test_name, True, "✅ Enriched successfully")
    
    except json.JSONDecodeError as e:
        return (test_name, False, f"JSON parse error: {e}")
    except Exception as e:
        return (test_name, False, f"Error: {e}")


async def enrich_all_tests(limit: int | None = None, force: bool = False) -> None:
    """Enrich all lab references with LLM-extracted clinical data."""
    
    print("=" * 70)
    print("LAB REFERENCES ENRICHMENT")
    print("=" * 70)
    
    async with AsyncSessionLocal() as session:
        # Get tests to enrich
        stmt = select(LabReference)
        if not force:
            stmt = stmt.where(LabReference.unit.is_(None))
        if limit:
            stmt = stmt.limit(limit)
        
        result = await session.execute(stmt)
        tests = result.scalars().all()
        
        total = len(tests)
        
        if total == 0:
            print("\n✅ All tests are already enriched!")
            print("   Use --force to re-enrich all tests")
            return
        
        print(f"\n📊 Found {total} tests to enrich")
        if limit:
            print(f"   (Limited to {limit} tests)")
        print("\nProcessing...\n")
        
        # Process each test
        success_count = 0
        fail_count = 0
        
        for idx, test in enumerate(tests, 1):
            test_name, success, message = await enrich_single_test(
                session, test, force
            )
            
            # Display progress
            status = "✅" if success else "❌"
            print(f"[{idx:3}/{total}] {status} {test_name:40} - {message}")
            
            if success:
                success_count += 1
            else:
                fail_count += 1
            
            # Small delay to avoid rate limiting
            if idx < total:
                await asyncio.sleep(0.5)
        
        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"✅ Successfully enriched: {success_count}/{total}")
        if fail_count > 0:
            print(f"❌ Failed: {fail_count}/{total}")
        print("\n💡 Tip: Run scripts/check_db_status.py to verify enrichment")
        print("=" * 70)


def main():
    """Parse arguments and run enrichment."""
    parser = argparse.ArgumentParser(
        description="Enrich lab_references with clinical data using LLM"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Only process N tests (for testing)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-enrich all tests even if already enriched",
    )
    
    args = parser.parse_args()
    
    asyncio.run(enrich_all_tests(limit=args.limit, force=args.force))


if __name__ == "__main__":
    main()

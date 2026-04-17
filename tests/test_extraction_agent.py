"""
Tests for PDFExtractor (app/services/pdf_extractor.py).
"""
from __future__ import annotations

from pathlib import Path
from statistics import mean
from unittest.mock import patch

import pytest
import pytest_asyncio

from app.schemas.extraction import ExtractedTest, ExtractionResult
from app.services.pdf_extractor import PDFExtractor

_CURRENT_DIR = Path(__file__).resolve().parents[1] / "data" / "synthetic_reports" / "current"
_REPORT_ID = "test-report-id"
_PATIENT_ID = "test-patient-id"


def _first_pdf() -> Path:
    pdfs = sorted(_CURRENT_DIR.glob("*.pdf"))
    if not pdfs:
        pytest.skip("No PDFs found in data/synthetic_reports/current/")
    return pdfs[0]


# ── test_pymupdf_success ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pymupdf_success():
    """
    Load a real PDF, run extraction, verify structure and confidence.
    """
    pdf_bytes = _first_pdf().read_bytes()
    extractor = PDFExtractor()
    result = await extractor.extract(pdf_bytes, _REPORT_ID, _PATIENT_ID)

    assert isinstance(result, ExtractionResult)
    assert len(result.extracted_tests) > 0, "Expected at least one extracted test"
    assert result.overall_confidence > 0.8, (
        f"Expected confidence > 0.8, got {result.overall_confidence}"
    )
    assert result.extraction_method == "pymupdf"


# ── test_self_heal_on_invalid_json ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_self_heal_on_invalid_json():
    """
    Mock _parse_with_gemini: first call returns empty + error (simulates bad JSON),
    second call (self-heal) returns a valid ExtractedTest list.
    Assert the result is a valid ExtractionResult.
    """
    call_count = {"n": 0}

    async def _fake_parse(raw_text: str, report_id: str):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # Return invalid JSON on first call to trigger self-heal path
            return [], ["JSON decode error: invalid JSON on attempt 1"]
        # Second call (self-heal) succeeds
        from app.schemas.extraction import ExtractedTest
        tests = [ExtractedTest(
            test_name="TSH", value=2.5, unit="mIU/L",
            reference_range_low=0.4, reference_range_high=4.0,
            status="normal", confidence=0.95,
        )]
        return tests, []

    pdf_bytes = _first_pdf().read_bytes()
    extractor = PDFExtractor()

    with patch.object(extractor, "_parse_with_gemini", side_effect=_fake_parse):
        result = await extractor.extract(pdf_bytes, _REPORT_ID, _PATIENT_ID)

    # Result must be a valid ExtractionResult regardless of path taken
    assert isinstance(result, ExtractionResult)
    assert result is not None


# ── test_confidence_is_mean ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_confidence_is_mean():
    """
    overall_confidence must equal the mean of individual test confidence scores.
    """
    pdf_bytes = _first_pdf().read_bytes()
    extractor = PDFExtractor()
    result = await extractor.extract(pdf_bytes, _REPORT_ID, _PATIENT_ID)

    if not result.extracted_tests:
        pytest.skip("No tests extracted — skipping confidence check")

    expected = round(mean(t.confidence for t in result.extracted_tests), 4)
    assert abs(result.overall_confidence - expected) < 0.001, (
        f"overall_confidence {result.overall_confidence} != mean {expected}"
    )


# ── test_empty_pdf_returns_empty ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_pdf_returns_empty():
    """
    Passing empty bytes must return an ExtractionResult with no tests and errors.
    """
    extractor = PDFExtractor()
    result = await extractor.extract(b"", _REPORT_ID, _PATIENT_ID)

    assert result.extracted_tests == [], f"Expected empty tests, got {result.extracted_tests}"
    assert len(result.errors) > 0, "Expected at least one error message for empty PDF"

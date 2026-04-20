"""
Pydantic schemas for the PDF extraction pipeline.

ExtractedTest  — one row from the lab results table inside a PDF.
ExtractionResult — the full result returned by PDFExtractor.extract().
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ExtractedTest(BaseModel):
    """A single lab test extracted from a PDF report."""

    test_name: str
    value: float
    unit: str
    reference_range_low: float | None = None
    reference_range_high: float | None = None
    status: Literal["normal", "high", "low", "critical"]
    confidence: float = Field(ge=0.0, le=1.0)
    category: str = "others"  # populated by pdf_extractor via classify_test()

    @field_validator("test_name", "unit", mode="before")
    @classmethod
    def strip_str(cls, v: object) -> str:
        return str(v).strip()
    
    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: object) -> str:
        """Normalize status to lowercase (LLM sometimes returns capitalized values)."""
        status_str = str(v).strip().lower()
        # Map common variations
        if status_str in ("normal", "norm", "ok"):
            return "normal"
        elif status_str in ("high", "elevated", "h"):
            return "high"
        elif status_str in ("low", "l", "decreased"):
            return "low"
        elif status_str in ("critical", "crit", "abnormal"):
            return "critical"
        return status_str  # Return as-is, will fail Literal validation if invalid

    @field_validator("value", "reference_range_low", "reference_range_high", mode="before")
    @classmethod
    def coerce_float_or_none(cls, v: object) -> float | None:
        if v is None or v == "":
            return None
        try:
            return float(str(v))
        except (TypeError, ValueError):
            return None


class ExtractionResult(BaseModel):
    """Aggregated result returned by PDFExtractor for one PDF file."""

    report_id: str
    patient_id: str
    extracted_tests: list[ExtractedTest] = Field(default_factory=list)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # "pymupdf" when text extraction succeeded; "groq" when Groq parsed it; "regex" for fallback
    extraction_method: Literal["pymupdf", "groq", "regex"] = "pymupdf"
    raw_text: str = ""
    errors: list[str] = Field(default_factory=list)
    
    # Patient demographics extracted from report
    patient_name: str | None = None
    patient_age: int | None = None
    patient_gender: str | None = None

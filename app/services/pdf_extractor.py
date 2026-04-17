"""
PDF extraction service for MedInsight.

PDFExtractor.extract() reads a PDF file's bytes and returns a structured
ExtractionResult with all lab tests found inside.

Pipeline:
  1. Extract raw text with PyMuPDF  (fast, offline)
  2. If text < 50 chars → return empty (scanned PDFs not supported without OCR)
  3. Send text to Groq (llama-3.3-70b) with a structured extraction prompt
  4. Validate JSON response with Pydantic
  5. If validation fails → self-healing: send malformed JSON back to Groq once more
  6. If Groq unavailable → deterministic regex parser fallback
  7. Return ExtractionResult

All LLM settings are read from app/core/config.py via app.core.config.settings.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.core.categories import classify_test
from app.schemas.extraction import ExtractedTest, ExtractionResult

log = get_logger(__name__)

# ── Gemini prompts ────────────────────────────────────────────────────────────

_EXTRACTION_PROMPT = """\
You are a medical data extraction specialist. Extract all lab test results from the following lab report text.

Return ONLY a valid JSON array — no explanation, no markdown, no code fences.
Each object in the array must have exactly these keys:
  - test_name       (string)
  - value           (number)
  - unit            (string)
  - reference_range_low   (number or null)
  - reference_range_high  (number or null)
  - status          (one of: "normal", "high", "low", "critical")
  - confidence      (number between 0.0 and 1.0)

Lab report text:
{text}
"""

_SELF_HEAL_PROMPT = """\
The following JSON is invalid or does not match the required schema. Fix it and return ONLY valid JSON — no explanation, no markdown, no code fences.

Required schema for each array element:
  - test_name       (string)
  - value           (number)
  - unit            (string)
  - reference_range_low   (number or null)
  - reference_range_high  (number or null)
  - status          (one of: "normal", "high", "low", "critical")
  - confidence      (number between 0.0 and 1.0)

Invalid JSON to fix:
{bad_json}
"""


class PDFExtractor:
    """
    Extracts structured lab results from a PDF file.

    Uses PyMuPDF for text extraction then Groq for structured JSON parsing.
    A regex fallback handles cases where Groq is unavailable.
    A self-healing retry handles malformed Groq JSON responses.
    """

    def __init__(self) -> None:
        pass  # no client state needed; Groq client is created per-call

    # ── public API ────────────────────────────────────────────────────────────

    async def extract(
        self,
        file_bytes: bytes,
        report_id: str,
        patient_id: str,
    ) -> ExtractionResult:
        """
        Extract lab tests from a PDF.

        Args:
            file_bytes: Raw bytes of the PDF file.
            report_id:  UUID string of the associated uploaded_report row.
            patient_id: UUID string of the patient.

        Returns:
            ExtractionResult with extracted tests, confidence, method used, and
            any error messages encountered during extraction.
        """
        file_hash = hashlib.md5(file_bytes).hexdigest()
        file_size_kb = round(len(file_bytes) / 1024, 1)

        log.info(
            "extraction_started",
            report_id=report_id,
            patient_id=patient_id,
            file_size_kb=file_size_kb,
            file_hash=file_hash,
        )

        raw_text, method = await self._extract_text(file_bytes)

        if not raw_text.strip():
            log.warning(
                "empty_text_extracted",
                report_id=report_id,
                method=method,
            )
            from typing import cast, Literal as _Literal
            return ExtractionResult(
                report_id=report_id,
                patient_id=patient_id,
                extraction_method=cast(_Literal["pymupdf", "groq", "regex"], method),
                raw_text="",
                errors=["No text could be extracted from the PDF."],
            )

        # Try Groq-powered structured extraction first; fall back to
        # deterministic regex parser if Groq is unavailable.
        try:
            tests, errors = await self._parse_with_groq(raw_text, report_id)
        except RuntimeError as groq_err:
            log.warning(
                "groq_unavailable_using_regex",
                report_id=report_id,
                reason=str(groq_err)[:120],
            )
            tests, errors = self._parse_with_regex(raw_text)
            errors.insert(0, f"Groq unavailable; used regex parser. ({groq_err!s:.80})")

        overall_confidence = (
            round(sum(t.confidence for t in tests) / len(tests), 4)
            if tests
            else 0.0
        )

        # Tag each test with its category (or "others" for unknowns)
        for t in tests:
            category = classify_test(t.test_name)
            # None means excluded — keep as "others" so orchestrator can filter later
            t.category = category if category is not None else "others"

        log.info(
            "extraction_complete",
            report_id=report_id,
            test_count=len(tests),
            overall_confidence=overall_confidence,
            method=method,
        )

        from typing import cast, Literal as _Literal
        return ExtractionResult(
            report_id=report_id,
            patient_id=patient_id,
            extracted_tests=tests,
            overall_confidence=overall_confidence,
            extraction_method=cast(_Literal["pymupdf", "groq", "regex"], method),
            raw_text=raw_text,
            errors=errors,
        )

    # ── text extraction ───────────────────────────────────────────────────────

    async def _extract_text(
        self, file_bytes: bytes
    ) -> tuple[str, str]:
        """
        Extract text using PyMuPDF.
        Returns (raw_text, method) where method is "pymupdf".
        """
        raw_text = ""
        try:
            raw_text = await asyncio.to_thread(self._pymupdf_extract, file_bytes)
            char_count = len(raw_text.strip())
            log.info("pymupdf_success", char_count=char_count)
            if char_count >= 50:
                return raw_text, "pymupdf"
            log.warning("pdf_too_short", char_count=char_count,
                        reason="PDF may be scanned/image-only; text extraction unavailable")
        except Exception as exc:
            log.warning("pymupdf_failed", reason=str(exc))
        return "", "pymupdf"

    @staticmethod
    def _pymupdf_extract(file_bytes: bytes) -> str:
        """Extract all text from a PDF using PyMuPDF (synchronous)."""
        import fitz  # type: ignore[import]

        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            return "\n".join(str(page.get_text("text")) for page in doc)



    # ── Groq structured extraction ────────────────────────────────────────────

    async def _parse_with_groq(
        self, raw_text: str, report_id: str
    ) -> tuple[list[ExtractedTest], list[str]]:
        """
        Send raw_text to Groq (llama-3.3-70b) for structured JSON extraction.
        Much faster and no daily quota limits compared to Gemini.
        Falls back to regex if Groq is unavailable.
        """
        from groq import Groq  # type: ignore[import]

        errors: list[str] = []
        prompt = _EXTRACTION_PROMPT.format(text=raw_text[:6000])  # stay within context

        try:
            client = Groq(api_key=settings.groq_api_key)
            response = await asyncio.to_thread(
                lambda: client.chat.completions.create(
                    model=settings.llm_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=settings.max_tokens_extraction,
                    temperature=settings.llm_temperature,
                )
            )
            response_text = response.choices[0].message.content or ""
        except Exception as exc:
            raise RuntimeError(f"Groq API error during extraction: {exc}") from exc

        tests, parse_error = self._parse_json_response(response_text)
        if parse_error is None:
            return tests, errors

        # Self-heal: ask Groq to fix its own malformed JSON
        errors.append(f"Initial Groq parse failed ({parse_error}); attempting self-heal.")
        heal_prompt = _SELF_HEAL_PROMPT.format(bad_json=response_text)
        try:
            client2 = Groq(api_key=settings.groq_api_key)
            healed = await asyncio.to_thread(
                lambda: client2.chat.completions.create(
                    model=settings.llm_model,
                    messages=[{"role": "user", "content": heal_prompt}],
                    max_tokens=settings.max_tokens_extraction,
                    temperature=0.0,
                )
            )
            healed_text = healed.choices[0].message.content or ""
        except Exception as exc:
            errors.append(f"Groq self-heal failed: {exc}")
            return [], errors

        tests, parse_error2 = self._parse_json_response(healed_text)
        if parse_error2 is None:
            return tests, errors

        errors.append(f"Self-heal also failed: {parse_error2}")
        return self._partial_salvage(response_text, errors), errors

    # ── regex / rule-based fallback parser ──────────────────────────────────

    @staticmethod
    def _parse_with_regex(
        raw_text: str,
    ) -> tuple[list[ExtractedTest], list[str]]:
        """
        Deterministic parser for the known MedInsight reportlab table format.

        The PyMuPDF extraction of our synthetic PDFs produces lines like:
            Test Name\nValue\nUnit\nReference Range\nStatus\n  (header)
            Hemoglobin\n15.22\ng/dL\n12.0 – 17.5\nNORMAL\n  (data rows)

        This parser groups non-header lines into 5-tuples and converts them to
        ExtractedTest objects with confidence=0.95 (deterministic parse).
        """
        _HEADER_TOKENS = {"test name", "value", "unit", "reference range", "status"}
        _STATUS_MAP = {
            "normal": "normal",
            "high": "high",
            "low": "low",
            "critical": "critical",
        }

        lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
        errors: list[str] = []
        tests: list[ExtractedTest] = []

        # Slide a 5-line window; skip header rows
        i = 0
        while i < len(lines):
            # Skip header rows (any line that is one of the header tokens)
            if lines[i].lower() in _HEADER_TOKENS:
                i += 1
                continue

            # Need at least 5 lines for a full row
            if i + 4 >= len(lines):
                break

            # Peek at the next 5 lines
            name_raw, val_raw, unit_raw, ref_raw, stat_raw = lines[i:i + 5]

            # The 2nd token must be numeric and 5th must be a known status
            if stat_raw.lower() not in _STATUS_MAP:
                i += 1
                continue

            try:
                value = float(val_raw)
            except ValueError:
                i += 1
                continue

            # Parse reference range "low – high" (en-dash or hyphen)
            ref_low: float | None = None
            ref_high: float | None = None
            ref_match = re.search(
                r"([\d.]+)\s*[–\-]\s*([\d.]+)", ref_raw
            )
            if ref_match:
                try:
                    ref_low = float(ref_match.group(1))
                    ref_high = float(ref_match.group(2))
                except ValueError:
                    pass

            status_str = _STATUS_MAP[stat_raw.lower()]

            tests.append(
                ExtractedTest(
                    test_name=name_raw,
                    value=value,
                    unit=unit_raw,
                    reference_range_low=ref_low,
                    reference_range_high=ref_high,
                    status=status_str,  # type: ignore[arg-type]
                    confidence=0.95,
                )
            )
            i += 5

        if not tests:
            errors.append("Regex parser found no rows — PDF format may differ from expected.")

        return tests, errors



    # ── JSON parsing helpers ──────────────────────────────────────────────────

    @staticmethod
    def _parse_json_response(
        text: str,
    ) -> tuple[list[ExtractedTest], str | None]:
        """
        Parse an LLM JSON response into validated ExtractedTest objects.

        Returns (tests, None) on success or ([], error_message) on failure.
        """
        # Strip markdown fences if the LLM added them despite instructions
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            return [], f"JSONDecodeError: {exc}"

        if not isinstance(data, list):
            return [], "Response is not a JSON array"

        tests: list[ExtractedTest] = []
        for item in data:
            try:
                tests.append(ExtractedTest.model_validate(item))
            except Exception as exc:
                return [], f"Pydantic validation error: {exc}"

        return tests, None

    @staticmethod
    def _partial_salvage(
        text: str, errors: list[str]
    ) -> list[ExtractedTest]:
        """
        Last-resort: try to parse whatever items are valid from the array,
        marking each with confidence 0.0.
        """
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(
                ln for ln in lines if not ln.startswith("```")
            ).strip()

        try:
            data = json.loads(cleaned)
        except Exception:
            return []

        if not isinstance(data, list):
            return []

        salvaged: list[ExtractedTest] = []
        for item in data:
            try:
                item["confidence"] = 0.0
                salvaged.append(ExtractedTest.model_validate(item))
            except Exception:
                pass  # skip items that still can't be validated

        if salvaged:
            errors.append(
                f"Partial salvage recovered {len(salvaged)} test(s) with confidence 0.0."
            )
        return salvaged


# ── manual smoke test ─────────────────────────────────────────────────────────

async def _test() -> None:
    _ROOT = Path(__file__).resolve().parents[2]
    test_pdf = _ROOT / "data" / "synthetic_reports" / "current"
    # Pick the first PDF available
    pdfs = sorted(test_pdf.glob("*.pdf"))
    if not pdfs:
        print("No PDFs found — run scripts/generate_pdfs.py first.")
        return

    pdf_path = pdfs[0]
    print(f"Testing extraction on: {pdf_path.name}")
    with open(pdf_path, "rb") as f:
        data = f.read()

    result = await PDFExtractor().extract(data, "test-report-id", "test-patient-id")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(_test())

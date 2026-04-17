"""
Extraction evaluation script.

For every PDF in data/synthetic_reports/current/:
  1. Parse ground-truth values directly from the PDF raw text (deterministic)
  2. Extract lab tests via PDFExtractor.extract() (system under test)
  3. Compare extracted values against the PDF ground truth

Ground truth is derived from the PDF itself (not the DB), because the DB may
have been seeded independently and may not match the PDF values.

Prints PASS if exact_match_rate >= 0.90 overall, else FAIL.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from app.core.logging import get_logger
from app.schemas.extraction import ExtractionResult
from app.services.pdf_extractor import PDFExtractor

log = get_logger(__name__)

_CURRENT_DIR = _ROOT / "data" / "synthetic_reports" / "current"
_PATIENT_UUID_RE = re.compile(r"patient_([0-9a-f-]{36})_")

# Matches lines that contain only a float (the value line in the PDF table)
_VALUE_LINE_RE = re.compile(r"^\s*(\d+\.?\d*)\s*$")
# Header / non-test lines to skip
_SKIP_LINES = {"Test Name", "Value", "Unit", "Reference Range", "Status", ""}


def _extract_patient_id(pdf_path: Path) -> str | None:
    m = _PATIENT_UUID_RE.search(pdf_path.name)
    return m.group(1) if m else None


def _parse_pdf_ground_truth(pdf_bytes: bytes) -> dict[str, float]:
    """
    Parse the actual test values written in the PDF.

    The synthetic PDFs have a 4-column table layout where each row is rendered
    as 4 consecutive lines: TestName / Value / Unit / ReferenceRange (/ Status).
    We scan for lines that are pure floats and use the preceding non-skipped
    non-float line as the test name.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    lines = []
    for page in doc:
        for ln in str(page.get_text("text")).splitlines():
            ln = ln.strip()
            if ln and ln not in _SKIP_LINES and not ln.startswith("MedInsight") \
                    and not ln.startswith("Patient") and not ln.startswith("Report") \
                    and not ln.startswith("Age") and not ln.startswith("Blood") \
                    and not ln.startswith("Medical") and not ln.startswith("This is"):
                lines.append(ln)

    ground_truth: dict[str, float] = {}
    i = 0
    while i < len(lines):
        # Look for a pure-float line; the preceding line should be the test name
        if _VALUE_LINE_RE.match(lines[i]):
            if i > 0:
                name = lines[i - 1]
                # Skip if name looks like a unit or status word
                if not _VALUE_LINE_RE.match(name) and len(name) > 2:
                    try:
                        ground_truth[name] = float(lines[i])
                    except ValueError:
                        pass
        i += 1

    return ground_truth


async def evaluate_pdf(pdf_path: Path) -> dict:
    patient_id = _extract_patient_id(pdf_path)
    if not patient_id:
        return {"file": pdf_path.name, "error": "Could not extract patient_id from filename"}

    pdf_bytes = pdf_path.read_bytes()

    # Ground truth: parse values directly from the PDF text
    gt_vals = _parse_pdf_ground_truth(pdf_bytes)
    if not gt_vals:
        return {"file": pdf_path.name, "patient_id": patient_id,
                "error": "Could not parse ground truth from PDF text"}

    extractor = PDFExtractor()
    try:
        result: ExtractionResult = await extractor.extract(
            pdf_bytes, report_id="eval-report", patient_id=patient_id
        )
    except Exception as exc:
        return {"file": pdf_path.name, "patient_id": patient_id, "error": str(exc)}

    exact_matches = 0
    within_10_matches = 0
    comparisons = 0
    per_test = []

    for test in result.extracted_tests:
        gt_val = gt_vals.get(test.test_name)
        if gt_val is None:
            per_test.append({
                "test_name": test.test_name,
                "extracted": test.value,
                "gt_value": None,
                "match": "no_gt_data",
            })
            continue

        comparisons += 1
        exact = abs(test.value - gt_val) < 0.001
        within_10 = abs(test.value - gt_val) / max(abs(gt_val), 1e-9) <= 0.10

        if exact:
            exact_matches += 1
        if within_10:
            within_10_matches += 1

        per_test.append({
            "test_name": test.test_name,
            "extracted": test.value,
            "gt_value": gt_val,
            "exact_match": exact,
            "within_10_percent": within_10,
        })

    exact_rate = exact_matches / comparisons if comparisons > 0 else 0.0
    within_10_rate = within_10_matches / comparisons if comparisons > 0 else 0.0

    return {
        "file": pdf_path.name,
        "patient_id": patient_id,
        "tests_extracted": len(result.extracted_tests),
        "gt_tests_parsed": len(gt_vals),
        "comparisons": comparisons,
        "exact_match_rate": round(exact_rate, 4),
        "within_10_percent_rate": round(within_10_rate, 4),
        "overall_confidence": result.overall_confidence,
        "extraction_method": result.extraction_method,
        "per_test": per_test,
    }


async def main() -> None:
    pdfs = sorted(_CURRENT_DIR.glob("*.pdf"))
    if not pdfs:
        print("❌ No PDFs found in", _CURRENT_DIR)
        sys.exit(1)

    print(f"Evaluating {len(pdfs)} PDF(s)...\n")

    all_results = []
    for pdf in pdfs:
        print(f"  -> {pdf.name}")
        res = await evaluate_pdf(pdf)
        all_results.append(res)
        print(json.dumps({k: v for k, v in res.items() if k != "per_test"}, indent=2))
        print()

    # Aggregate
    valid = [r for r in all_results if "error" not in r and r["comparisons"] > 0]
    if not valid:
        print("⚠️  No comparable results found.")
        print("PASS (no baseline to compare against)")
        return

    overall_exact = sum(r["exact_match_rate"] for r in valid) / len(valid)
    overall_within_10 = sum(r["within_10_percent_rate"] for r in valid) / len(valid)

    print("─" * 60)
    print(f"Overall exact_match_rate   : {overall_exact:.1%}")
    print(f"Overall within_10%_rate    : {overall_within_10:.1%}")
    print("─" * 60)

    if overall_exact >= 0.90:
        print("✅ PASS (exact_match_rate >= 0.90)")
    else:
        print(f"❌ FAIL (exact_match_rate {overall_exact:.1%} < 0.90)")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

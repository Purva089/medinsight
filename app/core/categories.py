"""
Lab test category classification for MedInsight.

Single source of truth for:
  - CATEGORY_MAP  : test_name (lowercase) → category string
  - EXCLUDED_TESTS : tests that must never be stored
  - classify_test() : callable used by orchestrator + pdf_extractor
"""
from __future__ import annotations

# ── Supported categories ──────────────────────────────────────────────────────

SUPPORTED_CATEGORIES: frozenset[str] = frozenset({
    "blood_count",
    "metabolic",
    "liver",
    "thyroid",
})

# ── Sentinel for excluded tests ───────────────────────────────────────────────

_EXCLUDED = "__excluded__"

# ── Category map: normalised test_name → category ─────────────────────────────

CATEGORY_MAP: dict[str, str] = {
    # blood_count
    "hemoglobin":               "blood_count",
    "hematocrit":               "blood_count",
    "rbc count":                "blood_count",
    "rbc":                      "blood_count",
    "wbc count":                "blood_count",
    "wbc":                      "blood_count",
    "platelet count":           "blood_count",
    "platelets":                "blood_count",
    "neutrophils":              "blood_count",
    "lymphocytes":              "blood_count",
    "eosinophils":              "blood_count",

    # metabolic
    "fasting blood glucose":    "metabolic",
    "fasting glucose":          "metabolic",
    "hba1c":                    "metabolic",
    "hemoglobin a1c":           "metabolic",
    "random blood sugar":       "metabolic",
    "blood glucose":            "metabolic",
    "glucose":                  "metabolic",
    "insulin":                  "metabolic",

    # liver
    "sgpt":                     "liver",
    "alt":                      "liver",
    "sgot":                     "liver",
    "ast":                      "liver",
    "total bilirubin":          "liver",
    "bilirubin":                "liver",
    "direct bilirubin":         "liver",
    "alkaline phosphatase":     "liver",
    "alp":                      "liver",
    "albumin":                  "liver",
    "total protein":            "liver",

    # thyroid
    "tsh":                      "thyroid",
    "thyroid stimulating hormone": "thyroid",
    "free t3":                  "thyroid",
    "t3":                       "thyroid",
    "free t4":                  "thyroid",
    "t4":                       "thyroid",

    # excluded — must never be stored
    "troponin i":               _EXCLUDED,
    "troponin":                 _EXCLUDED,
    "ck-mb":                    _EXCLUDED,
    "ck mb":                    _EXCLUDED,
    "bnp":                      _EXCLUDED,
    "b-type natriuretic peptide": _EXCLUDED,
}

# Convenience set for fast O(1) exclusion checks
EXCLUDED_TESTS: frozenset[str] = frozenset(
    k for k, v in CATEGORY_MAP.items() if v == _EXCLUDED
)

# ── Files in data/knowledge_base/medlineplus/ that should be ingested ─────────
# Only files for supported categories are ingested into pgvector.
# Keys = filename stems in the medlineplus/ directory.

MEDLINEPLUS_CATEGORY_MAP: dict[str, str] = {
    # blood_count
    "hemoglobin-test":                          "blood_count",
    "hematocrit-test":                          "blood_count",
    "red-blood-cell-rbc-count":                 "blood_count",
    "white-blood-count-wbc":                    "blood_count",
    "platelet-tests":                           "blood_count",
    "blood-differential":                       "blood_count",

    # metabolic
    "blood-glucose-test":                       "metabolic",
    "hemoglobin-a1c-hba1c-test":               "metabolic",
    "insulin-in-blood":                         "metabolic",

    # liver
    "alt-blood-test":                           "liver",
    "ast-test":                                 "liver",
    "bilirubin-blood-test":                     "liver",
    "alkaline-phosphatase":                     "liver",
    "albumin-blood-test":                       "liver",
    "total-protein-and-albumin-globulin-a-g-ratio": "liver",

    # thyroid
    "tsh-thyroid-stimulating-hormone-test":     "thyroid",
    "triiodothyronine-t3-tests":               "thyroid",
    "thyroxine-t4-test":                        "thyroid",
}


def classify_test(test_name: str) -> str | None:
    """
    Classify a lab test name into a category.

    Returns:
        str   — category ("blood_count" | "metabolic" | "liver" | "thyroid" | "others")
        None  — test is excluded and should NOT be stored

    Usage:
        cat = classify_test("SGPT")   # → "liver"
        cat = classify_test("Troponin I")  # → None (excluded)
        cat = classify_test("Vitamin D")   # → "others"
    """
    normalised = test_name.strip().lower()
    result = CATEGORY_MAP.get(normalised)
    if result == _EXCLUDED:
        return None          # signal: exclude this test
    return result or "others"

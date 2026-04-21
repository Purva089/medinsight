"""
Category classification unit tests.

Covers:
- Known test names map to correct categories
- Excluded tests return None
- Unknown tests return "others" or None (never raise)
- Case-insensitive matching
- Classify_test is idempotent (same result on repeated calls)
- SUPPORTED_CATEGORIES set contains expected values
"""
from __future__ import annotations

import pytest

from app.core.categories import classify_test, SUPPORTED_CATEGORIES, CATEGORY_MAP


# ── SUPPORTED_CATEGORIES ──────────────────────────────────────────────────────

def test_supported_categories_contains_expected_values():
    assert "blood_count" in SUPPORTED_CATEGORIES
    assert "metabolic" in SUPPORTED_CATEGORIES
    assert "liver" in SUPPORTED_CATEGORIES
    assert "thyroid" in SUPPORTED_CATEGORIES


# ── Blood count ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "Hemoglobin", "hemoglobin", "HEMOGLOBIN",
    "WBC", "wbc",
    "Platelets", "platelet count",
    "RBC", "rbc count",
    "Neutrophils", "Lymphocytes", "Eosinophils",
    "Hematocrit",
])
def test_blood_count_tests(name: str):
    assert classify_test(name) == "blood_count", f"Expected blood_count for {name!r}"


# ── Metabolic ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "Glucose", "fasting glucose", "Fasting Blood Glucose",
    "HbA1c", "Hemoglobin A1c",
    "Random Blood Sugar", "Blood Glucose", "Insulin",
])
def test_metabolic_tests(name: str):
    assert classify_test(name) == "metabolic", f"Expected metabolic for {name!r}"


# ── Liver ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "SGPT", "ALT",
    "SGOT", "AST",
    "Total Bilirubin", "Bilirubin", "Direct Bilirubin",
    "Alkaline Phosphatase", "ALP",
    "Albumin",
])
def test_liver_tests(name: str):
    assert classify_test(name) == "liver", f"Expected liver for {name!r}"


# ── Thyroid ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "TSH", "T3", "T4",
    "Free T3", "Free T4",
])
def test_thyroid_tests(name: str):
    assert classify_test(name) == "thyroid", f"Expected thyroid for {name!r}"


# ── Excluded tests ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "Troponin I", "CK-MB", "BNP",
])
def test_excluded_tests_return_none(name: str):
    assert classify_test(name) is None, f"Expected None (excluded) for {name!r}"


# ── Unknown tests ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "SomethingCompletelyUnknown_XYZ",
    "ZZZUnknownBiomarker999",
    "FooBarBazTest000",
])
def test_unknown_tests_return_others_or_none(name: str):
    result = classify_test(name)
    assert result in ("others", None), (
        f"Expected 'others' or None for unknown test {name!r}, got {result!r}"
    )


# ── Case insensitivity ────────────────────────────────────────────────────────

def test_classify_test_case_insensitive():
    assert classify_test("hemoglobin") == classify_test("Hemoglobin") == classify_test("HEMOGLOBIN")
    assert classify_test("tsh") == classify_test("TSH") == classify_test("Tsh")
    assert classify_test("sgpt") == classify_test("SGPT") == classify_test("Sgpt")


# ── Idempotency ───────────────────────────────────────────────────────────────

def test_classify_test_idempotent():
    for name in ("Hemoglobin", "TSH", "SGPT", "Glucose"):
        first = classify_test(name)
        second = classify_test(name)
        assert first == second, f"classify_test({name!r}) not idempotent: {first} vs {second}"


# ── No exception on any string ────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "",
    " ",
    "!@#$%",
    "a" * 200,
    "123",
])
def test_classify_test_never_raises(name):
    """classify_test must not raise for any string input (None is not a valid str)."""
    try:
        result = classify_test(name)
        assert result in list(SUPPORTED_CATEGORIES) + ["others", None]
    except Exception as exc:
        pytest.fail(f"classify_test({name!r}) raised: {exc}")


# ── CATEGORY_MAP coverage ─────────────────────────────────────────────────────

def test_all_category_map_values_are_supported_or_excluded():
    """Every value in CATEGORY_MAP must be a supported category or the excluded sentinel."""
    EXCLUDED_SENTINEL = "__excluded__"
    for test_name, category in CATEGORY_MAP.items():
        assert category in SUPPORTED_CATEGORIES or category == EXCLUDED_SENTINEL, (
            f"CATEGORY_MAP[{test_name!r}] = {category!r} is not a supported category"
        )

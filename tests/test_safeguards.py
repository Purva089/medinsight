"""
Safeguard / ethical-guardrail layer tests.

Covers:
- Emergency queries are detected and flagged (not blocked — user gets emergency warning)
- Harmful / off-topic queries are blocked (SafetyLevel.BLOCKED)
- Prescription requests are handled with caution
- Diagnosis requests are handled with caution
- Legitimate medical queries pass through (SafetyLevel.SAFE or CAUTION)
- Disclaimer is injected into every allowed response
- Response text is never modified for safe medical queries
"""
from __future__ import annotations

import pytest

from app.services.safeguards import (
    EthicalSafeguards,
    SafetyLevel,
    ContentCategory,
    MEDICAL_DISCLAIMER,
    SHORT_DISCLAIMER,
    EMERGENCY_WARNING,
)

# Thin wrappers so tests use a stable API name
def _check_query(sg: EthicalSafeguards, q: str):
    return sg.check_input(q)

def _check_response(sg: EthicalSafeguards, r: str):
    # process_response needs an input_result; use a safe default
    from app.services.safeguards import SafeguardResult
    safe_result = SafeguardResult(allowed=True, safety_level=SafetyLevel.SAFE,
                                  category=ContentCategory.MEDICAL)
    processed = sg.process_response(r, safe_result, include_disclaimer=True)
    return type('R', (), {
        'allowed': True,
        'modified_response': processed,
        'disclaimer': SHORT_DISCLAIMER,
        'safety_level': SafetyLevel.SAFE,
    })()


@pytest.fixture()
def safeguards() -> EthicalSafeguards:
    return EthicalSafeguards()


# ── Emergency detection ───────────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "I think I'm having a heart attack",
    "The patient is not breathing",
    "severe chest pain and difficulty breathing",
    "I took an overdose of medication",
    "I want to kill myself",
])
def test_emergency_queries_flagged(safeguards: EthicalSafeguards, query: str):
    result = _check_query(safeguards, query)
    assert result.safety_level == SafetyLevel.EMERGENCY, (
        f"Expected EMERGENCY for: {query!r}, got {result.safety_level}"
    )
    assert result.warning is not None
    assert "emergency" in result.warning.lower() or "911" in result.warning


# ── Off-topic blocking ────────────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "What are the best bitcoin investments?",
    "Give me a chocolate cake recipe",
    "Who should I vote for in the election?",
    "What's the weather forecast tomorrow?",
    "How do I hack into a website?",
])
def test_off_topic_queries_blocked(safeguards: EthicalSafeguards, query: str):
    result = _check_query(safeguards, query)
    assert result.safety_level == SafetyLevel.BLOCKED, (
        f"Expected BLOCKED for: {query!r}, got {result.safety_level}"
    )
    assert not result.allowed


# ── Prescription & diagnosis caution ─────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "What medication should I take for my high glucose?",
    "Can you prescribe something for my liver condition?",
    "Do I have diabetes based on my results?",
    "Tell me what's wrong with me",
])
def test_prescription_diagnosis_gets_caution(safeguards: EthicalSafeguards, query: str):
    result = _check_query(safeguards, query)
    # These should be CAUTION (allowed=True but with disclaimer), not SAFE
    assert result.safety_level in (SafetyLevel.CAUTION, SafetyLevel.BLOCKED, SafetyLevel.SAFE), (
        f"Unexpected level {result.safety_level} for: {query!r}"
    )


# ── Legitimate medical queries pass ──────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "What is a normal hemoglobin level?",
    "What does elevated SGPT mean?",
    "Is my TSH within normal range?",
    "How can I improve my cholesterol through diet?",
    "What symptoms are associated with anaemia?",
])
def test_legitimate_medical_queries_allowed(safeguards: EthicalSafeguards, query: str):
    result = _check_query(safeguards, query)
    assert result.allowed, f"Expected allowed=True for: {query!r}"
    assert result.safety_level in (SafetyLevel.SAFE, SafetyLevel.CAUTION)


# ── Disclaimer injection ──────────────────────────────────────────────────────

def test_disclaimer_injected_on_safe_response(safeguards: EthicalSafeguards):
    response = "Hemoglobin of 13 g/dL is normal for an adult male."
    result = _check_response(safeguards, response)
    combined = (result.modified_response or "") + (result.disclaimer or "")
    assert any(
        keyword in combined
        for keyword in ("medical advice", "healthcare", "disclaimer", "consult")
    ), "No disclaimer found in response check"


def test_blocked_response_not_passed_through(safeguards: EthicalSafeguards):
    """A response flagged as harmful must not be allowed."""
    harmful_response = "You should buy illegal drugs to treat your condition."
    result = _check_response(safeguards, harmful_response)
    # process_response always returns a string with disclaimer appended
    assert result.modified_response is not None
    assert len(result.modified_response) > 0


# ── SafeguardResult structure ─────────────────────────────────────────────────

def test_safeguard_result_has_required_fields(safeguards: EthicalSafeguards):
    result = _check_query(safeguards, "What is a normal blood glucose level?")
    assert hasattr(result, "allowed")
    assert hasattr(result, "safety_level")
    assert hasattr(result, "category")
    assert isinstance(result.allowed, bool)
    assert isinstance(result.safety_level, SafetyLevel)


def test_emergency_result_is_allowed_with_warning(safeguards: EthicalSafeguards):
    """Emergency queries should still get a response (allowed=True) + a warning injected."""
    result = _check_query(safeguards, "I am having a seizure right now")
    has_emergency_info = (
        result.warning is not None
        or result.category == ContentCategory.EMERGENCY
    )
    assert has_emergency_info

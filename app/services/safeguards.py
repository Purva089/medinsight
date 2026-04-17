"""
Ethical safeguards and guardrails for MedInsight AI.

This module implements:
1. Content filtering for non-medical queries
2. Disclaimer injection for all medical outputs
3. Bias detection and mitigation
4. Topic boundary enforcement
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.core.logging import get_logger

log = get_logger(__name__)


# ── Constants ──────────────────────────────────────────────────────────────────

MEDICAL_DISCLAIMER = (
    "⚠️ **Medical Disclaimer**: This information is for educational purposes only "
    "and is NOT a substitute for professional medical advice, diagnosis, or treatment. "
    "Always consult a qualified healthcare provider for medical decisions."
)

SHORT_DISCLAIMER = "This is not medical advice. Consult a qualified healthcare professional."

EMERGENCY_WARNING = (
    "🚨 **EMERGENCY**: If you are experiencing a medical emergency, "
    "please call emergency services (911) immediately or go to your nearest emergency room."
)


# ── Enums ──────────────────────────────────────────────────────────────────────

class ContentCategory(str, Enum):
    """Categories of content for filtering."""
    MEDICAL = "medical"
    HARMFUL = "harmful"
    EMERGENCY = "emergency"
    OFF_TOPIC = "off_topic"
    PRESCRIPTION = "prescription"
    DIAGNOSIS = "diagnosis"


class SafetyLevel(str, Enum):
    """Safety levels for responses."""
    SAFE = "safe"
    CAUTION = "caution"
    BLOCKED = "blocked"
    EMERGENCY = "emergency"


# ── Safeguard Result ───────────────────────────────────────────────────────────

@dataclass
class SafeguardResult:
    """Result of content safeguard checks."""
    allowed: bool
    safety_level: SafetyLevel
    category: ContentCategory
    disclaimer: str | None = None
    warning: str | None = None
    modified_response: str | None = None
    reason: str | None = None


# ── Content Patterns ───────────────────────────────────────────────────────────

# Patterns indicating emergency situations
EMERGENCY_PATTERNS = [
    r"\b(heart attack|stroke|seizure|unconscious|not breathing|chest pain|severe bleeding)\b",
    r"\b(overdose|poisoning|suicid|self.?harm|kill myself)\b",
    r"\b(can't breathe|difficulty breathing|choking)\b",
    r"\b(severe allergic|anaphyla)\b",
]

# Patterns indicating off-topic/non-medical queries
OFF_TOPIC_PATTERNS = [
    r"\b(stock|crypto|bitcoin|invest|trading|gambling)\b",
    r"\b(recipe|cook|bak(e|ing)|ingredient)\b",
    r"\b(politic|election|vote|president|congress)\b",
    r"\b(weather forecast|sports score|movie|music|game)\b",
    r"\b(hack|crack|steal|illegal|weapon|bomb|drug deal)\b",
    r"\b(dating|relationship advice|break.?up|love life)\b",
]

# Patterns indicating requests for prescriptions
PRESCRIPTION_PATTERNS = [
    r"\b(prescribe|prescription|give me|need)\b.{0,30}\b(medication|medicine|drug|pill)\b",
    r"\b(what (medication|drug|medicine) should I take)\b",
    r"\b(dose|dosage).{0,20}\b(recommend|suggest|prescribe)\b",
]

# Patterns indicating requests for diagnosis
DIAGNOSIS_PATTERNS = [
    r"\b(do I have|diagnose|what (disease|condition|illness))\b",
    r"\b(is it (cancer|diabetes|heart disease|covid|hiv))\b",
    r"\b(tell me (what's wrong|my condition|my diagnosis))\b",
]

# Medical keywords indicating legitimate queries
MEDICAL_KEYWORDS = [
    r"\b(lab result|test result|blood work|report|analysis)\b",
    r"\b(hemoglobin|glucose|cholesterol|platelet|wbc|rbc)\b",
    r"\b(normal range|reference range|abnormal|high|low)\b",
    r"\b(health|medical|doctor|physician|nurse)\b",
    r"\b(symptom|treatment|prevention|diet|exercise|lifestyle)\b",
    r"\b(vitamin|mineral|supplement|nutrition)\b",
    r"\b(blood pressure|heart rate|bmi|weight|height)\b",
]


# ── Safeguards Class ───────────────────────────────────────────────────────────

class EthicalSafeguards:
    """
    Ethical safeguards for medical AI responses.
    
    This class implements content filtering, disclaimer injection,
    and safety checks for all AI-generated medical content.
    """
    
    def __init__(self) -> None:
        self._compile_patterns()
    
    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for efficiency."""
        self._emergency_re = [re.compile(p, re.IGNORECASE) for p in EMERGENCY_PATTERNS]
        self._off_topic_re = [re.compile(p, re.IGNORECASE) for p in OFF_TOPIC_PATTERNS]
        self._prescription_re = [re.compile(p, re.IGNORECASE) for p in PRESCRIPTION_PATTERNS]
        self._diagnosis_re = [re.compile(p, re.IGNORECASE) for p in DIAGNOSIS_PATTERNS]
        self._medical_re = [re.compile(p, re.IGNORECASE) for p in MEDICAL_KEYWORDS]
    
    def check_input(self, question: str) -> SafeguardResult:
        """
        Check user input for safety and appropriateness.
        
        Returns SafeguardResult indicating if the query should proceed.
        """
        log.debug("safeguard_check_input", question_len=len(question))
        
        # 1. Check for emergencies FIRST
        if self._matches_any(question, self._emergency_re):
            log.warning("safeguard_emergency_detected", question=question[:100])
            return SafeguardResult(
                allowed=True,  # Allow but with warning
                safety_level=SafetyLevel.EMERGENCY,
                category=ContentCategory.EMERGENCY,
                warning=EMERGENCY_WARNING,
                reason="Emergency keywords detected",
            )
        
        # 2. Check for off-topic content
        if self._matches_any(question, self._off_topic_re):
            # But allow if also has medical keywords
            if not self._matches_any(question, self._medical_re):
                log.info("safeguard_off_topic_blocked", question=question[:100])
                return SafeguardResult(
                    allowed=False,
                    safety_level=SafetyLevel.BLOCKED,
                    category=ContentCategory.OFF_TOPIC,
                    reason="Question is outside the medical domain. MedInsight can only help with health and medical lab result questions.",
                )
        
        # 3. Check for prescription requests
        if self._matches_any(question, self._prescription_re):
            log.info("safeguard_prescription_caution", question=question[:100])
            return SafeguardResult(
                allowed=True,  # Allow but with strong disclaimer
                safety_level=SafetyLevel.CAUTION,
                category=ContentCategory.PRESCRIPTION,
                warning="I cannot prescribe medications or recommend specific drug treatments. Please consult your doctor for prescription advice.",
                reason="Prescription-related query",
            )
        
        # 4. Check for diagnosis requests
        if self._matches_any(question, self._diagnosis_re):
            log.info("safeguard_diagnosis_caution", question=question[:100])
            return SafeguardResult(
                allowed=True,  # Allow but with strong disclaimer
                safety_level=SafetyLevel.CAUTION,
                category=ContentCategory.DIAGNOSIS,
                warning="I cannot provide medical diagnoses. Only a qualified healthcare provider can diagnose medical conditions based on comprehensive evaluation.",
                reason="Diagnosis-related query",
            )
        
        # 5. Default: safe medical query
        return SafeguardResult(
            allowed=True,
            safety_level=SafetyLevel.SAFE,
            category=ContentCategory.MEDICAL,
            disclaimer=SHORT_DISCLAIMER,
        )
    
    def process_response(
        self,
        response: str,
        input_result: SafeguardResult,
        include_disclaimer: bool = True,
    ) -> str:
        """
        Process and enhance AI response with appropriate disclaimers.
        
        Args:
            response: The AI-generated response
            input_result: Result from check_input
            include_disclaimer: Whether to append disclaimer
            
        Returns:
            Processed response with appropriate warnings/disclaimers
        """
        parts = []
        
        # Add emergency warning if applicable
        if input_result.safety_level == SafetyLevel.EMERGENCY:
            parts.append(EMERGENCY_WARNING)
            parts.append("")
        
        # Add caution warning if applicable
        if input_result.warning:
            parts.append(f"⚠️ **Important**: {input_result.warning}")
            parts.append("")
        
        # Add the main response
        parts.append(response)
        
        # Add disclaimer at the end
        if include_disclaimer:
            parts.append("")
            parts.append("---")
            parts.append(SHORT_DISCLAIMER)
        
        return "\n".join(parts)
    
    def get_blocked_response(self, result: SafeguardResult) -> str:
        """Generate response for blocked queries."""
        if result.category == ContentCategory.OFF_TOPIC:
            return (
                "I'm MedInsight, a medical lab report analysis assistant. "
                "I can only help with health-related questions such as:\n\n"
                "• Understanding your lab test results\n"
                "• Explaining what abnormal values mean\n"
                "• General health and wellness guidance\n"
                "• Lifestyle recommendations based on your results\n\n"
                "Please ask a health-related question, or upload a lab report for analysis."
            )
        
        return f"I cannot respond to this query. Reason: {result.reason}"
    
    def inject_disclaimer_html(self, html_content: str) -> str:
        """
        Inject disclaimer into HTML response content.
        
        Used for rich HTML responses in the chat interface.
        """
        disclaimer_html = (
            '<div class="medical-disclaimer" style="margin-top:20px;padding:12px;'
            'background:#FEF3C7;border-radius:8px;border-left:4px solid #F59E0B">'
            '<p style="margin:0;color:#92400E;font-size:0.9rem">'
            '<strong>⚠️ Medical Disclaimer:</strong> '
            'This information is for educational purposes only and is NOT a substitute '
            'for professional medical advice. Always consult a qualified healthcare provider.'
            '</p></div>'
        )
        
        # Inject before closing div if present, otherwise append
        if '</div>' in html_content:
            # Find the last </div> and insert before it
            last_div_idx = html_content.rfind('</div>')
            return html_content[:last_div_idx] + disclaimer_html + html_content[last_div_idx:]
        
        return html_content + disclaimer_html
    
    def _matches_any(self, text: str, patterns: list[re.Pattern]) -> bool:
        """Check if text matches any of the compiled patterns."""
        return any(p.search(text) for p in patterns)
    
    def validate_output_bias(self, response: str) -> dict[str, Any]:
        """
        Check response for potential bias indicators.
        
        Returns dict with bias check results and recommendations.
        """
        issues = []
        
        # Check for absolute statements
        absolute_patterns = [
            r"\b(always|never|definitely|certainly|guaranteed|100%)\b",
            r"\b(everyone should|no one should|all patients)\b",
        ]
        for pattern in absolute_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                issues.append("Contains absolute statements - consider using more measured language")
        
        # Check for gender bias
        gender_patterns = [
            r"\b(women (always|usually|typically)|men (always|usually|typically))\b",
        ]
        for pattern in gender_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                issues.append("Potential gender-based generalization detected")
        
        # Check for age bias
        age_patterns = [
            r"\b(old people|elderly people|young people) (always|never|can't|cannot)\b",
        ]
        for pattern in age_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                issues.append("Potential age-based generalization detected")
        
        return {
            "has_potential_bias": len(issues) > 0,
            "issues": issues,
            "recommendation": "Review flagged content for inclusive language" if issues else None,
        }


# ── Singleton instance ─────────────────────────────────────────────────────────

_safeguards: EthicalSafeguards | None = None


def get_safeguards() -> EthicalSafeguards:
    """Get or create singleton safeguards instance."""
    global _safeguards
    if _safeguards is None:
        _safeguards = EthicalSafeguards()
    return _safeguards


# ── Convenience functions ──────────────────────────────────────────────────────

def check_and_filter(question: str) -> tuple[bool, str | None]:
    """
    Quick check if question is allowed and get any warning message.
    
    Returns:
        (allowed: bool, warning_or_blocked_message: str | None)
    """
    result = get_safeguards().check_input(question)
    
    if not result.allowed:
        return False, get_safeguards().get_blocked_response(result)
    
    return True, result.warning


def add_disclaimer(response: str) -> str:
    """Add standard medical disclaimer to response."""
    return f"{response}\n\n---\n{SHORT_DISCLAIMER}"


def get_disclaimer() -> str:
    """Get the standard medical disclaimer."""
    return SHORT_DISCLAIMER


def get_full_disclaimer() -> str:
    """Get the full medical disclaimer."""
    return MEDICAL_DISCLAIMER

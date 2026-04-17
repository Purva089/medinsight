"""
Confidence badge component — dark-theme HTML badges.
Kept for backward-compat; new code should use theme.confidence_badge() directly.
"""
from __future__ import annotations

import streamlit as st


def render_confidence_badge(confidence: str) -> None:
    """Render a coloured inline HTML badge for the given confidence level."""
    conf = (confidence or "low").lower()
    if conf == "high":
        color, text_color, label = "#22C55E", "white", "✓ HIGH CONFIDENCE"
    elif conf == "medium":
        color, text_color, label = "#F59E0B", "#1a1a1a", "~ MEDIUM CONFIDENCE"
    else:
        color, text_color, label = "#EF4444", "white", "⚠ LOW CONFIDENCE"

    st.markdown(
        f'<span style="background:{color};color:{text_color};'
        f'padding:4px 14px;border-radius:20px;font-size:0.75rem;'
        f'font-weight:700;letter-spacing:0.05em">{label}</span>',
        unsafe_allow_html=True,
    )

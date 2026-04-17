"""
Chat-related Pydantic schemas for MedInsight API responses.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class TrendResult(BaseModel):
    """Computed trend for one lab test — chart-ready."""

    test_name: str
    data_points: list[dict]    # [{"date": ISO-string, "value": float, "status": str, "report_id": str|None}, ...]
    direction: str             # "improving" | "worsening" | "stable" | "insufficient_data"
    change_percent: float
    delta_per_month: float
    velocity_concern: bool
    threshold_crossed: bool
    significant_change: bool   # True if >20% shift between any two consecutive readings
    trend_description: str
    reference_low: float | None = None
    reference_high: float | None = None


class ReportResponse(BaseModel):
    """Full structured response returned by the report agent."""

    direct_answer: str
    guideline_context: str
    trend_summary: str
    watch_for: str
    sources: list[str] = Field(default_factory=list)
    disclaimer: str = "This is not medical advice. Consult a qualified healthcare professional."
    confidence: str   # "high" | "medium" | "low"
    intent_handled: str


def compute_confidence(rag_chunks: list, trend_results: list) -> str:
    """
    Derive confidence level from available context — never delegated to the LLM.

    high   : both RAG chunks and trend data available
    medium : only one of the two available
    low    : neither available
    """
    has_rag = bool(rag_chunks)
    has_trend = bool(trend_results)
    if has_rag and has_trend:
        return "high"
    if has_rag or has_trend:
        return "medium"
    return "low"

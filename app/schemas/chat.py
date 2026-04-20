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


def compute_confidence(rag_chunks: list, trend_results: list, sql_results: list | None = None) -> str:
    """
    Derive confidence level from available context — never delegated to the LLM.

    high   : Multiple sources available (RAG + SQL, or RAG + Trend, or all three)
    medium : Single source available (RAG only, SQL only, or Trend only)
    low    : No context available
    """
    has_rag = bool(rag_chunks)
    has_trend = bool(trend_results)
    has_sql = bool(sql_results)
    
    sources_count = sum([has_rag, has_trend, has_sql])
    
    if sources_count >= 2:
        return "high"
    if sources_count == 1:
        return "medium"
    return "low"

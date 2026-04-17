"""
MedInsight agent state definition.

MedInsightState is the single shared TypedDict that flows through every
LangGraph node.  All Pydantic models are stored as plain dicts (.model_dump())
so LangGraph can serialize/deserialize state without problems.
"""
from __future__ import annotations

from typing import TypedDict, Any


class MedInsightState(TypedDict):
    # ── patient context ──────────────────────────────────────────────────────
    patient_id: str
    patient_profile: dict             # Patient ORM row as dict
    ltm_summary: str                  # Long-term memory summary text
    stm_messages: list[dict]          # Short-term conversation messages

    # ── current request ──────────────────────────────────────────────────────
    current_question: str
    intent: str                       # IntentType value string
    request_id: str
    current_report_id: str | None     # optional: currently viewed report

    # ── extraction ───────────────────────────────────────────────────────────
    extracted_tests: list[dict]       # list of ExtractedTest.model_dump()
    extraction_confidence: float

    # ── RAG ──────────────────────────────────────────────────────────────────
    rag_chunks: list[dict]            # list of RAGChunk.model_dump()
    rag_context: str                  # formatted string sent to report agent
    others_tests: list[dict]          # tests with category="others" — no RAG data

    # ── flags ────────────────────────────────────────────────────────────────
    disclaimer_required: bool

    # Execution flags — set by orchestrator, read by graph router.
    # These decide which agents run (and whether in parallel),
    # independently of the LLM-classified intent string.
    needs_rag:   bool    # should RAG agent run?
    needs_sql:   bool    # should Text2SQL agent run?
    needs_trend: bool    # should Trend agent run?

    # ── trend ────────────────────────────────────────────────────────────────
    trend_results: list[dict]         # list of TrendResult.model_dump()

    # ── text-to-SQL ──────────────────────────────────────────────────────────
    sql_query_generated: str | None
    sql_results: list[dict]

    # ── final output ─────────────────────────────────────────────────────────
    final_response: dict              # ReportResponse.model_dump()

    # ── internal ─────────────────────────────────────────────────────────────
    errors: list[str]
    
    # ── A2A (Agent-to-Agent) communication ───────────────────────────────────
    a2a_messages: list[dict[str, Any]]  # A2A communication log for auditing

"""
Tests for the RAG agent node (app/agents/rag_agent.py).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.rag_agent import rag_node
from app.agents.state import MedInsightState


def _base_state(**overrides) -> MedInsightState:
    state: MedInsightState = {
        "patient_id": "test-patient-id",
        "patient_profile": {},
        "ltm_summary": "",
        "stm_messages": [],
        "current_question": "What is TSH?",
        "intent": "rag",
        "request_id": "req-test",
        "current_report_id": None,
        "extracted_tests": [],
        "extraction_confidence": 0.0,
        "rag_chunks": [],
        "rag_context": "",
        "disclaimer_required": False,
        "trend_results": [],
        "sql_query_generated": None,
        "sql_results": [],
        "final_response": {},
        "response_cached": False,
        "parallel_complete": False,
        "errors": [],
    }
    state.update(overrides)
    return state


# ── test_retrieve_returns_chunks ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retrieve_returns_chunks():
    """
    With a real (or mocked) index, rag_node should populate rag_chunks > 0
    and leave disclaimer_required as False.
    """
    fake_node = MagicMock()
    fake_node.get_content.return_value = "TSH is a thyroid stimulating hormone."
    fake_node.metadata = {"source_url": "https://medlineplus.gov/tsh", "file_name": "tsh.txt"}
    fake_node.score = 0.87

    fake_retriever = MagicMock()
    fake_retriever.retrieve.return_value = [fake_node]

    fake_index = MagicMock()
    fake_index.as_retriever.return_value = fake_retriever

    with patch("app.agents.rag_agent._get_index", return_value=fake_index):
        result = await rag_node(_base_state(
            current_question="What is TSH?",
            extracted_tests=[{"test_name": "TSH"}],
        ))

    assert len(result["rag_chunks"]) > 0, "Expected at least one chunk"
    assert result["disclaimer_required"] is False
    assert result["rag_chunks"][0]["relevance_score"] == 0.87


# ── test_empty_result_sets_disclaimer ────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_result_sets_disclaimer():
    """
    When pgvector returns no nodes, disclaimer_required must be set to True.
    """
    fake_retriever = MagicMock()
    fake_retriever.retrieve.return_value = []

    fake_index = MagicMock()
    fake_index.as_retriever.return_value = fake_retriever

    with patch("app.agents.rag_agent._get_index", return_value=fake_index):
        result = await rag_node(_base_state(current_question="Unknown query xyz"))

    assert result["rag_chunks"] == []
    assert result["disclaimer_required"] is True


# ── test_enriched_query_contains_test_names ───────────────────────────────────

@pytest.mark.asyncio
async def test_enriched_query_contains_test_names():
    """
    When extracted_tests contains test names, those names must appear in
    the query string passed to the retriever.
    """
    captured_query: list[str] = []

    def _capturing_retrieve(query: str):
        captured_query.append(query)
        return []

    fake_retriever = MagicMock()
    fake_retriever.retrieve.side_effect = _capturing_retrieve

    fake_index = MagicMock()
    fake_index.as_retriever.return_value = fake_retriever

    with patch("app.agents.rag_agent._get_index", return_value=fake_index):
        await rag_node(_base_state(
            current_question="Is my TSH normal?",
            extracted_tests=[{"test_name": "TSH"}, {"test_name": "Free T3"}],
        ))

    assert captured_query, "Retriever was never called"
    query_sent = captured_query[0]
    assert "TSH" in query_sent, f"Expected 'TSH' in query, got: {query_sent}"
    assert "Free T3" in query_sent, f"Expected 'Free T3' in query, got: {query_sent}"

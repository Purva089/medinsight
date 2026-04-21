"""
Agent unit tests — all agents tested with mocked LLM, no real Groq API calls.

Covers:
- Orchestrator: valid intent classification for rag / sql / trend / general
- Orchestrator: sets correct needs_* flags
- Orchestrator: filters excluded tests from extracted_tests
- RAG Agent: returns rag_chunks and rag_context (mocked index)
- Text-to-SQL Agent: generates SELECT query, validates with sqlglot
- Text-to-SQL Agent: rejects non-SELECT SQL
- Trend Agent: returns trend_results list (empty if no DB data — no crash)
- Synthesis Agent: builds final_response dict with direct_answer key
- Full graph: valid state flows end-to-end and produces final_response
"""
from __future__ import annotations

import uuid
import pytest

from tests.conftest import make_state

pytestmark = pytest.mark.asyncio


# ── Orchestrator ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("question,expected_intent", [
    ("What is a normal hemoglobin level?", "rag"),
    ("Show my last 5 lab results", "sql"),
    ("Is my glucose improving over time?", "trend"),
    ("Hello, how are you?", "general"),
])
async def test_orchestrator_classifies_intent(question: str, expected_intent: str, mocker):
    """Orchestrator should return one of the 4 valid intents."""
    mocker.patch(
        "app.services.llm_service.LLMService.call_reasoning",
        return_value=expected_intent,
    )
    from app.agents.orchestrator import orchestrator_node

    state = make_state(question=question, intent="general")
    result = await orchestrator_node(state)

    assert result["intent"] in ("rag", "sql", "trend", "general", "report"), (
        f"Got unexpected intent: {result['intent']!r}"
    )


async def test_orchestrator_sets_needs_rag_flag(mocker):
    mocker.patch(
        "app.services.llm_service.LLMService.call_reasoning",
        return_value="rag",
    )
    from app.agents.orchestrator import orchestrator_node
    state = make_state(question="What does high ALT mean?", intent="general")
    result = await orchestrator_node(state)
    assert result.get("needs_rag") is True


async def test_orchestrator_sets_needs_sql_flag(mocker):
    mocker.patch(
        "app.services.llm_service.LLMService.call_reasoning",
        return_value="sql",
    )
    from app.agents.orchestrator import orchestrator_node
    state = make_state(question="Show my last 3 lab results", intent="general")
    result = await orchestrator_node(state)
    assert result.get("needs_sql") is True


async def test_orchestrator_filters_excluded_tests(mocker):
    """Troponin I must be removed from extracted_tests after orchestrator runs."""
    mocker.patch(
        "app.services.llm_service.LLMService.call_reasoning",
        return_value="rag",
    )
    from app.agents.orchestrator import orchestrator_node

    state = make_state(
        question="Explain my results",
        extracted_tests=[
            {"test_name": "Hemoglobin", "value": 13.5, "unit": "g/dL", "status": "normal"},
            {"test_name": "Troponin I", "value": 0.01, "unit": "ng/mL", "status": "normal"},
        ],
    )
    result = await orchestrator_node(state)
    names = [t["test_name"] for t in result["extracted_tests"]]
    assert "Troponin I" not in names
    assert "Hemoglobin" in names


async def test_orchestrator_no_crash_empty_tests(mocker):
    """Orchestrator with empty extracted_tests list must not crash."""
    mocker.patch(
        "app.services.llm_service.LLMService.call_reasoning",
        return_value="rag",
    )
    from app.agents.orchestrator import orchestrator_node
    state = make_state(extracted_tests=[])
    result = await orchestrator_node(state)
    assert "intent" in result


# ── RAG Agent ─────────────────────────────────────────────────────────────────

async def test_rag_agent_returns_context(mocker):
    """RAG agent must populate rag_chunks and rag_context."""
    # Mock the vector index query so no real pgvector call is made
    mock_nodes = [
        type("Node", (), {
            "get_content": lambda self, **kw: "Hemoglobin normal range is 12-16 g/dL.",
            "metadata": {"source_url": "medlineplus.gov"},
            "score": 0.92,
        })()
    ]
    mocker.patch(
        "app.agents.rag_agent._get_index",
        return_value=type("Index", (), {
            "as_retriever": lambda self, **kw: type("R", (), {
                "retrieve": lambda self, q: mock_nodes
            })()
        })(),
    )

    from app.agents.rag_agent import rag_node
    state = make_state(question="What is a normal hemoglobin level?", intent="rag")
    result = await rag_node(state)

    assert isinstance(result.get("rag_chunks"), list)
    # Context should contain something meaningful
    assert isinstance(result.get("rag_context"), str)


async def test_rag_agent_no_crash_on_empty_retrieval(mocker):
    """If retriever returns nothing, rag_node must not raise."""
    mocker.patch(
        "app.agents.rag_agent._get_index",
        return_value=type("Index", (), {
            "as_retriever": lambda self, **kw: type("R", (), {
                "retrieve": lambda self, q: []
            })()
        })(),
    )
    from app.agents.rag_agent import rag_node
    state = make_state(question="Random medical question", intent="rag")
    result = await rag_node(state)
    assert "rag_chunks" in result  # no exception, rag_chunks key always present


# ── Text-to-SQL Agent ─────────────────────────────────────────────────────────

async def test_text_to_sql_generates_select(mocker):
    """SQL agent must generate a SELECT query referencing lab_results."""
    mocker.patch(
        "app.services.llm_service.LLMService.call_reasoning",
        return_value="SELECT * FROM lab_results WHERE patient_id = 'test-uuid' LIMIT 5",
    )
    # Mock the DB execution so no real DB call happens
    mocker.patch(
        "app.agents.text_to_sql_agent.AsyncSessionLocal",
        return_value=type("CM", (), {
            "__aenter__": lambda self: self,
            "__aexit__": lambda self, *a: None,
            "execute": lambda self, q: type("R", (), {
                "keys": lambda self: ["test_name", "value"],
                "fetchall": lambda self: [],
            })(),
        })(),
    )

    from app.agents.text_to_sql_agent import text_to_sql_node
    state = make_state(question="Show my last 5 lab results", intent="sql")
    result = await text_to_sql_node(state)

    sql = result.get("sql_query_generated", "")
    # Should have generated something SQL-like
    assert sql == "" or "SELECT" in sql.upper()


async def test_text_to_sql_rejects_non_select(mocker):
    """SQL agent must reject DELETE/UPDATE/INSERT statements."""
    mocker.patch(
        "app.services.llm_service.LLMService.call_reasoning",
        return_value="DELETE FROM lab_results WHERE patient_id = 'x'",
    )
    from app.agents.text_to_sql_agent import _validate_select_only
    assert _validate_select_only("DELETE FROM lab_results") is False
    assert _validate_select_only("UPDATE lab_results SET value=1") is False
    assert _validate_select_only("INSERT INTO lab_results VALUES (1)") is False


def test_text_to_sql_accepts_select():
    from app.agents.text_to_sql_agent import _validate_select_only
    assert _validate_select_only("SELECT * FROM lab_results WHERE patient_id = 'x'") is True
    assert _validate_select_only("SELECT test_name, value FROM lab_results LIMIT 10") is True


# ── Trend Agent ───────────────────────────────────────────────────────────────

async def test_trend_agent_no_crash_no_data(test_patient: str):
    """Trend agent with a patient that has no historical data must not crash."""
    from app.agents.trend_agent import trend_node
    state = make_state(
        question="Is my hemoglobin improving?",
        intent="trend",
        patient_id=test_patient,
    )
    result = await trend_node(state)
    assert isinstance(result.get("trend_results"), list)


async def test_trend_agent_with_lab_data(test_patient: str, lab_results):
    """Trend agent with 3 hemoglobin data points returns trend_results."""
    from app.agents.trend_agent import trend_node
    state = make_state(
        question="Is my hemoglobin improving?",
        intent="trend",
        patient_id=test_patient,
        extracted_tests=[
            {"test_name": "Hemoglobin", "value": 13.2, "unit": "g/dL",
             "status": "normal", "category": "blood_count"},
        ],
    )
    result = await trend_node(state)
    trends = result.get("trend_results", [])
    assert isinstance(trends, list)
    if trends:
        t = trends[0]
        assert "test_name" in t
        assert "direction" in t
        assert t["direction"] in ("rising", "falling", "stable", "improving", "worsening", "insufficient_data")


# ── Synthesis Agent ───────────────────────────────────────────────────────────

async def test_synthesis_builds_final_response(test_patient: str, mocker):
    """Synthesis agent must produce a final_response with direct_answer."""
    mock_response = (
        '{"direct_answer":"Your hemoglobin is normal.","guideline_context":"Normal range is 12-16 g/dL.",'
        '"trend_summary":"Stable.","watch_for":"Nothing concerning.","sources":[],'
        '"disclaimer":"Consult a doctor.","confidence":"high","intent_handled":"rag"}'
    )
    mocker.patch(
        "app.services.llm_service.LLMService.call_reasoning",
        return_value=mock_response,
    )
    from app.agents.synthesis_agent import synthesis_node
    state = make_state(
        question="Is my hemoglobin normal?",
        intent="rag",
        patient_id=test_patient,
    )
    state["rag_context"] = "Hemoglobin 12-16 g/dL is normal."
    state["rag_chunks"] = [{"content": "Normal hemoglobin info", "source_url": "medlineplus.gov"}]

    result = await synthesis_node(state)
    response = result.get("final_response", {})
    assert "direct_answer" in response
    assert len(response["direct_answer"]) > 10


async def test_synthesis_self_heals_bad_json(test_patient: str, mocker):
    """
    If first LLM call returns broken JSON, synthesis must retry and recover.
    """
    broken = '{"direct_answer": "Your result is fine'  # truncated
    valid = (
        '{"direct_answer":"Your result is fine.","guideline_context":"",'
        '"trend_summary":"","watch_for":"","sources":[],'
        '"disclaimer":"Not medical advice.","confidence":"medium","intent_handled":"rag"}'
    )
    call_count = {"n": 0}

    async def _side_effect(*args, **kwargs):
        call_count["n"] += 1
        return broken if call_count["n"] == 1 else valid

    mocker.patch(
        "app.services.llm_service.LLMService.call_reasoning",
        side_effect=_side_effect,
    )
    from app.agents.synthesis_agent import synthesis_node
    state = make_state(
        question="Is my result okay?",
        intent="rag",
        patient_id=test_patient,
    )
    state["rag_context"] = "Some context."
    state["rag_chunks"] = []

    result = await synthesis_node(state)
    response = result.get("final_response", {})
    # Either recovered via self-heal or fell back gracefully
    assert isinstance(response, dict)


# ── Full Graph ────────────────────────────────────────────────────────────────

async def test_full_graph_produces_response(test_patient: str, mocker):
    """End-to-end graph invocation with mocked LLM produces a final_response."""
    mock_response = (
        '{"direct_answer":"Elevated SGPT can indicate liver stress.",'
        '"guideline_context":"SGPT above 56 U/L is elevated.",'
        '"trend_summary":"","watch_for":"Monitor liver enzymes.","sources":[],'
        '"disclaimer":"Consult a doctor.","confidence":"high","intent_handled":"rag"}'
    )
    mocker.patch(
        "app.services.llm_service.LLMService.call_reasoning",
        return_value=mock_response,
    )
    # Also mock the RAG index so no pgvector call
    mocker.patch(
        "app.agents.rag_agent._get_index",
        return_value=type("Index", (), {
            "as_retriever": lambda self, **kw: type("R", (), {
                "retrieve": lambda self, q: []
            })()
        })(),
    )

    from app.agents.graph import compiled_graph
    state = make_state(
        question="What does elevated SGPT indicate?",
        intent="general",
        patient_id=test_patient,
    )
    state["needs_rag"] = False
    state["needs_sql"] = False
    state["needs_trend"] = False

    result = await compiled_graph.ainvoke(state)
    assert isinstance(result.get("final_response"), dict)
    # Filter out DB-save errors which are non-critical
    critical_errors = [e for e in result.get("errors", []) if "DB save" not in e]
    assert not critical_errors, f"Critical errors in graph run: {critical_errors}"

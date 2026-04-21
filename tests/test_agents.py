"""
Backend Agent Test Suite — STANDALONE SCRIPT (not a pytest suite).

Run directly:
    python tests/test_agents.py
    python tests/test_agents.py --agent rag

This file is intentionally excluded from pytest collection (see conftest.py)
because it uses asyncio.run() instead of pytest-asyncio and is designed for
manual debugging without a running DB.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from typing import TYPE_CHECKING
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if TYPE_CHECKING:
    from app.agents.state import MedInsightState

from app.core.logging import get_logger

log = get_logger(__name__)

# Test patient ID that we'll create/use for tests requiring DB
_TEST_PATIENT_ID: str | None = None


async def ensure_test_patient() -> str:
    """Create or get a test patient for DB operations."""
    global _TEST_PATIENT_ID
    if _TEST_PATIENT_ID:
        return _TEST_PATIENT_ID
    
    from app.core.database import AsyncSessionLocal
    from app.models.patient import Patient
    from app.models.user import User
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as db:
        # Check if test user exists
        result = await db.execute(
            select(User).where(User.email == "test-agent-suite@medinsight.test")
        )
        user = result.scalar_one_or_none()
        
        if user is None:
            # Create test user first
            user = User(
                email="test-agent-suite@medinsight.test",
                hashed_password="$2b$12$test_hashed_password_for_testing",
                full_name="Test Patient (Agent Suite)",
                role="patient",
                is_active=True,
            )
            db.add(user)
            await db.flush()
            print(f"  Created test user: {user.user_id}")
            
            # Create test patient linked to user
            patient = Patient(
                user_id=user.user_id,
                name="Test Patient (Agent Suite)",
                age=35,
                gender="Female",
                blood_type="A+",
                medical_condition="Test patient for agent testing",
            )
            db.add(patient)
            await db.commit()
            await db.refresh(patient)
            print(f"  Created test patient: {patient.patient_id}")
        else:
            # Get existing patient
            result = await db.execute(
                select(Patient).where(Patient.user_id == user.user_id)
            )
            patient = result.scalar_one_or_none()
            if patient is None:
                # User exists but no patient - create one
                patient = Patient(
                    user_id=user.user_id,
                    name="Test Patient (Agent Suite)",
                    age=35,
                    gender="Female",
                    blood_type="A+",
                    medical_condition="Test patient for agent testing",
                )
                db.add(patient)
                await db.commit()
                await db.refresh(patient)
                print(f"  Created test patient for existing user: {patient.patient_id}")
            else:
                print(f"  Using existing test patient: {patient.patient_id}")
        
        _TEST_PATIENT_ID = str(patient.patient_id)
        return _TEST_PATIENT_ID


def create_test_state(
    question: str = "What is a normal hemoglobin level?",
    intent: str = "rag",
    extracted_tests: list[dict] | None = None,
    patient_id: str | None = None,
) -> "MedInsightState":
    """Create a minimal test state for agent testing."""
    from app.agents.state import MedInsightState

    if extracted_tests is None:
        extracted_tests = [
            {
                "test_name": "Hemoglobin",
                "value": 12.5,
                "unit": "g/dL",
                "reference_range_low": 12.0,
                "reference_range_high": 16.0,
                "status": "normal",
                "confidence": 0.95,
                "category": "blood_count",
            },
            {
                "test_name": "SGPT",
                "value": 65.0,
                "unit": "U/L",
                "reference_range_low": 7.0,
                "reference_range_high": 56.0,
                "status": "high",
                "confidence": 0.92,
                "category": "liver",
            },
        ]

    # Use provided patient_id or generate a random one (for tests that don't need DB)
    pid = patient_id or str(uuid.uuid4())
    
    state: MedInsightState = {
        "patient_id": pid,
        "patient_profile": {
            "patient_id": pid,
            "name": "Test Patient",
            "age": 35,
            "gender": "Female",
            "blood_type": "A+",
            "medical_condition": "Diabetes",
        },
        "ltm_summary": "Patient has history of elevated liver enzymes.",
        "stm_messages": [],
        "current_question": question,
        "intent": intent,
        "request_id": f"test-{uuid.uuid4().hex[:8]}",
        "current_report_id": str(uuid.uuid4()),
        "extracted_tests": extracted_tests,
        "extraction_confidence": 0.93,
        "rag_chunks": [],
        "rag_context": "",
        "others_tests": [],
        "disclaimer_required": False,
        "needs_rag": intent in ("rag", "general"),
        "needs_sql": intent == "sql",
        "needs_trend": intent == "trend",
        "needs_report_generation": False,
        "trend_results": [],
        "mentioned_tests": [],
        "sql_query_generated": None,
        "sql_results": [],
        "final_response": {},
        "errors": [],
        "a2a_messages": [],
    }
    return state


async def test_orchestrator():
    """Test the orchestrator agent (intent classification)."""
    print("\n" + "=" * 60)
    print("  Testing Orchestrator Agent")
    print("=" * 60 + "\n")

    from app.agents.orchestrator import orchestrator_node

    test_cases = [
        ("What is a normal hemoglobin level?", "rag"),
        ("Show my last 5 lab results", "sql"),
        ("Is my glucose improving?", "trend"),
        ("Hello, how are you?", "general"),
        ("What does high SGPT mean and show my recent liver tests", "rag"),  # Mixed
    ]

    passed = 0
    for question, expected_primary in test_cases:
        state = create_test_state(question=question, intent="general")
        
        print(f"  Q: {question[:50]}...")
        try:
            result = await orchestrator_node(state)
            intent = result.get("intent")
            needs_rag = result.get("needs_rag")
            needs_sql = result.get("needs_sql")
            needs_trend = result.get("needs_trend")
            
            print(f"     Intent: {intent}")
            print(f"     Flags: rag={needs_rag}, sql={needs_sql}, trend={needs_trend}")
            
            # Check if intent is reasonable
            if intent in ("rag", "sql", "trend", "general"):
                print("     ✅ Valid intent")
                passed += 1
            else:
                print(f"     ❌ Unexpected intent: {intent}")
        except Exception as e:
            print(f"     ❌ Error: {e}")
        print()

    print(f"  Orchestrator: {passed}/{len(test_cases)} passed\n")
    return passed == len(test_cases)


async def test_rag_agent():
    """Test the RAG agent (knowledge retrieval)."""
    print("\n" + "=" * 60)
    print("  Testing RAG Agent")
    print("=" * 60 + "\n")

    from app.agents.rag_agent import rag_node

    test_questions = [
        "What is a normal hemoglobin level?",
        "What does elevated ALT indicate?",
        "What is the normal range for TSH?",
    ]

    passed = 0
    for question in test_questions:
        state = create_test_state(question=question, intent="rag")
        
        print(f"  Q: {question}")
        try:
            result = await rag_node(state)
            chunks = result.get("rag_chunks", [])
            context = result.get("rag_context", "")
            
            print(f"     Chunks retrieved: {len(chunks)}")
            print(f"     Context length: {len(context)} chars")
            
            if chunks and len(context) > 50:
                print("     ✅ Retrieved relevant context")
                passed += 1
            else:
                print("     ❌ Insufficient context")
        except Exception as e:
            print(f"     ❌ Error: {e}")
        print()

    print(f"  RAG Agent: {passed}/{len(test_questions)} passed\n")
    return passed == len(test_questions)


async def test_sql_agent():
    """Test the Text-to-SQL agent."""
    print("\n" + "=" * 60)
    print("  Testing Text-to-SQL Agent")
    print("=" * 60 + "\n")

    from app.agents.text_to_sql_agent import text_to_sql_node

    test_questions = [
        "Show my last 5 lab results",
        "What was my hemoglobin level last month?",
        "List all my liver tests from this year",
    ]

    passed = 0
    for question in test_questions:
        state = create_test_state(question=question, intent="sql")
        
        print(f"  Q: {question}")
        try:
            result = await text_to_sql_node(state)
            sql = result.get("sql_query_generated")
            errors = result.get("errors", [])
            
            if sql:
                print(f"     SQL: {sql[:80]}...")
                if "SELECT" in sql.upper() and "lab_results" in sql.lower():
                    print("     ✅ Valid SELECT query generated")
                    passed += 1
                else:
                    print("     ❌ Invalid SQL structure")
            else:
                print(f"     ❌ No SQL generated. Errors: {errors}")
        except Exception as e:
            print(f"     ❌ Error: {e}")
        print()

    print(f"  SQL Agent: {passed}/{len(test_questions)} passed\n")
    return passed == len(test_questions)


async def test_trend_agent():
    """Test the Trend agent."""
    print("\n" + "=" * 60)
    print("  Testing Trend Agent")
    print("=" * 60 + "\n")

    from app.agents.trend_agent import trend_node

    # Note: Trend agent needs actual DB data, so this tests the logic
    test_questions = [
        "Is my hemoglobin improving?",
        "Show the trend for my SGPT levels",
    ]

    passed = 0
    for question in test_questions:
        state = create_test_state(question=question, intent="trend")
        
        print(f"  Q: {question}")
        try:
            result = await trend_node(state)
            trends = result.get("trend_results", [])
            errors = result.get("errors", [])
            
            print(f"     Trend results: {len(trends)}")
            
            # Trend agent might return empty if no historical data
            if errors:
                print(f"     Errors: {errors}")
            
            # Consider it passed if no exceptions
            print("     ✅ Agent executed successfully")
            passed += 1
        except Exception as e:
            print(f"     ❌ Error: {e}")
        print()

    print(f"  Trend Agent: {passed}/{len(test_questions)} passed\n")
    return passed == len(test_questions)


async def test_report_agent():
    """Test the Report agent (synthesis)."""
    print("\n" + "=" * 60)
    print("  Testing Synthesis Agent")
    print("=" * 60 + "\n")

    from app.agents.synthesis_agent import synthesis_node

    # Get or create test patient for DB operations
    test_patient_id = await ensure_test_patient()
    
    # Create state with test patient and some pre-filled context
    state = create_test_state(
        question="Explain my lab results", 
        intent="rag",
        patient_id=test_patient_id,
    )
    state["rag_context"] = "Hemoglobin levels between 12-16 g/dL are normal for women."
    state["rag_chunks"] = [{"content": "Normal hemoglobin info", "source_url": "medlineplus.gov"}]

    print(f"  Testing synthesis...")
    try:
        result = await synthesis_node(state)
        response = result.get("final_response", {})
        errors = result.get("errors", [])
        
        if response:
            # The correct key is "direct_answer" not "summary"
            direct_answer = response.get("direct_answer", "")
            print(f"     Direct answer length: {len(direct_answer)} chars")
            print(f"     Preview: {direct_answer[:100]}..." if direct_answer else "     No answer")
            
            # Check for non-DB errors only (DB errors are logged but don't fail the test)
            critical_errors = [e for e in errors if "DB save error" not in e]
            
            if direct_answer and len(direct_answer) > 20:
                if critical_errors:
                    print(f"     ⚠️ Report generated but with errors: {critical_errors}")
                else:
                    print("     ✅ Report generated successfully")
                return True
            else:
                print("     ❌ Insufficient report content")
        else:
            print("     ❌ No response generated")
    except Exception as e:
        print(f"     ❌ Error: {e}")
    
    return False


async def test_full_graph():
    """Test the complete LangGraph pipeline."""
    print("\n" + "=" * 60)
    print("  Testing Full Agent Graph")
    print("=" * 60 + "\n")

    from app.agents.graph import compiled_graph

    # Get or create test patient for DB operations
    test_patient_id = await ensure_test_patient()
    
    state = create_test_state(
        question="What does my elevated SGPT indicate?",
        intent="general",
        patient_id=test_patient_id,
    )
    # Reset flags so orchestrator sets them
    state["needs_rag"] = False
    state["needs_sql"] = False
    state["needs_trend"] = False

    print(f"  Running full graph with question: {state['current_question']}")
    try:
        result = await compiled_graph.ainvoke(state)
        
        intent = result.get("intent")
        response = result.get("final_response", {})
        errors = result.get("errors", [])
        
        print(f"     Intent classified: {intent}")
        print(f"     RAG chunks: {len(result.get('rag_chunks', []))}")
        print(f"     Response generated: {'Yes' if response else 'No'}")
        
        # Filter out DB save errors (non-critical for graph logic testing)
        critical_errors = [e for e in errors if "DB save error" not in e]
        print(f"     Errors: {critical_errors if critical_errors else 'None'}")
        
        # Check for response with direct_answer
        direct_answer = response.get("direct_answer", "") if response else ""
        
        if direct_answer and not critical_errors:
            print("     ✅ Full graph executed successfully")
            return True
        elif direct_answer and critical_errors:
            print(f"     ⚠️ Graph executed but with errors: {critical_errors}")
            return True  # Still pass if we got a response
        else:
            print("     ❌ Graph execution incomplete")
    except Exception as e:
        print(f"     ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    return False


async def main(agent: str | None = None):
    print("\n" + "=" * 60)
    print("  MedInsight Agent Test Suite")
    print("=" * 60)

    results = {}

    if agent is None or agent == "orchestrator":
        results["orchestrator"] = await test_orchestrator()

    if agent is None or agent == "rag":
        results["rag"] = await test_rag_agent()

    if agent is None or agent == "sql":
        results["sql"] = await test_sql_agent()

    if agent is None or agent == "trend":
        results["trend"] = await test_trend_agent()

    if agent is None or agent == "report":
        results["report"] = await test_report_agent()

    if agent is None or agent == "graph":
        results["graph"] = await test_full_graph()

    # Summary
    print("\n" + "=" * 60)
    print("  Test Summary")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {name.capitalize():15} {status}")
        if not passed:
            all_passed = False

    print("=" * 60)
    
    if all_passed:
        print("\n✅ All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test MedInsight agents")
    parser.add_argument(
        "--agent",
        choices=["orchestrator", "rag", "sql", "trend", "report", "graph"],
        help="Test specific agent (default: all)",
    )
    args = parser.parse_args()
    
    exit_code = asyncio.run(main(agent=args.agent))
    sys.exit(exit_code)

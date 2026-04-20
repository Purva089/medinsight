"""
RAGAS Evaluation for MedInsight RAG Pipeline.

Evaluates the RAG agent using industry-standard metrics:
  - Faithfulness: Is the answer grounded in the context?
  - Answer Relevancy: Is the answer relevant to the question?
  - Context Recall: Does the context contain necessary info?
  - Context Precision: How precise is the retrieved context?

Usage:
    pip install ragas datasets
    python evaluation/ragas_eval.py

Requires OPENAI_API_KEY for RAGAS default evaluation LLM, or configure
a different evaluator LLM.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

# ── RAGAS Test Dataset ────────────────────────────────────────────────────────

RAG_EVALUATION_DATASET = [
    {
        "question": "What is a normal hemoglobin level for adults?",
        "ground_truth": "Normal hemoglobin levels are 14-18 g/dL for men and 12-16 g/dL for women.",
        "expected_context_keywords": ["hemoglobin", "normal", "range", "g/dL"],
    },
    {
        "question": "What does high SGPT (ALT) indicate?",
        "ground_truth": "High SGPT/ALT levels can indicate liver damage, hepatitis, or other liver conditions.",
        "expected_context_keywords": ["liver", "ALT", "SGPT", "elevated", "damage"],
    },
    {
        "question": "What is a normal TSH level?",
        "ground_truth": "Normal TSH levels are typically 0.4-4.0 mIU/L for adults.",
        "expected_context_keywords": ["TSH", "thyroid", "normal", "mIU/L"],
    },
    {
        "question": "What does low platelet count mean?",
        "ground_truth": "Low platelet count (thrombocytopenia) can indicate bleeding disorders, bone marrow problems, or immune conditions.",
        "expected_context_keywords": ["platelet", "low", "thrombocytopenia"],
    },
    {
        "question": "What is HbA1c and what is a normal level?",
        "ground_truth": "HbA1c measures average blood sugar over 2-3 months. Normal is below 5.7%.",
        "expected_context_keywords": ["HbA1c", "blood", "glucose", "diabetes", "percent"],
    },
]


async def get_rag_response(question: str) -> tuple[str, list[str]]:
    """
    Call the RAG agent and return (answer, contexts).
    
    Returns:
        Tuple of (generated_answer, list_of_context_strings)
    """
    from app.agents.rag_agent import _get_index
    from app.agents.state import MedInsightState
    from app.agents.rag_agent import rag_node
    import uuid

    # Build minimal state for RAG
    state: MedInsightState = {
        "patient_id": str(uuid.uuid4()),
        "patient_profile": {"name": "Test"},
        "ltm_summary": "",
        "stm_messages": [],
        "current_question": question,
        "intent": "rag",
        "request_id": f"ragas-eval-{uuid.uuid4().hex[:8]}",
        "current_report_id": None,
        "extracted_tests": [{"test_name": "Hemoglobin", "value": 14.0, "unit": "g/dL", "status": "normal", "category": "blood_count"}],
        "extraction_confidence": 0.95,
        "rag_chunks": [],
        "rag_context": "",
        "others_tests": [],
        "disclaimer_required": False,
        "needs_rag": True,
        "needs_sql": False,
        "needs_trend": False,
        "needs_report_generation": False,
        "trend_results": [],
        "mentioned_tests": [],
        "sql_query_generated": None,
        "sql_results": [],
        "final_response": {},
        "errors": [],
        "a2a_messages": [],
    }

    result_state = await rag_node(state)
    
    # Extract context chunks
    contexts = [
        chunk.get("content", chunk.get("text", ""))
        for chunk in result_state.get("rag_chunks", [])
    ]
    
    # The RAG agent doesn't generate an answer, just retrieves context
    # For RAGAS, we'll use the rag_context as the "answer"
    answer = result_state.get("rag_context", "")
    
    return answer, contexts


def evaluate_with_ragas(dataset: list[dict]) -> dict:
    """
    Run RAGAS evaluation on the dataset.
    
    Requires: pip install ragas datasets
    """
    try:
        from ragas import evaluate  # type: ignore
        from ragas.metrics import (  # type: ignore
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        )
        from datasets import Dataset  # type: ignore
    except ImportError:
        print("❌ RAGAS not installed. Run: pip install ragas datasets")
        print("   Also requires OPENAI_API_KEY environment variable for evaluation LLM")
        return {"error": "ragas not installed"}

    # Prepare data for RAGAS
    questions = []
    answers = []
    contexts = []
    ground_truths = []

    print("\n📊 Collecting RAG responses for evaluation...\n")
    
    for i, item in enumerate(dataset, 1):
        question = item["question"]
        print(f"  [{i}/{len(dataset)}] {question}")
        
        # Get RAG response
        answer, context_list = asyncio.run(get_rag_response(question))
        
        questions.append(question)
        answers.append(answer if answer else "No relevant information found.")
        contexts.append(context_list if context_list else [""])
        ground_truths.append(item["ground_truth"])
        
        print(f"      Retrieved {len(context_list)} context chunks")

    # Create RAGAS dataset
    ragas_data = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths,
    })

    print("\n🔬 Running RAGAS evaluation (this may take a minute)...\n")

    # Run evaluation
    try:
        result = evaluate(
            ragas_data,
            metrics=[
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            ],
        )
        return result
    except Exception as e:
        print(f"❌ RAGAS evaluation failed: {e}")
        print("   Make sure OPENAI_API_KEY is set for the evaluation LLM")
        return {"error": str(e)}


def evaluate_simple(dataset: list[dict]) -> dict:
    """
    Simple keyword-based evaluation (fallback when RAGAS not available).
    """
    print("\n📊 Running simple keyword-based evaluation...\n")
    
    results = []
    
    for i, item in enumerate(dataset, 1):
        question = item["question"]
        expected_keywords = item["expected_context_keywords"]
        
        print(f"  [{i}/{len(dataset)}] {question}")
        
        answer, contexts = asyncio.run(get_rag_response(question))
        
        # Check if expected keywords appear in context
        all_context = " ".join(contexts).lower()
        found_keywords = [kw for kw in expected_keywords if kw.lower() in all_context]
        missing_keywords = [kw for kw in expected_keywords if kw.lower() not in all_context]
        
        keyword_recall = len(found_keywords) / len(expected_keywords) if expected_keywords else 0
        has_context = len(contexts) > 0
        
        passed = has_context and keyword_recall >= 0.5
        
        results.append({
            "question": question,
            "has_context": has_context,
            "context_count": len(contexts),
            "keyword_recall": keyword_recall,
            "found_keywords": found_keywords,
            "missing_keywords": missing_keywords,
            "passed": passed,
        })
        
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"      {status} | contexts={len(contexts)} | keyword_recall={keyword_recall:.0%}")
        if missing_keywords:
            print(f"      missing: {missing_keywords}")
        print()

    # Summary
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    avg_recall = sum(r["keyword_recall"] for r in results) / total if total else 0

    return {
        "passed": passed,
        "total": total,
        "pass_rate": passed / total if total else 0,
        "avg_keyword_recall": avg_recall,
        "results": results,
    }


def main():
    print("=" * 60)
    print("  MedInsight RAGAS Evaluation")
    print("=" * 60)

    # Try RAGAS first, fall back to simple evaluation
    try:
        import ragas  # type: ignore
        print("\n✓ RAGAS library found, using full evaluation")
        results = evaluate_with_ragas(RAG_EVALUATION_DATASET)
        
        if "error" not in results:
            print("\n" + "=" * 60)
            print("  RAGAS Scores")
            print("=" * 60)
            for metric, score in results.items():
                if isinstance(score, (int, float)):
                    print(f"  {metric}: {score:.3f}")
            print("=" * 60)
        else:
            print(f"\n⚠️  RAGAS error: {results['error']}")
            print("Falling back to simple evaluation...\n")
            results = evaluate_simple(RAG_EVALUATION_DATASET)
            
    except ImportError:
        print("\n⚠️  RAGAS not installed, using simple keyword evaluation")
        print("   To use RAGAS: pip install ragas datasets")
        print()
        results = evaluate_simple(RAG_EVALUATION_DATASET)

    # Print final summary for simple evaluation
    if isinstance(results, dict) and "pass_rate" in results:
        print("\n" + "=" * 60)
        print("  Simple Evaluation Summary")
        print("=" * 60)
        print(f"  Pass Rate: {results['passed']}/{results['total']} ({results['pass_rate']:.0%})")
        print(f"  Avg Keyword Recall: {results['avg_keyword_recall']:.0%}")
        print("=" * 60)
        
        if results["pass_rate"] < 1.0:
            print("\n❌ Some questions did not pass:")
            for r in results["results"]:
                if not r["passed"]:
                    print(f"  • {r['question'][:60]}...")
            sys.exit(1)
        else:
            print("\n✅ All questions passed!")


if __name__ == "__main__":
    main()

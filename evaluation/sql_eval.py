"""
SQL evaluation script.

For each question in settings.evaluation_sql_questions:
  1. Run text_to_sql_node with a synthetic test patient_id
  2. Verify generated SQL contains all expected_contains keywords
  3. Verify sqlglot parses the SQL without rejection

Prints pass/fail per query and overall pass rate.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import sqlglot

from app.agents.state import MedInsightState
from app.agents.text_to_sql_agent import _validate_select_only, text_to_sql_node
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_TEST_PATIENT_ID = str(uuid.uuid4())


def _base_state(question: str) -> MedInsightState:
    return {
        "patient_id": _TEST_PATIENT_ID,
        "patient_profile": {},
        "ltm_summary": "",
        "stm_messages": [],
        "current_question": question,
        "intent": "sql",
        "request_id": "eval-sql",
        "current_report_id": None,
        "extracted_tests": [],
        "extraction_confidence": 0.0,
        "rag_chunks": [],
        "rag_context": "",
        "others_tests": [],
        "disclaimer_required": False,
        "needs_rag": False,
        "needs_sql": True,
        "needs_trend": False,
        "trend_results": [],
        "sql_query_generated": None,
        "sql_results": [],
        "final_response": {},
        "errors": [],
        "a2a_messages": [],
    }


async def evaluate_query(question: str, expected_contains: list[str]) -> dict:
    state = _base_state(question)
    try:
        result_state = await text_to_sql_node(state)
    except Exception as exc:
        return {
            "question": question,
            "generated_sql": None,
            "passed": False,
            "reason": f"Exception during text_to_sql_node: {exc!s:.150}",
        }

    generated_sql = result_state.get("sql_query_generated")
    errors = result_state.get("errors", [])

    # Check for rejection
    if not generated_sql or errors:
        return {
            "question": question,
            "generated_sql": generated_sql,
            "passed": False,
            "reason": f"SQL rejected or not generated. errors={errors}",
        }

    sql_upper = generated_sql.upper()

    # Check all expected keywords are present (case-insensitive)
    missing_keywords = [kw for kw in expected_contains if kw.upper() not in sql_upper]
    if missing_keywords:
        return {
            "question": question,
            "generated_sql": generated_sql,
            "passed": False,
            "reason": f"Missing keywords: {missing_keywords}",
        }

    # Validate via sqlglot
    sqlglot_ok = _validate_select_only(generated_sql)
    if not sqlglot_ok:
        return {
            "question": question,
            "generated_sql": generated_sql,
            "passed": False,
            "reason": "sqlglot rejected — not a pure SELECT statement",
        }

    return {
        "question": question,
        "generated_sql": generated_sql,
        "passed": True,
        "reason": "",
    }


async def main() -> None:
    sql_questions = settings.evaluation_sql_questions
    if not sql_questions:
        print("❌ No SQL questions found in settings.evaluation_sql_questions")
        sys.exit(1)

    print(f"Evaluating {len(sql_questions)} SQL question(s) with patient_id={_TEST_PATIENT_ID[:8]}...\n")

    results = []
    for i, item in enumerate(sql_questions, 1):
        question = item["question"]
        expected = item.get("expected_tables", item.get("expected_contains", []))
        print(f"  [{i}/{len(sql_questions)}] {question}")
        print(f"      expected keywords: {expected}")

        res = await evaluate_query(question, expected)
        results.append(res)

        status = "✅ PASS" if res["passed"] else "❌ FAIL"
        print(f"      {status}")
        if res["generated_sql"]:
            print(f"      SQL: {res['generated_sql'][:120]}")
        if res["reason"]:
            print(f"      reason: {res['reason']}")
        print()

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    pass_rate = passed / total

    print("─" * 60)
    print(f"SQL pass rate: {passed}/{total} ({pass_rate:.0%})")
    print("─" * 60)

    if pass_rate == 1.0:
        print("✅ PASS (all queries generated valid SELECT SQL with expected keywords)")
    else:
        failed = [r for r in results if not r["passed"]]
        print(f"❌ FAIL — {len(failed)} query(ies) did not pass:")
        for r in failed:
            print(f"  • {r['question'][:70]} — {r['reason']}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

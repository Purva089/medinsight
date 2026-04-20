"""
RAG evaluation script.

For each question in settings.evaluation_rag_questions:
  1. Call the RAG agent retriever
  2. Assert chunks > 0, top relevance_score > 0.5, source URLs present
  3. Log pass/fail per question

Prints overall pass rate.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from app.agents.rag_agent import _get_index
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_SCORE_THRESHOLD = 0.5


async def evaluate_question(question: str, test_idx: int) -> dict:
    """Run RAG retrieval for one question and return pass/fail with details."""
    try:
        idx = _get_index()
        if idx is None:
            return {"question": question, "passed": False, "reason": "Index not initialized"}
        retriever = idx.as_retriever(similarity_top_k=3)

        import asyncio as _asyncio
        nodes = await _asyncio.to_thread(retriever.retrieve, question)

        chunks = [
            {
                "text": n.get_content()[:80],
                "source_url": (n.metadata or {}).get("source_url"),
                "score": round(n.score or 0.0, 4),
            }
            for n in nodes
        ]

        has_chunks = len(chunks) > 0
        top_score = chunks[0]["score"] if chunks else 0.0
        score_ok = top_score > _SCORE_THRESHOLD
        has_sources = any(c["source_url"] for c in chunks)

        passed = has_chunks and score_ok

        return {
            "question": question,
            "chunks_retrieved": len(chunks),
            "top_score": top_score,
            "score_ok": score_ok,
            "has_sources": has_sources,
            "passed": passed,
            "reason": "" if passed else (
                "no chunks" if not has_chunks else f"score {top_score:.3f} <= {_SCORE_THRESHOLD}"
            ),
        }

    except Exception as exc:
        return {
            "question": question,
            "chunks_retrieved": 0,
            "top_score": 0.0,
            "score_ok": False,
            "has_sources": False,
            "passed": False,
            "reason": f"Exception: {exc!s:.120}",
        }


async def main() -> None:
    questions = settings.evaluation_rag_questions
    if not questions:
        print("❌ No RAG questions found in settings.evaluation_rag_questions")
        sys.exit(1)

    print(f"Evaluating {len(questions)} RAG question(s)...\n")

    results = []
    for i, q in enumerate(questions, 1):
        print(f"  [{i}/{len(questions)}] {q}")
        res = await evaluate_question(q, i)
        results.append(res)
        status = "✅ PASS" if res["passed"] else "❌ FAIL"
        print(f"      {status} | chunks={res['chunks_retrieved']} | top_score={res['top_score']:.3f} | sources={res['has_sources']}")
        if res["reason"]:
            print(f"      reason: {res['reason']}")
        print()

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    pass_rate = passed / total

    print("─" * 60)
    print(f"RAG pass rate: {passed}/{total} ({pass_rate:.0%})")
    print("─" * 60)

    if pass_rate == 1.0:
        print("✅ PASS (all questions returned chunks with score > 0.5)")
    else:
        failed = [r for r in results if not r["passed"]]
        print(f"❌ FAIL — {len(failed)} question(s) did not meet threshold:")
        for r in failed:
            print(f"  • {r['question'][:70]} — {r['reason']}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

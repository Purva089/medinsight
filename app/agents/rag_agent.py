"""
RAG agent — retrieves relevant medical knowledge from pgvector.

Skips retrieval entirely for "others" category tests — the knowledge base
has no data for unsupported tests, so we return a structured unavailable notice.
"""
from __future__ import annotations

from app.agents.state import MedInsightState
from app.core.categories import SUPPORTED_CATEGORIES
from app.core.logging import get_logger
from app.services.knowledge_base import get_embed_model, get_index

log = get_logger(__name__)

_embed_model = None
_index = None


def _get_index():
    global _embed_model, _index
    if _index is None:
        _embed_model = get_embed_model()
        _index = get_index(_embed_model)
    return _index


def _split_tests_by_category(
    extracted_tests: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Split tests into:
      supported : have a category in SUPPORTED_CATEGORIES
      others    : category == "others" or missing
    """
    supported, others = [], []
    for t in extracted_tests:
        cat = t.get("category", "others")
        if cat in SUPPORTED_CATEGORIES:
            supported.append(t)
        else:
            others.append(t)
    return supported, others


async def rag_node(state: MedInsightState) -> MedInsightState:
    """
    Retrieve top-3 relevant knowledge chunks from pgvector.

    Only queries pgvector for tests in supported categories.
    Tests with category "others" receive a knowledge-unavailable notice
    without touching pgvector.

    Sets state["rag_chunks"], state["rag_context"], state["others_tests"].
    On failure: sets disclaimer_required=True and continues.
    """
    import asyncio

    question = state["current_question"]
    extracted_tests = state.get("extracted_tests", [])

    supported_tests, others_tests = _split_tests_by_category(extracted_tests)

    # Store "others" tests in state for the report agent to handle separately
    state["others_tests"] = others_tests

    if others_tests:
        log.info(
            "rag_others_tests_skipped",
            others_count=len(others_tests),
            others_names=[t.get("test_name") for t in others_tests],
        )

    # If ALL tests are "others" and there are no supported tests → skip RAG
    if not supported_tests and extracted_tests:
        log.info(
            "rag_all_tests_unsupported",
            total_tests=len(extracted_tests),
        )
        state["rag_chunks"] = []
        state["rag_context"] = ""
        state["disclaimer_required"] = True
        return state

    supported_names = [t.get("test_name", "") for t in supported_tests]

    enriched_query = (
        f"{question} {' '.join(supported_names)} normal range interpretation"
        if supported_names
        else question
    )

    log.info(
        "rag_retrieving",
        question_preview=question[:80],
        enriched_query_preview=enriched_query[:120],
        supported_tests=supported_names,
        others_tests=[t.get("test_name") for t in others_tests],
    )

    try:
        idx = _get_index()
        retriever = idx.as_retriever(similarity_top_k=3)
        nodes = await asyncio.to_thread(retriever.retrieve, enriched_query)

        chunks: list[dict] = []
        for node in nodes:
            meta = node.metadata or {}
            score = round(node.score or 0.0, 4)
            source = meta.get("file_name", meta.get("source_file", "unknown"))
            # Only accept chunks that match the category of supported tests
            chunk_cat = meta.get("category", "")
            chunks.append({
                "text": node.get_content(),
                "source_url": meta.get("source_url"),
                "source_file": source,
                "relevance_score": score,
                "category": chunk_cat,
                "doc_type": meta.get("doc_type", ""),
            })
            log.debug(
                "rag_chunk",
                source_file=source,
                category=chunk_cat,
                doc_type=meta.get("doc_type", ""),
                relevance_score=score,
                text_len=len(node.get_content()),
            )

        state["rag_chunks"] = chunks
        state["rag_context"] = "\n\n".join(
            f"[{c['source_file']} | {c['category']} | {c['doc_type']}]\n{c['text']}"
            for c in chunks
        )

        if not chunks:
            state["disclaimer_required"] = True
            log.warning(
                "rag_empty_result",
                disclaimer_required=True,
                enriched_query_preview=enriched_query[:120],
            )
        else:
            log.info(
                "rag_chunks_retrieved",
                count=len(chunks),
                top_score=chunks[0]["relevance_score"],
                context_chars=len(state["rag_context"]),
                sources=[c["source_file"] for c in chunks],
            )

    except Exception as exc:
        log.error("rag_node_error", error=str(exc)[:200], exc_info=True)
        state["rag_chunks"] = []
        state["rag_context"] = ""
        state["disclaimer_required"] = True
        state["errors"] = state.get("errors", []) + [f"RAG error: {exc!s:.100}"]

    return state


    return state

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

# Module-level cache for embedding model and index
# These are initialized once on first use and reused across all requests
_embed_model = None
_index = None
_initialized = False


def _get_index():
    """Get or create the vector index. Caches at module level for reuse."""
    global _embed_model, _index, _initialized
    if not _initialized:
        log.info("rag_initializing_index", status="starting")
        _embed_model = get_embed_model()
        _index = get_index(_embed_model)
        _initialized = True
        log.info("rag_index_ready", status="complete")
    return _index


def prewarm_rag():
    """Pre-warm the RAG index. Called during app startup."""
    log.info("rag_prewarm_started", message="Pre-warming RAG index and embedding model")
    try:
        _ = _get_index()  # This will trigger initialization
        log.info("rag_prewarm_complete", message="RAG index ready for queries")
    except Exception as exc:
        log.error("rag_prewarm_failed", error=str(exc)[:200], exc_info=True)


from app.core.categories import SUPPORTED_CATEGORIES, classify_test


_CLINIC_DIR = None

def _get_clinic_dir():
    global _CLINIC_DIR
    if _CLINIC_DIR is None:
        from pathlib import Path
        _CLINIC_DIR = Path(__file__).resolve().parents[2] / "data" / "knowledge_base" / "clinics"
    return _CLINIC_DIR


def _load_clinic_context(supported_tests: list[dict]) -> str:
    """
    Read clinic file for the categories of the given tests and return
    the first doctor entry as formatted text — guaranteed to appear in
    rag_context regardless of vector search ranking.
    """
    if not supported_tests:
        return ""
    # Collect unique categories that have abnormal tests
    categories = list({
        t.get("category", "others")
        for t in supported_tests
        if t.get("status", "").lower() in ("high", "low", "critical")
    })
    if not categories:
        # Include clinic info for all supported categories even if status unknown
        categories = list({t.get("category", "others") for t in supported_tests})

    clinic_dir = _get_clinic_dir()
    parts = []
    for cat in categories:
        clinic_file = clinic_dir / f"clinics_{cat}.txt"
        if not clinic_file.exists():
            continue
        try:
            text = clinic_file.read_text(encoding="utf-8")
            # Extract first doctor block (between first two --- separators)
            blocks = [b.strip() for b in text.split("---") if b.strip() and "doctor_name" in b]
            if blocks:
                parts.append(
                    f"[clinics_{cat}.txt | {cat} | clinic_info]\n{blocks[0]}"
                )
        except Exception:
            continue
    return "\n\n".join(parts)


def _split_tests_by_category(
    extracted_tests: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Split tests into:
      supported : have a category in SUPPORTED_CATEGORIES
      others    : category == "others" or missing
    
    Also re-classifies tests at runtime in case they were stored with wrong category.
    """
    supported, others = [], []
    for t in extracted_tests:
        # First check stored category
        cat = t.get("category", "others")
        
        # If category is "others", try to re-classify from test name
        # This handles cases where tests were stored before category mapping was updated
        if cat == "others" or cat not in SUPPORTED_CATEGORIES:
            test_name = t.get("test_name", "")
            reclassified = classify_test(test_name)
            if reclassified and reclassified in SUPPORTED_CATEGORIES:
                cat = reclassified
                t["category"] = cat  # Update in-place for downstream use
                log.debug("rag_reclassified_test", test_name=test_name, new_category=cat)
        
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
        if idx is None:
            raise RuntimeError("Index not initialized")
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

        # Deterministically append clinic info for the test categories found
        # This ensures clinic details always appear for abnormal supported tests,
        # regardless of whether the vector search ranked the clinic chunk in top-3
        clinic_context = _load_clinic_context(supported_tests)
        if clinic_context:
            state["rag_context"] += "\n\n" + clinic_context
            log.info("rag_clinic_context_appended", chars=len(clinic_context))

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

    # RAG agent's job is done - return state with rag_chunks and rag_context
    # synthesis_agent will format the final response with proper safeguards and LLM formatting
    log.info(
        "rag_agent_complete",
        patient_id=state.get("patient_id", "?"),
        chunks_retrieved=len(state.get("rag_chunks", [])),
        context_length=len(state.get("rag_context", "")),
    )

    return state

"""
Orchestrator agent — classifies intent, routes to specialised agents,
and runs the category classifier sub-task for extracted tests.

First node in the LangGraph pipeline:
1. Classifies user intent using LLM
2. Runs category classifier on extracted_tests (sub-task)
3. Routes to the appropriate specialised agents
"""
from __future__ import annotations

from app.agents.state import MedInsightState
from app.core.categories import classify_test
from app.core.logging import get_logger, AgentLogger
from app.core.prompts import PROMPT_CLASSIFICATION
from app.schemas.enums import IntentType
from app.services.llm_service import llm_service as _llm

log = get_logger(__name__)
agent_log = AgentLogger("orchestrator")


def _classify_extracted_tests(extracted_tests: list[dict]) -> list[dict]:
    """
    Sub-task: categorise every extracted test and filter out excluded ones.

    Mutates each test dict in-place to add / overwrite the 'category' key.
    Tests whose classify_test() returns None are removed (excluded tests).
    """
    kept: list[dict] = []
    for test in extracted_tests:
        name = test.get("test_name", "")
        cat = classify_test(name)
        if cat is None:
            log.debug("orchestrator_test_excluded", test_name=name)
            continue          # Troponin I, CK-MB, BNP → skip
        test = dict(test)     # shallow copy — don't mutate original
        test["category"] = cat
        kept.append(test)
    return kept


async def orchestrator_node(state: MedInsightState) -> MedInsightState:
    """
    Step 1 of the graph.

    1. Run category classifier on extracted_tests (sub-task, no LLM).
    2. Call LLM to classify intent.
    3. Set state["intent"] and state["extracted_tests"].
    """
    patient_id = state["patient_id"]
    question = state["current_question"]
    extracted_tests = state.get("extracted_tests", [])

    # Start agent execution tracking
    agent_log.start(
        task="intent_classification",
        input_preview=question[:80],
    )

    # ── Sub-task: classify + filter extracted tests ───────────────────────────
    if extracted_tests:
        classified = _classify_extracted_tests(extracted_tests)
        excluded_count = len(extracted_tests) - len(classified)
        log.info(
            "orchestrator_tests_classified",
            patient_id=patient_id,
            total=len(extracted_tests),
            kept=len(classified),
            excluded=excluded_count,
        )
        state["extracted_tests"] = classified

    # ── LLM classification ────────────────────────────────────────────────────
    prompt = PROMPT_CLASSIFICATION.format(question=question)
    intent_str = IntentType.RAG.value   # safe default (was GENERAL)

    log.info(
        "orchestrator_classifying",
        patient_id=patient_id,
        question_preview=question[:80],
        prompt_len=len(prompt),
    )

    try:
        # Use fast model for classification (smaller, faster)
        raw = await _llm.call_fast(prompt, max_tokens=10)
        raw_clean = raw.strip().lower().split()[0] if raw.strip() else ""
        
        # Handle common synonyms and map to core intents
        intent_synonyms = {
            # RAG synonyms (understanding/explanation)
            "explain": "rag",
            "explanation": "rag",
            "meaning": "rag",
            "interpret": "rag",
            "understand": "rag",
            "why": "rag",
            "what": "rag",
            # SQL synonyms (querying/listing)
            "list": "sql",
            "show": "sql",
            "retrieve": "sql",
            "query": "sql",
            "get": "sql",
            "find": "sql",
            "summary": "sql",
            "summarize": "sql",
            "overview": "sql",
            # TREND synonyms (temporal analysis)
            "change": "trend",
            "changes": "trend",
            "history": "trend",
            "improving": "trend",
            "trend": "trend",
            "compare": "trend",
            # Off-topic fallback to RAG (safeguards will block)
            "hi": "rag",
            "hello": "rag",
            "thanks": "rag",
        }
        raw_clean = intent_synonyms.get(raw_clean, raw_clean)
        
        # Map raw string to IntentType
        is_known = raw_clean in IntentType._value2member_map_  # type: ignore[attr-defined]
        intent_str = IntentType(raw_clean).value if is_known else IntentType.RAG.value  # type: ignore[attr-defined]

        log.debug(
            "orchestrator_classification_raw",
            raw_output=raw.strip()[:100],
            cleaned=raw_clean,
            known_intent=is_known,
        )
    except Exception as exc:
        agent_log.error(exc)
        log.error(
            "orchestrator_classification_error",
            patient_id=patient_id,
            error=str(exc)[:200],
            exc_info=True,
        )
        state["errors"] = state.get("errors", []) + [f"Classification LLM error: {exc!s:.100}"]

    state["intent"] = intent_str

    # ── Set execution flags ───────────────────────────────────────────────────
    # These are read by route_after_orchestrator() in graph.py to decide
    # which agents run and whether to parallelise.  The LLM only answers
    # "what does the user want?" — the orchestrator answers "which agents?".
    question_lower = question.lower()

    needs_rag   = intent_str == IntentType.RAG.value
    needs_sql   = intent_str == IntentType.SQL.value
    needs_trend = intent_str == IntentType.TREND.value

    # Detect report generation requests
    report_keywords = [
        "generate report", "create report", "download report",
        "generate pdf", "create pdf", "download pdf",
        "export report", "make report", "full report",
        "comprehensive report", "detailed report"
    ]
    needs_report_generation = any(kw in question_lower for kw in report_keywords)

    # If the question mentions a known test name alongside sql/trend,
    # also pull RAG context automatically (parallel enrichment).
    # AND extract the specific test name for trend queries
    mentioned_tests = []
    if intent_str in (IntentType.SQL.value, IntentType.TREND.value):
        from app.core.categories import CATEGORY_MAP  # local import to avoid circularity
        import re
        
        # Sort test names by length (longest first) to match "hemoglobin a1c" before "hemoglobin"
        sorted_tests = sorted(CATEGORY_MAP.keys(), key=len, reverse=True)
        
        for test_name in sorted_tests:
            # Use word boundary matching to avoid substring matches
            # "hemoglobin" should NOT match "hemoglobin a1c"
            pattern = r'\b' + re.escape(test_name) + r'\b'
            if re.search(pattern, question_lower):
                needs_rag = True
                if intent_str == IntentType.TREND.value:
                    # Store the specific test name for trend queries (exact DB format)
                    # Database has "Hemoglobin", "WBC Count", etc. (title case)
                    standardized_name = test_name.replace("_", " ").title()
                    if standardized_name not in mentioned_tests:  # Avoid duplicates
                        mentioned_tests.append(standardized_name)
        
        log.debug(
            "orchestrator_mentioned_tests",
            question=question[:50],
            mentioned_tests=mentioned_tests,
            intent=intent_str,
        )
    
    # Store mentioned test names for trend agent to filter
    if mentioned_tests:
        state["mentioned_tests"] = mentioned_tests
    
    # If generating a report, ALWAYS include trend analysis (for charts)
    if needs_report_generation:
        needs_trend = True

    state["needs_rag"]   = needs_rag
    state["needs_sql"]   = needs_sql
    state["needs_trend"] = needs_trend
    state["needs_report_generation"] = needs_report_generation

    agent_log.complete(
        status="success",
        intent=intent_str,
        needs_rag=needs_rag,
        needs_sql=needs_sql,
        needs_trend=needs_trend,
        needs_report_generation=needs_report_generation,
    )

    log.info(
        "orchestrator_classified",
        patient_id=patient_id,
        question_preview=question[:80],
        intent=intent_str,
        needs_rag=needs_rag,
        needs_sql=needs_sql,
        needs_trend=needs_trend,
        needs_report_generation=needs_report_generation,
    )
    return state


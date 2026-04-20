from enum import Enum


class IntentType(str, Enum):
    RAG     = "rag"      # medical knowledge / what does a result mean
    SQL     = "sql"      # retrieve own records from DB (includes summaries)
    TREND   = "trend"    # how has a value changed over time
    # NO GENERAL FALLBACK: every question must map to rag/sql/trend
    # Parallel execution is decided by orchestrator flags (needs_rag,
    # needs_sql, needs_trend), not by LLM-classified intents.

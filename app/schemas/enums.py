from enum import Enum


class IntentType(str, Enum):
    RAG     = "rag"      # medical knowledge / what does a result mean
    SQL     = "sql"      # retrieve own records from DB
    TREND   = "trend"    # how has a value changed over time
    GENERAL = "general"  # fallback → routes to RAG
    # Parallel execution is decided by orchestrator flags (needs_rag,
    # needs_sql, needs_trend), not by LLM-classified intents.

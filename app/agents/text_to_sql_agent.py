"""
Text-to-SQL agent — converts a natural language question to a SQL SELECT,
validates with sqlglot, and executes on a read-only DB session.
"""
from __future__ import annotations

import json

import sqlglot
from sqlalchemy import text

from app.agents.state import MedInsightState
from app.core.database import AsyncSessionLocal, engine
from app.core.prompts import PROMPT_TEXT_TO_SQL
from app.core.logging import get_logger
from app.models.base import Base
from app.services.llm_service import llm_service as _llm

log = get_logger(__name__)


def _build_schema_description() -> str:
    """
    Dynamically build a table+column summary from SQLAlchemy metadata.
    Never hardcode table names here.
    """
    lines: list[str] = []
    for table in Base.metadata.sorted_tables:
        cols = ", ".join(c.name for c in table.columns)
        lines.append(f"{table.name}({cols})")
    return "; ".join(lines)


def _validate_select_only(sql: str) -> bool:
    """
    Use sqlglot to parse and confirm the statement is a SELECT only.
    Returns True if safe, False otherwise.
    """
    try:
        statements = sqlglot.parse(sql, dialect="postgres")
        if not statements:
            return False
        for stmt in statements:
            if not isinstance(stmt, sqlglot.expressions.Select):
                return False
        return True
    except Exception:
        return False


async def text_to_sql_node(state: MedInsightState) -> MedInsightState:
    """
    1. Build schema description from metadata.
    2. Format prompt with patient_id from state (never from user input).
    3. Call LLM to generate SQL.
    4. Validate with sqlglot — reject non-SELECT.
    5. Execute on read-only session.
    6. Store results in state.
    """
    patient_id = state["patient_id"]
    question = state["current_question"]

    schema_desc = _build_schema_description()
    prompt = PROMPT_TEXT_TO_SQL.format(
        patient_id=patient_id,
        schema_description=schema_desc,
        question=question,
    )

    sql_query: str | None = None
    sql_results: list[dict] = []

    log.info(
        "sql_agent_start",
        patient_id=patient_id,
        question_preview=question[:80],
        prompt_len=len(prompt),
    )

    try:
        raw_sql = await _llm.call_reasoning(prompt, max_tokens_key="text_to_sql")
        # Strip markdown fences if present
        raw_sql = raw_sql.strip()
        if raw_sql.startswith("```"):
            lines = raw_sql.split("\n")
            raw_sql = "\n".join(ln for ln in lines if not ln.startswith("```")).strip()

        log.info(
            "sql_generated",
            patient_id=patient_id,
            sql_preview=raw_sql[:300],
        )

        if not _validate_select_only(raw_sql):
            log.warning(
                "sql_rejected_not_select",
                generated_sql=raw_sql[:300],
            )
            state["sql_query_generated"] = raw_sql
            state["sql_results"] = []
            state["errors"] = state.get("errors", []) + [
                f"Generated SQL rejected (not a SELECT): {raw_sql[:100]}"
            ]
            return state

        sql_query = raw_sql

        # Execute on a separate read-only connection
        async with engine.connect() as conn:
            # Set transaction to read-only at the DB level
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            result = await conn.execute(text(sql_query))
            cols = list(result.keys())
            sql_results = [dict(zip(cols, row)) for row in result.fetchall()]

        log.info(
            "sql_executed",
            patient_id=patient_id,
            sql_preview=sql_query[:200],
            row_count=len(sql_results),
            columns=list(sql_results[0].keys()) if sql_results else [],
        )

    except Exception as exc:
        log.error("text_to_sql_error", error=str(exc)[:200], exc_info=True)
        state["errors"] = state.get("errors", []) + [f"Text-to-SQL error: {exc!s:.100}"]

    state["sql_query_generated"] = sql_query
    state["sql_results"] = sql_results
    log.info(
        "sql_agent_complete",
        patient_id=patient_id,
        row_count=len(sql_results),
        errors=len(state.get("errors", [])),
    )
    return state

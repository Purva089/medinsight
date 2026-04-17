"""
LangGraph graph assembly for MedInsight.

Architecture (LangGraph Native Parallel with Send):
───────────────────────────────────────────────────

  User Question
       │
       ▼
  ┌──────────────┐
  │ orchestrator │  ← LLM classifies intent, Python sets needs_* flags
  └──────┬───────┘
         │
         ▼
  route_to_agents()  ← Returns Send() objects for EACH needed agent
         │
    ┌────┴────┬────────────┐   (parallel fan-out via LangGraph Send)
    ▼         ▼            ▼
┌───────┐ ┌───────┐ ┌────────────┐
│  RAG  │ │ Trend │ │ Text2SQL   │   ← Run in parallel automatically
└───┬───┘ └───┬───┘ └─────┬──────┘
    │         │           │
    └────┬────┴───────────┘
         │
         ▼ (fan-in via state reducers)
  ┌──────────────┐
  │ report_agent │  ← Synthesises all results into final response
  └──────┬───────┘
         │
         ▼
        END

Key LangGraph features used:
  • Send() for conditional parallel fan-out (no explicit parallel nodes!)
  • Annotated reducers for automatic state merge from parallel branches
  • LangGraph decides parallelism — not hardcoded node combinations

Each node is wrapped by ``traced_node`` for structured logging.
"""
from __future__ import annotations

import functools
import time
from typing import Callable, Awaitable, Annotated, Sequence

from langgraph.constants import Send
from langgraph.graph import END, StateGraph

from app.agents.orchestrator import orchestrator_node
from app.agents.rag_agent import rag_node
from app.agents.report_agent import report_node
from app.agents.state import MedInsightState
from app.agents.text_to_sql_agent import text_to_sql_node
from app.agents.trend_agent import trend_node
from app.core.logging import get_logger

log = get_logger(__name__)


# ── Reducer functions for parallel state merge ────────────────────────────────

def merge_lists(left: list, right: list) -> list:
    """Reducer: concatenate lists from parallel branches."""
    return (left or []) + (right or [])


def merge_str(left: str, right: str) -> str:
    """Reducer: concatenate strings (for rag_context)."""
    if not left:
        return right or ""
    if not right:
        return left
    return f"{left}\n\n{right}"


def merge_bool_or(left: bool, right: bool) -> bool:
    """Reducer: OR booleans (disclaimer_required from any branch)."""
    return left or right


def keep_last(left: str | None, right: str | None) -> str | None:
    """Reducer: keep non-None value (for sql_query_generated)."""
    return right if right is not None else left


# ── State with reducers for parallel merge ────────────────────────────────────

class ParallelMedInsightState(MedInsightState, total=False):
    """
    Extended state with Annotated reducers for LangGraph parallel fan-in.
    
    When multiple agents run in parallel and write to the same field,
    the reducer function merges their outputs automatically.
    """
    # Override list fields with merge reducer
    rag_chunks: Annotated[list, merge_lists]
    trend_results: Annotated[list, merge_lists]
    sql_results: Annotated[list, merge_lists]
    errors: Annotated[list, merge_lists]
    others_tests: Annotated[list, merge_lists]

    # Override string fields
    rag_context: Annotated[str, merge_str]

    # Override optional string
    sql_query_generated: Annotated[str | None, keep_last]

    # Override bool with OR
    disclaimer_required: Annotated[bool, merge_bool_or]


# ── tracing decorator ─────────────────────────────────────────────────────────

def traced_node(
    name: str,
) -> Callable[
    [Callable[..., Awaitable[MedInsightState]]],
    Callable[..., Awaitable[MedInsightState]],
]:
    """
    Decorator that wraps an async agent node with structured enter/exit logs.

    Emits:
      ``node_enter``  – before the node runs (node, patient_id, intent)
      ``node_exit``   – after the node runs   (node, duration_ms, error_count)
    """

    def decorator(
        fn: Callable[..., Awaitable[MedInsightState]],
    ) -> Callable[..., Awaitable[MedInsightState]]:
        @functools.wraps(fn)
        async def wrapper(state: MedInsightState) -> MedInsightState:
            patient_id = state.get("patient_id", "?")
            intent = state.get("intent", "—")

            log.info(
                "node_enter",
                node=name,
                patient_id=patient_id,
                intent=intent,
            )
            t0 = time.perf_counter()

            try:
                result = await fn(state)
            except Exception as exc:
                duration_ms = round((time.perf_counter() - t0) * 1000)
                log.error(
                    "node_error",
                    node=name,
                    patient_id=patient_id,
                    duration_ms=duration_ms,
                    exc_type=type(exc).__name__,
                    error=str(exc)[:300],
                    exc_info=True,
                )
                raise

            duration_ms = round((time.perf_counter() - t0) * 1000)
            errors = result.get("errors", [])
            log.info(
                "node_exit",
                node=name,
                patient_id=patient_id,
                intent=result.get("intent", intent),
                duration_ms=duration_ms,
                error_count=len(errors),
                errors=errors if errors else None,
            )
            return result

        return wrapper

    return decorator


# ── LangGraph routing with Send() for parallel execution ──────────────────────

def route_to_agents(state: MedInsightState) -> Sequence[Send]:
    """
    LangGraph conditional fan-out using Send().

    Returns a list of Send() objects — one for each agent that should run.
    LangGraph automatically executes them in parallel and merges results
    using the reducers defined in ParallelMedInsightState.

    This is the PROPER LangGraph way to do conditional parallel execution,
    not explicit "parallel_rag_trend" nodes.
    """
    needs_rag = state.get("needs_rag", False)
    needs_sql = state.get("needs_sql", False)
    needs_trend = state.get("needs_trend", False)
    intent = state.get("intent", "general")

    sends: list[Send] = []

    if needs_rag:
        sends.append(Send("rag_agent", state))
        log.debug("route_send", target="rag_agent", intent=intent)

    if needs_sql:
        sends.append(Send("text_to_sql_agent", state))
        log.debug("route_send", target="text_to_sql_agent", intent=intent)

    if needs_trend:
        sends.append(Send("trend_agent", state))
        log.debug("route_send", target="trend_agent", intent=intent)

    # Default: if nothing selected, run RAG (handles "general" intent)
    if not sends:
        sends.append(Send("rag_agent", state))
        log.debug("route_send", target="rag_agent", reason="default_fallback")

    log.info(
        "graph_routing",
        intent=intent,
        needs_rag=needs_rag,
        needs_sql=needs_sql,
        needs_trend=needs_trend,
        parallel_count=len(sends),
        targets=[s.node for s in sends],
        patient_id=state.get("patient_id", "?"),
    )

    return sends


# ── graph construction ────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """
    Build the MedInsight LangGraph with native parallel execution.

    Flow:
      orchestrator → [parallel agents via Send()] → report_agent → END

    The orchestrator sets needs_rag/needs_sql/needs_trend flags.
    route_to_agents() returns Send() objects for each needed agent.
    LangGraph runs them in parallel and merges state via reducers.
    report_agent receives the merged state and generates the final response.
    """
    graph = StateGraph(ParallelMedInsightState)

    # ── Add nodes (only 5 real agents, no synthetic parallel nodes) ───────────
    graph.add_node("orchestrator", traced_node("orchestrator")(orchestrator_node))
    graph.add_node("rag_agent", traced_node("rag_agent")(rag_node))
    graph.add_node("trend_agent", traced_node("trend_agent")(trend_node))
    graph.add_node("text_to_sql_agent", traced_node("text_to_sql_agent")(text_to_sql_node))
    graph.add_node("report_agent", traced_node("report_agent")(report_node))

    # ── Entry point ───────────────────────────────────────────────────────────
    graph.set_entry_point("orchestrator")

    # ── Conditional fan-out: orchestrator → [agents in parallel] ──────────────
    # route_to_agents returns Send() objects — LangGraph handles parallelism
    graph.add_conditional_edges("orchestrator", route_to_agents)

    # ── All agents converge to report_agent ───────────────────────────────────
    # State is automatically merged via reducers before report_agent runs
    graph.add_edge("rag_agent", "report_agent")
    graph.add_edge("trend_agent", "report_agent")
    graph.add_edge("text_to_sql_agent", "report_agent")

    # ── Final output ──────────────────────────────────────────────────────────
    graph.add_edge("report_agent", END)

    return graph


# ── Compiled graph (singleton) ────────────────────────────────────────────────

compiled_graph = build_graph().compile()


# ── Visualisation helper (for debugging) ──────────────────────────────────────

def get_graph_mermaid() -> str:
    """Return Mermaid diagram of the graph for documentation."""
    return compiled_graph.get_graph().draw_mermaid()

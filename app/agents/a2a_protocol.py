"""
Agent-to-Agent (A2A) Communication Protocol for MedInsight.

This module enables explicit agent-to-agent interactions where one agent
can request services from another agent, demonstrating true A2A collaboration.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from app.agents.state import MedInsightState
from app.core.logging import get_logger

log = get_logger(__name__)


# ── A2A Message Types ──────────────────────────────────────────────────────────

@dataclass
class A2ARequest:
    """Request from one agent to another."""
    request_id: str
    source_agent: str
    target_agent: str
    action: str
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "action": self.action,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class A2AResponse:
    """Response from one agent to another."""
    request_id: str
    source_agent: str
    target_agent: str
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


# ── A2A Communication Hub ──────────────────────────────────────────────────────

class A2ACommunicationHub:
    """
    Central hub for agent-to-agent communication.
    
    Agents register their capabilities and can request services from other agents.
    This enables true A2A collaboration beyond shared state.
    """
    
    def __init__(self) -> None:
        self._agents: dict[str, Callable[..., Awaitable[A2AResponse]]] = {}
        self._message_log: list[dict[str, Any]] = []
    
    def register_agent(
        self,
        agent_name: str,
        handler: Callable[[A2ARequest, MedInsightState], Awaitable[A2AResponse]],
    ) -> None:
        """Register an agent's request handler."""
        self._agents[agent_name] = handler
        log.info("a2a_agent_registered", agent=agent_name)
    
    async def send_request(
        self,
        request: A2ARequest,
        state: MedInsightState,
    ) -> A2AResponse:
        """
        Send a request from one agent to another.
        
        Returns the response from the target agent.
        """
        log.info(
            "a2a_request_sent",
            request_id=request.request_id,
            source=request.source_agent,
            target=request.target_agent,
            action=request.action,
        )
        
        
        self._message_log.append({
            "type": "request",
            **request.to_dict(),
        })
        
        # Check if target agent is registered
        if request.target_agent not in self._agents:
            response = A2AResponse(
                request_id=request.request_id,
                source_agent=request.target_agent,
                target_agent=request.source_agent,
                success=False,
                error=f"Unknown agent: {request.target_agent}",
            )
        else:
            # Call the target agent
            handler = self._agents[request.target_agent]
            try:
                response = await handler(request, state)
            except Exception as exc:
                log.error(
                    "a2a_request_error",
                    request_id=request.request_id,
                    target=request.target_agent,
                    error=str(exc),
                )
                response = A2AResponse(
                    request_id=request.request_id,
                    source_agent=request.target_agent,
                    target_agent=request.source_agent,
                    success=False,
                    error=str(exc)[:200],
                )
        
    
        self._message_log.append({
            "type": "response",
            **response.to_dict(),
        })
        
        log.info(
            "a2a_response_received",
            request_id=request.request_id,
            source=response.source_agent,
            target=response.target_agent,
            success=response.success,
        )
        
        return response
    
    def get_message_log(self) -> list[dict[str, Any]]:
        """Get the A2A message log for debugging/auditing."""
        return self._message_log.copy()
    
    def clear_message_log(self) -> None:
        """Clear the message log."""
        self._message_log.clear()


# ── Singleton Hub Instance ─────────────────────────────────────────────────────

_hub: A2ACommunicationHub | None = None


def get_a2a_hub() -> A2ACommunicationHub:
    """Get or create the singleton A2A hub."""
    global _hub
    if _hub is None:
        _hub = A2ACommunicationHub()
        _register_default_handlers(_hub)
    return _hub


# ── Agent Handlers ─────────────────────────────────────────────────────────────

async def _trend_agent_handler(
    request: A2ARequest,
    state: MedInsightState,
) -> A2AResponse:
    """
    Handle A2A requests to the trend agent.
    
    Supported actions:
    - get_trends: Get trend data for specified tests
    - get_trend_summary: Get a text summary of trends
    """
    from app.agents.trend_agent import trend_node
    
    action = request.action
    payload = request.payload
    
    if action == "get_trends":
        # Run trend analysis
        state_copy = copy.deepcopy(state)
        
        # Override extracted_tests if specific tests requested
        if "test_names" in payload:
            state_copy["extracted_tests"] = [
                {"test_name": name} for name in payload["test_names"]
            ]
        
        result_state = await trend_node(state_copy)
        
        return A2AResponse(
            request_id=request.request_id,
            source_agent="trend_agent",
            target_agent=request.source_agent,
            success=True,
            data={
                "trend_results": result_state.get("trend_results", []),
                "trend_count": len(result_state.get("trend_results", [])),
            },
        )
    
    elif action == "get_trend_summary":
        
        trend_results = state.get("trend_results", [])
        
        if not trend_results:
         
            state_copy = copy.deepcopy(state)
            result_state = await trend_node(state_copy)
            trend_results = result_state.get("trend_results", [])
        
        summary_parts = []
        for trend in trend_results:
            test_name = trend.get("test_name", "Unknown")
            direction = trend.get("direction", "stable")
            change_pct = trend.get("change_percent", 0)
            velocity_concern = trend.get("velocity_concern", False)
            threshold_crossed = trend.get("threshold_crossed", False)
            
            summary = f"• {test_name}: {direction} ({change_pct:+.1f}%)"
            if velocity_concern:
                summary += " ⚠️ rapid change"
            if threshold_crossed:
                summary += " ⚠️ crossed threshold"
            summary_parts.append(summary)
        
        return A2AResponse(
            request_id=request.request_id,
            source_agent="trend_agent",
            target_agent=request.source_agent,
            success=True,
            data={
                "summary": "\n".join(summary_parts) if summary_parts else "No trend data available.",
                "trend_count": len(trend_results),
                "has_concerns": any(
                    t.get("velocity_concern") or t.get("threshold_crossed")
                    for t in trend_results
                ),
            },
        )
    
    else:
        return A2AResponse(
            request_id=request.request_id,
            source_agent="trend_agent",
            target_agent=request.source_agent,
            success=False,
            error=f"Unknown action: {action}",
        )


async def _rag_agent_handler(
    request: A2ARequest,
    state: MedInsightState,
) -> A2AResponse:
    """
    Handle A2A requests to the RAG agent.
    
    Supported actions:
    - get_guidelines: Get medical guidelines for specific conditions
    - search_knowledge_base: Search the knowledge base
    """
    from app.agents.rag_agent import rag_node
    
    action = request.action
    payload = request.payload
    
    if action == "get_guidelines":
        
        state_copy = copy.deepcopy(state)
        
        condition = payload.get("condition", state_copy.get("current_question", ""))
        state_copy["current_question"] = f"medical guidelines for {condition}"
        
        result_state = await rag_node(state_copy)
        
        return A2AResponse(
            request_id=request.request_id,
            source_agent="rag_agent",
            target_agent=request.source_agent,
            success=True,
            data={
                "rag_context": result_state.get("rag_context", ""),
                "rag_chunks": result_state.get("rag_chunks", []),
                "chunk_count": len(result_state.get("rag_chunks", [])),
            },
        )
    
    elif action == "search_knowledge_base":
        query = payload.get("query", "")
        if not query:
            return A2AResponse(
                request_id=request.request_id,
                source_agent="rag_agent",
                target_agent=request.source_agent,
                success=False,
                error="Query is required for search",
            )
        
        state_copy = copy.deepcopy(state)
        state_copy["current_question"] = query
        
        result_state = await rag_node(state_copy)
        
        return A2AResponse(
            request_id=request.request_id,
            source_agent="rag_agent",
            target_agent=request.source_agent,
            success=True,
            data={
                "results": result_state.get("rag_chunks", []),
                "context": result_state.get("rag_context", ""),
            },
        )
    
    else:
        return A2AResponse(
            request_id=request.request_id,
            source_agent="rag_agent",
            target_agent=request.source_agent,
            success=False,
            error=f"Unknown action: {action}",
        )


async def _sql_agent_handler(
    request: A2ARequest,
    state: MedInsightState,
) -> A2AResponse:
    """
    Handle A2A requests to the SQL agent.
    
    Supported actions:
    - query_data: Execute a natural language query against patient data
    - get_patient_stats: Get statistical summary of patient data
    """
    from app.agents.text_to_sql_agent import text_to_sql_node
    
    action = request.action
    payload = request.payload
    
    if action == "query_data":
        query = payload.get("query", "")
        if not query:
            return A2AResponse(
                request_id=request.request_id,
                source_agent="sql_agent",
                target_agent=request.source_agent,
                success=False,
                error="Query is required",
            )
        
        state_copy = copy.deepcopy(state)
        state_copy["current_question"] = query
        
        result_state = await text_to_sql_node(state_copy)
        
        return A2AResponse(
            request_id=request.request_id,
            source_agent="sql_agent",
            target_agent=request.source_agent,
            success=True,
            data={
                "sql_query": result_state.get("sql_query_generated"),
                "results": result_state.get("sql_results", []),
                "result_count": len(result_state.get("sql_results", [])),
            },
        )
    
    else:
        return A2AResponse(
            request_id=request.request_id,
            source_agent="sql_agent",
            target_agent=request.source_agent,
            success=False,
            error=f"Unknown action: {action}",
        )


def _register_default_handlers(hub: A2ACommunicationHub) -> None:
    """Register default agent handlers."""
    hub.register_agent("trend_agent", _trend_agent_handler)
    hub.register_agent("rag_agent", _rag_agent_handler)
    hub.register_agent("sql_agent", _sql_agent_handler)


# ── Convenience Functions for Agents ───────────────────────────────────────────

async def request_trend_data(
    source_agent: str,
    state: MedInsightState,
    test_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Convenience function for an agent to request trend data.
    
    Args:
        source_agent: Name of the requesting agent
        state: Current MedInsight state
        test_names: Optional list of specific test names to analyze
        
    Returns:
        Dict with trend_results and trend_count
    """
    hub = get_a2a_hub()
    
    request = A2ARequest(
        request_id=str(uuid.uuid4()),
        source_agent=source_agent,
        target_agent="trend_agent",
        action="get_trends",
        payload={"test_names": test_names} if test_names else {},
    )
    
    response = await hub.send_request(request, state)
    
    if response.success:
        return response.data or {}
    else:
        log.warning("a2a_trend_request_failed", error=response.error)
        return {"trend_results": [], "trend_count": 0}


async def request_trend_summary(
    source_agent: str,
    state: MedInsightState,
) -> dict[str, Any]:
    """
    Convenience function for an agent to request a trend summary.
    
    Returns:
        Dict with summary text and metadata
    """
    hub = get_a2a_hub()
    
    request = A2ARequest(
        request_id=str(uuid.uuid4()),
        source_agent=source_agent,
        target_agent="trend_agent",
        action="get_trend_summary",
        payload={},
    )
    
    response = await hub.send_request(request, state)
    
    if response.success:
        return response.data or {}
    else:
        log.warning("a2a_trend_summary_failed", error=response.error)
        return {"summary": "No trend data available.", "trend_count": 0}


async def request_guidelines(
    source_agent: str,
    state: MedInsightState,
    condition: str,
) -> dict[str, Any]:
    """
    Convenience function for an agent to request medical guidelines.
    
    Args:
        source_agent: Name of the requesting agent
        state: Current MedInsight state
        condition: Medical condition to get guidelines for
        
    Returns:
        Dict with rag_context and rag_chunks
    """
    hub = get_a2a_hub()
    
    request = A2ARequest(
        request_id=str(uuid.uuid4()),
        source_agent=source_agent,
        target_agent="rag_agent",
        action="get_guidelines",
        payload={"condition": condition},
    )
    
    response = await hub.send_request(request, state)
    
    if response.success:
        return response.data or {}
    else:
        log.warning("a2a_guidelines_request_failed", error=response.error)
        return {"rag_context": "", "rag_chunks": []}

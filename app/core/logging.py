"""
Enhanced Structured Logging for MedInsight.

This module provides enterprise-grade logging with:
- Request tracing with correlation IDs
- Performance metrics and timing
- Automatic context enrichment
- Log level filtering by environment
- Structured JSON output for production
- Pretty console output for development
- Sensitive data masking
- Error tracking with stack traces

Usage:
    from app.core.logging import get_logger, log_performance, mask_sensitive
    
    log = get_logger(__name__)
    
    with log_performance(log, "database_query"):
        results = await db.execute(query)
    
    log.info("user_authenticated", user_id=mask_sensitive(user_id))
"""
from __future__ import annotations

import functools
import logging
import sys
import time
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from collections.abc import MutableMapping
from typing import Any, Callable, Generator, TypeVar

import structlog
from structlog.types import Processor

from app.core.config import settings

# Type variable for generic function decoration
F = TypeVar("F", bound=Callable[..., Any])


# ══════════════════════════════════════════════════════════════════════════════
# SENSITIVE DATA MASKING
# ══════════════════════════════════════════════════════════════════════════════

_SENSITIVE_KEYS = frozenset({
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "authorization", "auth", "credentials", "credit_card", "ssn",
    "social_security", "private_key", "access_token", "refresh_token",
})


def mask_sensitive(value: str, visible_chars: int = 4) -> str:
    """
    Mask sensitive data, showing only last N characters.
    
    Examples:
        mask_sensitive("sk-1234567890abcdef") -> "****cdef"
        mask_sensitive("short") -> "****"
    """
    if not value or len(value) <= visible_chars:
        return "****"
    return f"****{value[-visible_chars:]}"


def _mask_sensitive_processor(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Processor that automatically masks sensitive fields."""
    for key in list(event_dict.keys()):
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in _SENSITIVE_KEYS):
            value = event_dict[key]
            if isinstance(value, str):
                event_dict[key] = mask_sensitive(value)
    return event_dict


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOM PROCESSORS
# ══════════════════════════════════════════════════════════════════════════════

def _add_service_context(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Add service-level context to every log entry."""
    event_dict.setdefault("service", settings.app_name or "medinsight")
    event_dict.setdefault("environment", "dev" if settings.app_debug else "prod")
    return event_dict


def _safe_add_logger_name(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Add logger name safely (works for both stdlib and structlog loggers)."""
    try:
        name = logger.name
    except AttributeError:
        name = event_dict.get("logger", "")
    if name:
        event_dict.setdefault("logger", name)
    return event_dict


def _format_exception_enhanced(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Format exceptions with full traceback for error logs."""
    exc_info = event_dict.pop("exc_info", None)
    if exc_info:
        if isinstance(exc_info, BaseException):
            event_dict["exception"] = {
                "type": type(exc_info).__name__,
                "message": str(exc_info)[:500],
            }
        elif exc_info is True:
            exc_type, exc_value, exc_tb = sys.exc_info()
            if exc_value:
                event_dict["exception"] = {
                    "type": exc_type.__name__ if exc_type else "Unknown",
                    "message": str(exc_value)[:500],
                }
    return event_dict


# ══════════════════════════════════════════════════════════════════════════════
# LOG LEVEL STYLES (for console)
# ══════════════════════════════════════════════════════════════════════════════

def _supports_unicode() -> bool:
    """Check if the terminal supports Unicode output."""
    import sys
    import os
    # Check Windows environment
    if sys.platform == "win32":
        # Check for Windows Terminal or modern console
        return os.environ.get("WT_SESSION") is not None or os.environ.get("TERM_PROGRAM") == "vscode"
    # Unix-like systems generally support unicode
    return True


# Use ASCII fallback for Windows cmd.exe
_USE_EMOJI = _supports_unicode()

_LEVEL_STYLES = {
    "debug": ("D" if not _USE_EMOJI else "~", "\033[36m"),     # Cyan
    "info": ("+" if not _USE_EMOJI else "*", "\033[32m"),      # Green  
    "warning": ("!" if not _USE_EMOJI else "!", "\033[33m"),   # Yellow
    "error": ("X" if not _USE_EMOJI else "X", "\033[31m"),     # Red
    "critical": ("!!" if not _USE_EMOJI else "!!", "\033[35m"),# Magenta
}


class EnhancedConsoleRenderer:
    """
    Custom console renderer with indicators and colored output.
    
    Format: [TIME] INDICATOR LEVEL | event | key=value key=value
    
    Works on both Windows (ASCII) and Unix (UTF-8) terminals.
    """
    
    def __init__(self, colors: bool = True):
        self.colors = colors
        self.reset = "\033[0m" if colors else ""
        self.dim = "\033[2m" if colors else ""
        self.bold = "\033[1m" if colors else ""
    
    def __call__(
        self, logger: Any, method_name: str, event_dict: dict[str, Any]
    ) -> str:
        # Extract core fields
        timestamp = event_dict.pop("timestamp", "")
        level = event_dict.pop("level", "info").lower()
        event = event_dict.pop("event", "")
        logger_name = event_dict.pop("logger", "")
        
        # Remove internal fields
        event_dict.pop("service", None)
        event_dict.pop("environment", None)
        
        # Get style for level
        emoji, color = _LEVEL_STYLES.get(level, ("•", ""))
        if not self.colors:
            color = ""
        
        # Format time (just HH:MM:SS.mmm)
        time_str = timestamp[11:23] if len(timestamp) >= 23 else timestamp[:12]
        
        # Build key-value pairs
        kv_parts = []
        for key, value in sorted(event_dict.items()):
            if value is None:
                continue
            if isinstance(value, str) and len(value) > 100:
                value = value[:97] + "..."
            kv_parts.append(f"{self.dim}{key}={self.reset}{value}")
        
        kv_str = " ".join(kv_parts)
        
        # Format logger name (short form)
        short_logger = logger_name.split(".")[-1] if logger_name else ""
        
        # Build final line
        parts = [
            f"{self.dim}[{time_str}]{self.reset}",
            f"{emoji}",
            f"{color}{self.bold}{level.upper():8}{self.reset}",
            f"{self.dim}│{self.reset}",
            f"{self.bold}{event}{self.reset}",
        ]
        
        if short_logger:
            parts.append(f"{self.dim}({short_logger}){self.reset}")
        
        if kv_str:
            parts.append(f"{self.dim}│{self.reset} {kv_str}")
        
        return " ".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
# SHARED PROCESSOR CHAIN
# ══════════════════════════════════════════════════════════════════════════════

_SHARED_PROCESSORS: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    _safe_add_logger_name,
    _add_service_context,
    _mask_sensitive_processor,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    _format_exception_enhanced,
]


def _get_renderer() -> Any:
    """Return appropriate renderer based on environment."""
    if settings.app_debug:
        return EnhancedConsoleRenderer(colors=True)
    return structlog.processors.JSONRenderer(sort_keys=True)


def configure_logging() -> None:
    """
    Configure structlog AND bridge Python stdlib logging through it.

    After this call every logger – whether created via
    ``structlog.get_logger()`` or ``logging.getLogger()`` – emits a
    consistently structured line:

      dev  → ConsoleRenderer  (colour, human-readable)
      prod → JSONRenderer     (machine-readable)

    The bridge means uvicorn's access/error logs, SQLAlchemy, groq, httpx
    and all third-party libraries all appear in the same format with the
    same timestamp, so you get ONE coherent log stream instead of two.
    """
    renderer = _get_renderer()

    # ── 1. structlog-native configuration ────────────────────────────────────
    # PrintLoggerFactory writes directly via print() — no stdlib round-trip.
    # This avoids double-processing when the stdlib bridge (step 2) is also set.
    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        # Disable caching so re-configuration (after uvicorn overrides) works
        cache_logger_on_first_use=False,
    )

    # ── 2. stdlib → structlog bridge ─────────────────────────────────────────
    # ProcessorFormatter feeds every stdlib LogRecord through the same
    # processor chain so output format is identical regardless of origin.
    formatter = structlog.stdlib.ProcessorFormatter(
        # Final processors run AFTER foreign_pre_chain on every record
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        # Run before renderer – adds level, name, timestamp, etc.
        foreign_pre_chain=_SHARED_PROCESSORS,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Replace ALL existing root handlers with ours
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)

    # ── 3. Per-library levels ─────────────────────────────────────────────────
    # Keep uvicorn's own logs but silence chatty third-party libraries.
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("groq").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("llama_index").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("multipart").setLevel(logging.WARNING)


# ── Run at import time ────────────────────────────────────────────────────────
configure_logging()


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Return a structlog bound logger scoped to the given module name.

    Usage::

        from app.core.logging import get_logger
        log = get_logger(__name__)
        log.info("something_happened", key="value", count=42)
    """
    return structlog.get_logger(name).bind(logger=name)


# ══════════════════════════════════════════════════════════════════════════════
# CONTEXT MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

def bind_context(**kwargs: Any) -> None:
    """
    Bind context variables that will be included in all subsequent logs.
    
    Useful for request-scoped context like request_id, user_id, etc.
    
    Usage:
        bind_context(request_id="abc-123", user_id="user-456")
        log.info("processing")  # Will include request_id and user_id
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()


def unbind_context(*keys: str) -> None:
    """Remove specific keys from the bound context."""
    structlog.contextvars.unbind_contextvars(*keys)


@contextmanager
def log_context(**kwargs: Any) -> Generator[None, None, None]:
    """
    Context manager for temporary log context.
    
    Usage:
        with log_context(operation="bulk_import", batch_size=100):
            log.info("starting_import")
            # ... do work ...
            log.info("import_complete")
    """
    bind_context(**kwargs)
    try:
        yield
    finally:
        unbind_context(*kwargs.keys())


# ══════════════════════════════════════════════════════════════════════════════
# PERFORMANCE LOGGING
# ══════════════════════════════════════════════════════════════════════════════

@contextmanager
def log_performance(
    logger: structlog.stdlib.BoundLogger,
    operation: str,
    warn_threshold_ms: float = 1000,
    error_threshold_ms: float = 5000,
    **extra_context: Any,
) -> Generator[dict[str, Any], None, None]:
    """
    Context manager for logging operation performance.
    
    Automatically logs start, completion, duration, and warns on slow operations.
    
    Usage:
        with log_performance(log, "database_query", table="users") as ctx:
            results = await db.execute(query)
            ctx["row_count"] = len(results)
        
        # Logs:
        # - operation_started: database_query table=users
        # - operation_completed: database_query duration_ms=45 row_count=100
    """
    context: dict[str, Any] = {"operation": operation, **extra_context}
    
    logger.debug(f"{operation}_started", **extra_context)
    start_time = time.perf_counter()
    
    try:
        yield context
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        context["duration_ms"] = round(duration_ms, 2)
        
        # Choose log level based on duration
        if duration_ms >= error_threshold_ms:
            logger.error(
                f"{operation}_slow",
                **context,
                threshold_exceeded="error",
            )
        elif duration_ms >= warn_threshold_ms:
            logger.warning(
                f"{operation}_slow",
                **context,
                threshold_exceeded="warning",
            )
        else:
            logger.info(f"{operation}_completed", **context)
            
    except Exception as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.error(
            f"{operation}_failed",
            duration_ms=round(duration_ms, 2),
            error_type=type(exc).__name__,
            error_message=str(exc)[:200],
            exc_info=True,
            **extra_context,
        )
        raise


def log_async_performance(
    operation: str,
    warn_threshold_ms: float = 1000,
    error_threshold_ms: float = 5000,
) -> Callable[[F], F]:
    """
    Decorator for async functions to log performance.
    
    Usage:
        @log_async_performance("fetch_user_data")
        async def get_user(user_id: str) -> User:
            ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger = get_logger(func.__module__)
            with log_performance(
                logger,
                operation,
                warn_threshold_ms=warn_threshold_ms,
                error_threshold_ms=error_threshold_ms,
                function=func.__name__,
            ):
                return await func(*args, **kwargs)
        return wrapper  # type: ignore
    return decorator


# ══════════════════════════════════════════════════════════════════════════════
# REQUEST TRACING
# ══════════════════════════════════════════════════════════════════════════════

def generate_request_id() -> str:
    """Generate a unique request ID for tracing."""
    return str(uuid.uuid4())[:8]


def generate_correlation_id() -> str:
    """Generate a correlation ID for distributed tracing."""
    return str(uuid.uuid4())


class RequestLogger:
    """
    Helper class for structured request logging.
    
    Usage:
        req_log = RequestLogger(request_id="abc123", endpoint="/api/v1/chat")
        req_log.start()
        req_log.log_step("validation_complete", valid=True)
        req_log.log_step("processing", items=42)
        req_log.complete(status_code=200)
    """
    
    def __init__(
        self,
        request_id: str,
        endpoint: str,
        method: str = "GET",
        **context: Any,
    ):
        self.request_id = request_id
        self.endpoint = endpoint
        self.method = method
        self.context = context
        self.start_time: float | None = None
        self.log = get_logger("request")
        self._step_count = 0
    
    def start(self, **extra: Any) -> None:
        """Log request start."""
        self.start_time = time.perf_counter()
        bind_context(
            request_id=self.request_id,
            endpoint=self.endpoint,
            method=self.method,
        )
        self.log.info(
            "request_started",
            **self.context,
            **extra,
        )
    
    def log_step(self, step: str, **data: Any) -> None:
        """Log an intermediate step in request processing."""
        self._step_count += 1
        elapsed = self._elapsed_ms()
        self.log.debug(
            f"request_step_{step}",
            step_number=self._step_count,
            elapsed_ms=elapsed,
            **data,
        )
    
    def complete(
        self,
        status_code: int = 200,
        **extra: Any,
    ) -> None:
        """Log request completion."""
        duration = self._elapsed_ms()
        level = "info" if status_code < 400 else "warning" if status_code < 500 else "error"
        
        getattr(self.log, level)(
            "request_completed",
            status_code=status_code,
            duration_ms=duration,
            steps=self._step_count,
            **extra,
        )
        clear_context()
    
    def error(self, error: Exception, status_code: int = 500) -> None:
        """Log request error."""
        duration = self._elapsed_ms()
        self.log.error(
            "request_failed",
            status_code=status_code,
            duration_ms=duration,
            steps=self._step_count,
            error_type=type(error).__name__,
            error_message=str(error)[:200],
            exc_info=True,
        )
        clear_context()
    
    def _elapsed_ms(self) -> float:
        if self.start_time is None:
            return 0.0
        return round((time.perf_counter() - self.start_time) * 1000, 2)


# ══════════════════════════════════════════════════════════════════════════════
# AUDIT LOGGING
# ══════════════════════════════════════════════════════════════════════════════

_audit_log = get_logger("audit")


def audit_log(
    action: str,
    actor_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    status: str = "success",
    **details: Any,
) -> None:
    """
    Log an audit event for compliance and security tracking.
    
    Usage:
        audit_log(
            action="patient_data_accessed",
            actor_id="user-123",
            resource_type="patient",
            resource_id="patient-456",
            status="success",
            fields_accessed=["name", "lab_results"],
        )
    """
    _audit_log.info(
        f"audit_{action}",
        audit=True,
        action=action,
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        **details,
    )


# ══════════════════════════════════════════════════════════════════════════════
# METRICS LOGGING
# ══════════════════════════════════════════════════════════════════════════════

_metrics_log = get_logger("metrics")


def log_metric(
    metric_name: str,
    value: float | int,
    unit: str = "",
    tags: dict[str, str] | None = None,
    **extra: Any,
) -> None:
    """
    Log a metric for monitoring and alerting.
    
    Usage:
        log_metric("response_time", 145.2, unit="ms", endpoint="/api/v1/chat")
        log_metric("cache_hit_rate", 0.85, tags={"cache": "redis"})
    """
    _metrics_log.info(
        f"metric_{metric_name}",
        metric=True,
        metric_name=metric_name,
        value=value,
        unit=unit,
        tags=tags or {},
        **extra,
    )


# ══════════════════════════════════════════════════════════════════════════════
# AGENT LOGGING HELPERS
# ══════════════════════════════════════════════════════════════════════════════

class AgentLogger:
    """
    Specialized logger for AI agent operations.
    
    Usage:
        agent_log = AgentLogger("report_agent", patient_id="123")
        agent_log.start("generating_report")
        agent_log.llm_call("groq", "llama-3.3-70b", tokens=500)
        agent_log.complete(confidence="high")
    """
    
    def __init__(self, agent_name: str, **context: Any):
        self.agent_name = agent_name
        self.context = context
        self.log = get_logger(f"agent.{agent_name}")
        self.start_time: float | None = None
        self._llm_calls = 0
        self._llm_tokens = 0
    
    def start(self, task: str, **extra: Any) -> None:
        """Log agent task start."""
        self.start_time = time.perf_counter()
        self.log.info(
            f"agent_{self.agent_name}_started",
            agent=self.agent_name,
            task=task,
            **self.context,
            **extra,
        )
    
    def llm_call(
        self,
        provider: str,
        model: str,
        tokens: int = 0,
        duration_ms: float = 0,
        **extra: Any,
    ) -> None:
        """Log an LLM call made by the agent."""
        self._llm_calls += 1
        self._llm_tokens += tokens
        self.log.debug(
            "agent_llm_call",
            agent=self.agent_name,
            provider=provider,
            model=model,
            tokens=tokens,
            duration_ms=duration_ms,
            call_number=self._llm_calls,
            **extra,
        )
    
    def a2a_request(
        self,
        target_agent: str,
        action: str,
        **extra: Any,
    ) -> None:
        """Log an agent-to-agent request."""
        self.log.info(
            "agent_a2a_request",
            source_agent=self.agent_name,
            target_agent=target_agent,
            action=action,
            **extra,
        )
    
    def a2a_response(
        self,
        source_agent: str,
        success: bool,
        duration_ms: float = 0,
        **extra: Any,
    ) -> None:
        """Log an agent-to-agent response received."""
        self.log.info(
            "agent_a2a_response",
            agent=self.agent_name,
            source_agent=source_agent,
            success=success,
            duration_ms=duration_ms,
            **extra,
        )
    
    def complete(
        self,
        status: str = "success",
        **extra: Any,
    ) -> None:
        """Log agent task completion."""
        duration = 0.0
        if self.start_time:
            duration = round((time.perf_counter() - self.start_time) * 1000, 2)
        
        self.log.info(
            f"agent_{self.agent_name}_completed",
            agent=self.agent_name,
            status=status,
            duration_ms=duration,
            llm_calls=self._llm_calls,
            total_tokens=self._llm_tokens,
            **self.context,
            **extra,
        )
    
    def error(self, error: Exception, **extra: Any) -> None:
        """Log agent error."""
        duration = 0.0
        if self.start_time:
            duration = round((time.perf_counter() - self.start_time) * 1000, 2)
        
        self.log.error(
            f"agent_{self.agent_name}_error",
            agent=self.agent_name,
            duration_ms=duration,
            error_type=type(error).__name__,
            error_message=str(error)[:200],
            llm_calls=self._llm_calls,
            exc_info=True,
            **self.context,
            **extra,
        )


# ══════════════════════════════════════════════════════════════════════════════
# EXPORTS
# ══════════════════════════════════════════════════════════════════════════════

__all__ = [
    # Core
    "get_logger",
    "configure_logging",
    
    # Context management
    "bind_context",
    "clear_context",
    "unbind_context",
    "log_context",
    
    # Performance
    "log_performance",
    "log_async_performance",
    
    # Request tracing
    "generate_request_id",
    "generate_correlation_id",
    "RequestLogger",
    
    # Security
    "mask_sensitive",
    
    # Audit & Metrics
    "audit_log",
    "log_metric",
    
    # Agent logging
    "AgentLogger",
]

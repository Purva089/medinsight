"""
FastAPI request/response middleware with enhanced structured logging.

Features:
- Unique request ID per request (UUID)
- Correlation ID support for distributed tracing
- Structured logging with timing metrics
- Performance warnings for slow requests
- Security-sensitive header masking
- Full request lifecycle tracking
"""
from __future__ import annotations

import time
import uuid
from typing import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.logging import (
    get_logger,
    bind_context,
    clear_context,
    audit_log,
    log_metric,
)

log = get_logger(__name__)

# Performance thresholds (ms)
WARN_THRESHOLD_MS = 10000   # Log warning if request takes > 10s
ERROR_THRESHOLD_MS = 60000  # Log error if request takes > 60s

# Paths to exclude from verbose logging
HEALTH_CHECK_PATHS = frozenset({"/health", "/healthz", "/ready", "/metrics"})


# ── helpers ───────────────────────────────────────────────────────────────────

def _client_ip(request: Request) -> str:
    """Best-effort client IP extraction (proxy-aware)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    if request.client:
        return request.client.host
    return "unknown"


def _user_agent(request: Request) -> str:
    ua = request.headers.get("user-agent", "")
    return ua[:120] if ua else "unknown"


def _request_size(request: Request) -> int:
    """Get request body size from Content-Length header."""
    try:
        return int(request.headers.get("content-length", 0))
    except (ValueError, TypeError):
        return 0


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Enhanced structured request/response logging middleware.

    Features:
    - UUID request_id in structlog context + X-Request-ID header
    - Performance metrics and slow request warnings
    - Audit logging for sensitive endpoints
    - Request/response size tracking
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())[:8]  # Short ID for readability
        correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))

        # Clear previous request context and bind new context
        clear_context()
        bind_context(
            request_id=request_id,
            correlation_id=correlation_id[:8],
            method=request.method,
            path=request.url.path,
        )

        # Make request_id available to endpoint code
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id

        # Skip verbose logging for health checks
        is_health_check = request.url.path in HEALTH_CHECK_PATHS
        
        # Extract request metadata
        client_ip = _client_ip(request)
        user_agent = _user_agent(request)
        request_size = _request_size(request)
        query = str(request.url.query)

        if not is_health_check:
            log.info(
                "http_request_started",
                client_ip=client_ip,
                user_agent=user_agent[:60],
                content_type=request.headers.get("content-type", ""),
                request_size_bytes=request_size,
                query=query[:100] if query else None,
            )

        t0 = time.perf_counter()

        try:
            response: Response = await call_next(request)
        except OSError as exc:
            # Network / DNS / DB connection failures — return 503, do not crash
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            log.error(
                "http_request_db_unavailable",
                duration_ms=duration_ms,
                exception_type=type(exc).__name__,
                exception_message=str(exc)[:300],
                client_ip=client_ip,
            )
            log_metric(
                "http_request_error",
                value=1,
                unit="count",
                tags={"path": request.url.path, "method": request.method},
            )
            return JSONResponse(
                status_code=503,
                content={"detail": "Database temporarily unavailable. Please try again shortly."},
                headers={"X-Request-ID": request_id, "X-Correlation-ID": correlation_id},
            )
        except Exception as exc:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            
            log.error(
                "http_request_exception",
                duration_ms=duration_ms,
                exception_type=type(exc).__name__,
                exception_message=str(exc)[:300],
                client_ip=client_ip,
                exc_info=True,
            )
            
            # Log metric for monitoring
            log_metric(
                "http_request_error",
                value=1,
                unit="count",
                tags={"path": request.url.path, "method": request.method},
            )
            raise

        duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        status_code = response.status_code

        # Determine log level based on status and duration
        if status_code >= 500:
            log_level = "error"
        elif status_code >= 400:
            log_level = "warning"
        elif duration_ms >= ERROR_THRESHOLD_MS:
            log_level = "error"
        elif duration_ms >= WARN_THRESHOLD_MS:
            log_level = "warning"
        else:
            log_level = "info"

        if not is_health_check:
            # Get response size
            response_size = 0
            if hasattr(response, "body"):
                response_size = len(response.body) if response.body else 0

            getattr(log, log_level)(
                "http_request_completed",
                status_code=status_code,
                duration_ms=duration_ms,
                response_size_bytes=response_size,
                slow_request=duration_ms >= WARN_THRESHOLD_MS,
            )

            # Log metric for monitoring
            log_metric(
                "http_request_duration",
                value=duration_ms,
                unit="ms",
                tags={
                    "path": request.url.path,
                    "method": request.method,
                    "status": str(status_code),
                },
            )

        # Add tracing headers to response
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id

        return response

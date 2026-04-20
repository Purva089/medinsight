"""
MedInsight FastAPI application entrypoint.

Run with:
    uvicorn app.api.main:app --reload
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.api.middleware import RequestLoggingMiddleware
from app.api.routers import auth, chat, history, reports, patients
from app.api.routers import mcp, tools  # MCP and Function Calling routers
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

log = get_logger(__name__)

# ── SlowAPI rate limiter ──────────────────────────────────────────────────────

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_requests_per_minute}/minute"],
)

# ── Lifespan event handler ────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown."""
    # Startup
    configure_logging()
    
    # Override uvicorn's propagation so its records flow through our handler
    for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_log = logging.getLogger(uvicorn_logger_name)
        uv_log.handlers.clear()
        uv_log.propagate = True
    
    log.info(
        "app_started",
        app_name=settings.app_name,
        version=settings.app_version,
        debug=settings.app_debug,
        cors_origins=settings.cors_origins,
    )
    log.info(
        "logging_configured",
        renderer="ConsoleRenderer" if settings.app_debug else "JSONRenderer",
        stdlib_bridge=True,
    )
    
    # Note: Embedding model loads lazily on first RAG request (~10s)
    # This avoids blocking startup while still caching after first use
    
    yield
    
    # Shutdown
    log.info("app_shutdown")

# ── FastAPI application ───────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name or "MedInsight API",
    version=settings.app_version or "0.1.0",
    description="AI-powered medical lab report analysis platform.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Rate limiter state & handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# CORS origins configured in app/core/config.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SlowAPI enforcement middleware
app.add_middleware(SlowAPIMiddleware)

# Request logging (UUID per request, structlog context, X-Request-ID header)
app.add_middleware(RequestLoggingMiddleware)


# ── Routers ───────────────────────────────────────────────────────────────────

_PREFIX = "/api/v1"

app.include_router(auth.router, prefix=_PREFIX)
app.include_router(reports.router, prefix=_PREFIX)
app.include_router(chat.router, prefix=_PREFIX)
app.include_router(history.router, prefix=_PREFIX)
app.include_router(patients.router, prefix=_PREFIX)
app.include_router(mcp.router, prefix=_PREFIX)    # MCP Server endpoints
app.include_router(tools.router, prefix=_PREFIX)  # Function/Tool Calling endpoints


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "version": settings.app_version or "0.1.0"}

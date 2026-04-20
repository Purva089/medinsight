"""
LLM service — wraps Groq with retry/timeout/fallback.

All model names, temperatures, and token limits are read from settings.
Nothing is hardcoded here.

Features:
- Automatic fallback model switching on rate limits
- Comprehensive performance logging with metrics
- Token usage tracking
- Retry with 1-second wait between attempts (fast recovery)
"""
from __future__ import annotations

import time

from pydantic import SecretStr

from app.core.config import settings
from app.core.logging import get_logger, log_metric

log = get_logger(__name__)

# ── token limit lookup ────────────────────────────────────────────────────────

_MAX_TOKENS: dict[str, int] = {
    "classification": settings.max_tokens_classification,
    "extraction":     settings.max_tokens_extraction,
    "self_heal":      settings.max_tokens_self_heal,
    "text_to_sql":    settings.max_tokens_text_to_sql,
    "ltm_summary":    settings.max_tokens_ltm_summary,
    "report":         settings.max_tokens_report,
}


def _get_max_tokens(key: str) -> int:
    return _MAX_TOKENS.get(key, 512)


# ── LLM Service ───────────────────────────────────────────────────────────────

class LLMService:
    """
    Central service for all LLM calls.

    call_reasoning → Groq (llama-3.3-70b-versatile or whatever is in settings)
    """

    # ── reasoning (Groq) ─────────────────────────────────────────────────────

    async def call_reasoning(self, prompt: str, max_tokens_key: str) -> str:
        """
        Call the Groq reasoning model with retry and 30-second timeout.

        Raises RuntimeError after all retries exhausted.
        """
        max_tokens = _get_max_tokens(max_tokens_key)
        model = settings.reasoning_model

        log.info(
            "llm_call_started",
            model=model,
            max_tokens_key=max_tokens_key,
            max_tokens=max_tokens,
            prompt_len=len(prompt),
            prompt_preview=prompt[:120].replace("\n", " "),
        )
        t0 = time.monotonic()

        try:
            result = await self._groq_with_retry(prompt, model, max_tokens)
        except Exception as exc:
            duration_ms = round((time.monotonic() - t0) * 1000)
            log.error(
                "llm_all_retries_failed",
                model=model,
                max_tokens_key=max_tokens_key,
                duration_ms=duration_ms,
                error=str(exc)[:200],
                exc_info=True,
            )
            # Log failure metric
            log_metric(
                "llm_call_failure",
                value=1,
                unit="count",
                tags={"model": model, "key": max_tokens_key, "provider": "groq"},
            )
            raise RuntimeError(f"Groq call failed after retries: {exc}") from exc

        duration_ms = round((time.monotonic() - t0) * 1000)
        
        # Log success metrics
        log_metric(
            "llm_call_duration",
            value=duration_ms,
            unit="ms",
            tags={"model": model, "key": max_tokens_key, "provider": "groq"},
        )
        log_metric(
            "llm_tokens_processed",
            value=len(result) // 4,  # Rough token estimate
            unit="tokens",
            tags={"model": model, "direction": "output"},
        )
        
        log.info(
            "llm_call_complete",
            model=model,
            max_tokens_key=max_tokens_key,
            duration_ms=duration_ms,
            result_len=len(result),
            tokens_per_sec=round((len(result) / 4) / (duration_ms / 1000), 1) if duration_ms > 0 else 0,
            result_preview=result[:120].replace("\n", " "),
        )
        return result

    async def _groq_with_retry(self, prompt: str, model: str, max_tokens: int) -> str:
        """
        Call Groq with retry logic and automatic fallback model switching.
        
        Retry strategy:
        - 4 attempts total (2 with main model, 2 with fallback)
        - 1 second wait between retries
        - Immediate switch to fallback on rate limit (429 errors)
        
        Args:
            prompt: The input prompt
            model: The Groq model to use (e.g., llama-3.3-70b-versatile)
            max_tokens: Maximum tokens in response
            
        Returns:
            The LLM response text
            
        Raises:
            RuntimeError: If all retries are exhausted
        """
        import asyncio
        from langchain_groq import ChatGroq  # type: ignore[import]
        from langchain_core.messages import HumanMessage  # type: ignore[import]

        last_exc: Exception | None = None
        current_model = model
        
        for attempt in range(1, 5):  # 4 attempts: 2 with main model, 2 with fallback
            try:
                llm = ChatGroq(
                    model=current_model,
                    api_key=SecretStr(settings.groq_api_key),
                    temperature=settings.llm_temperature,
                    max_tokens=max_tokens,
                    timeout=30,
                )
                response = await asyncio.wait_for(
                    llm.ainvoke([HumanMessage(content=prompt)]),
                    timeout=35,
                )
                return response.content  # type: ignore[return-value]
            except Exception as exc:
                last_exc = exc
                error_str = str(exc).lower()
                is_rate_limit = "429" in str(exc) or "rate limit" in error_str
                
                # If rate limited on main model, switch to fallback
                if is_rate_limit and current_model == model and settings.fallback_reasoning_model:
                    current_model = settings.fallback_reasoning_model
                    log.warning(
                        "llm_switching_to_fallback",
                        provider="groq",
                        from_model=model,
                        to_model=current_model,
                        reason="rate_limit",
                    )
                    continue  # Try immediately with fallback model
                
                wait = 1  # Flat 1s between retries for fast recovery
                log.warning(
                    "llm_retry_attempt",
                    provider="groq",
                    model=current_model,
                    attempt=attempt,
                    remaining=4 - attempt,
                    error_type=type(exc).__name__,
                    error=str(exc)[:150],
                    wait_seconds=wait,
                )
                if attempt < 4:
                    await asyncio.sleep(wait)
        
        raise RuntimeError(f"Groq exhausted retries: {last_exc}") from last_exc


    async def call_fast(self, prompt: str, max_tokens: int = 10) -> str:
        """
        Ultra-fast LLM call for simple tasks like classification.
        Uses the fallback (smaller/faster) model with minimal tokens.
        """
        import asyncio
        from langchain_groq import ChatGroq
        from langchain_core.messages import HumanMessage

        model = settings.fallback_reasoning_model or settings.reasoning_model
        log.info("llm_fast_call", model=model, prompt_len=len(prompt))
        t0 = time.monotonic()

        try:
            llm = ChatGroq(
                model=model,
                api_key=SecretStr(settings.groq_api_key),
                temperature=0.0,  # Deterministic for classification
                max_tokens=max_tokens,
                timeout=10,  # 10 second timeout
            )
            response = await asyncio.wait_for(
                llm.ainvoke([HumanMessage(content=prompt)]),
                timeout=12,
            )
            content = response.content
            result = content.strip() if isinstance(content, str) else str(content)
            duration_ms = round((time.monotonic() - t0) * 1000)
            log.info("llm_fast_complete", model=model, duration_ms=duration_ms, result=result[:50])
            return result
        except Exception as exc:
            log.error("llm_fast_error", error=str(exc)[:100])
            raise RuntimeError(f"Fast LLM call failed: {exc}") from exc


# Module-level singleton — import and use this instead of LLMService()
llm_service = LLMService()

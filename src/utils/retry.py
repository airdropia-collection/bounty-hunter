"""
Retry decorators built on ``tenacity``.

Wrap any network-call function with ``@retry_network()`` for exponential
backoff on transient failures.
"""
from __future__ import annotations

from typing import Callable

try:
    from tenacity import (
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential_jitter,
    )
except ImportError:  # pragma: no cover
    retry = None  # type: ignore
    retry_if_exception_type = None  # type: ignore
    stop_after_attempt = None  # type: ignore
    wait_exponential_jitter = None  # type: ignore

from src.utils.logger import get_logger

log = get_logger("retry")


def retry_network(max_attempts: int = 3, base_delay: float = 1.0, max_delay: float = 8.0):
    """Decorator: retry on Exception with exponential backoff + jitter.

    Use on:
        - HTTP calls (httpx, requests)
        - AI API calls (Gemini, Groq)
        - GitHub API calls
        - Web3 RPC calls
    """
    if retry is None:
        def _identity(fn: Callable) -> Callable:
            return fn
        return _identity

    def _before_sleep(rs):
        exc = rs.outcome.exception() if rs.outcome.failed else None
        log.warning(
            "%s: attempt %d failed, retrying in %.1fs (%s)",
            rs.fn.__name__ if rs.fn else "?",
            rs.attempt_number,
            rs.next_action.sleep if hasattr(rs.next_action, "sleep") else 0.0,
            exc,
        )

    return retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(initial=base_delay, max=max_delay),
        before_sleep=_before_sleep,
        reraise=True,
    )

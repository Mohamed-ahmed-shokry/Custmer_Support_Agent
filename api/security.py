"""Opt-in API security: API-key auth, rate limiting, token quotas (no extra deps)."""

from __future__ import annotations

import datetime
import threading
import time
from collections import deque

_lock = threading.Lock()
_hits: dict[str, deque[float]] = {}
_token_usage: dict[tuple[str, str], int] = {}

WINDOW_SECONDS = 60.0

# Paths that stay public (probes, metrics, API docs).
PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/health/live",
        "/health/ready",
        "/metrics",
        "/metrics.json",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)


def reset() -> None:
    """Clear all rate-limit and quota state (used by tests)."""
    with _lock:
        _hits.clear()
        _token_usage.clear()


def is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS


def check_api_key(provided_key: str | None, configured_key: str) -> bool:
    """Return True when the request is authorized.

    Auth is disabled when no key is configured (empty string).
    """
    if not configured_key:
        return True
    return provided_key == configured_key


def check_rate_limit(key: str, limit_per_min: int, now: float | None = None) -> bool:
    """Return True when the request is within the sliding-window limit.

    A non-positive limit disables rate limiting.
    """
    if limit_per_min <= 0:
        return True
    current = time.monotonic() if now is None else now
    cutoff = current - WINDOW_SECONDS
    with _lock:
        hits = _hits.setdefault(key, deque())
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= limit_per_min:
            return False
        hits.append(current)
        return True


def _today() -> str:
    return datetime.date.today().isoformat()


def check_token_quota(
    key: str, additional_tokens: int, daily_budget: int, today: str | None = None
) -> bool:
    """Return True when `additional_tokens` fits the client's daily budget.

    A non-positive budget disables quota enforcement.
    """
    if daily_budget <= 0:
        return True
    day = today if today is not None else _today()
    with _lock:
        return _token_usage.get((key, day), 0) + additional_tokens <= daily_budget


def record_token_usage(key: str, tokens: int, today: str | None = None) -> int:
    """Add `tokens` to the client's daily usage, returning the new total."""
    day = today if today is not None else _today()
    with _lock:
        total = _token_usage.get((key, day), 0) + tokens
        _token_usage[(key, day)] = total
        return total

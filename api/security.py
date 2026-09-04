"""Opt-in API security: API-key auth and per-IP rate limiting (no extra deps)."""

from __future__ import annotations

import threading
import time
from collections import deque

_lock = threading.Lock()
_hits: dict[str, deque[float]] = {}

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
    """Clear all rate-limit state (used by tests)."""
    with _lock:
        _hits.clear()


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

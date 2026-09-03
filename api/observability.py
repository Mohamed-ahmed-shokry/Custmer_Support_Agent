"""Lightweight in-memory observability counters (no extra dependencies)."""

from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_start_time = time.monotonic()
_counters: dict[str, int] = {
    "chat_requests": 0,
    "chat_errors": 0,
    "stream_requests": 0,
    "uploads": 0,
    "upload_errors": 0,
    "deletes": 0,
}


def increment(counter: str, amount: int = 1) -> int:
    with _lock:
        _counters[counter] = _counters.get(counter, 0) + amount
        return _counters[counter]


def snapshot() -> dict[str, int | float]:
    with _lock:
        data = dict(_counters)
    data["uptime_seconds"] = round(time.monotonic() - _start_time, 2)
    return data


def render_prometheus() -> str:
    lines = []
    for key, value in snapshot().items():
        lines.append(f"rag_agent_{key} {value}")
    return "\n".join(lines) + "\n"

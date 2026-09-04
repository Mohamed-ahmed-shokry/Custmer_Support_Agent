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
    "prompt_tokens_est": 0,
    "completion_tokens_est": 0,
}
_latency: dict[str, dict[str, float]] = {}

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token). Not a billing figure."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def increment(counter: str, amount: int = 1) -> int:
    with _lock:
        _counters[counter] = _counters.get(counter, 0) + amount
        return _counters[counter]


def record_latency(group: str, seconds: float) -> None:
    with _lock:
        entry = _latency.setdefault(group, {"count": 0, "total": 0.0})
        entry["count"] += 1
        entry["total"] += seconds


def reset() -> None:
    """Reset counters (used by tests)."""
    with _lock:
        for key in _counters:
            _counters[key] = 0
        _latency.clear()


def snapshot() -> dict[str, int | float]:
    with _lock:
        data: dict[str, int | float] = dict(_counters)
        latency = {group: dict(entry) for group, entry in _latency.items()}
    data["uptime_seconds"] = round(time.monotonic() - _start_time, 2)
    for group in sorted(latency):
        count = latency[group]["count"]
        total = latency[group]["total"]
        data[f"latency_count_{group}"] = int(count)
        data[f"latency_avg_seconds_{group}"] = round(total / count, 4) if count else 0.0
    return data


def render_prometheus() -> str:
    lines = []
    for key, value in snapshot().items():
        lines.append(f"rag_agent_{key} {value}")
    return "\n".join(lines) + "\n"

"""Document collection naming (no side effects on import)."""

from __future__ import annotations

import re

DEFAULT_COLLECTION = "default"
MAX_COLLECTION_LENGTH = 64
_COLLECTION_RE = re.compile(r"[a-z0-9][a-z0-9_-]*")


def normalize_collection(value: str | None) -> str:
    """Normalize a user-supplied collection name, raising ValueError if invalid."""
    name = (value or "").strip().lower() or DEFAULT_COLLECTION
    if len(name) > MAX_COLLECTION_LENGTH or _COLLECTION_RE.fullmatch(name) is None:
        raise ValueError(
            "Collection must be 1-64 chars: lowercase letters, numbers, '-' or '_'."
        )
    return name

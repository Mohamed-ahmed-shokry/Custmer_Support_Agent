"""PII redaction for log output (no extra dependencies)."""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
PHONE_RE = re.compile(r"(?<!\d)(\+?1[-.\s]?)?(\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}(?!\d)")


def redact_pii(text: str) -> str:
    """Replace email addresses, SSNs, and phone-like numbers with placeholders."""
    redacted = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    redacted = SSN_RE.sub("[REDACTED_SSN]", redacted)
    return PHONE_RE.sub("[REDACTED_PHONE]", redacted)

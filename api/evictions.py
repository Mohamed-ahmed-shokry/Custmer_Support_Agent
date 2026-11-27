"""Eviction compliance, statutory legal notices, court filings, and payment plan workouts engine."""

from __future__ import annotations

import datetime
import secrets
from datetime import UTC
from enum import StrEnum


class NoticeType(StrEnum):
    PAY_OR_QUIT = "pay_or_quit"
    CURE_OR_QUIT = "cure_or_quit"
    UNCONDITIONAL_QUIT = "unconditional_quit"
    NON_RENEWAL = "non_renewal"


class CaseStatus(StrEnum):
    NOTICE_SERVED = "notice_served"
    CURE_WINDOW_ACTIVE = "cure_window_active"
    PAYMENT_PLAN_ACTIVE = "payment_plan_active"
    FILED_IN_COURT = "filed_in_court"
    HEARING_SCHEDULED = "hearing_scheduled"
    JUDGMENT_GRANTED = "judgment_granted"
    CURED_DISMISSED = "cured_dismissed"
    EVICTED_CLOSED = "evicted_closed"


class PaymentPlanStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    DEFAULTED = "defaulted"
    CANCELLED = "cancelled"


class DeliveryMethod(StrEnum):
    CERTIFIED_MAIL = "certified_mail"
    PERSONAL_SERVICE = "personal_service"
    POSTED_AND_MAILED = "posted_and_mailed"
    PORTAL_AND_MAIL = "portal_and_mail"


DEFAULT_CURE_DAYS = 5
MIN_SEEDED_CASES = 2


def _generate_case_id() -> str:
    return f"evc_{secrets.token_hex(4)}"


def _generate_plan_id() -> str:
    return f"ppl_{secrets.token_hex(4)}"


def _now_iso() -> str:
    return datetime.datetime.now(UTC).isoformat()


def _today_str() -> str:
    return datetime.datetime.now(UTC).strftime("%Y-%m-%d")


def _compute_cure_deadline(served_date: str, cure_days: int = DEFAULT_CURE_DAYS) -> str:
    try:
        dt = datetime.date.fromisoformat(served_date[:10])
    except ValueError:
        dt = datetime.datetime.now(UTC).date()
    return (dt + datetime.timedelta(days=max(1, cure_days))).isoformat()

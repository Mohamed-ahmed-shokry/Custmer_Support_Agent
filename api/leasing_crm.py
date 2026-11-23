"""Prospective leasing CRM, property tours, rental applications, and applicant screening engine."""

from __future__ import annotations

import datetime
import secrets
from datetime import UTC
from enum import StrEnum


class LeadSource(StrEnum):
    ZILLOW = "zillow"
    APARTMENTS_COM = "apartments_com"
    WEBSITE = "website"
    WALK_IN = "walk_in"
    REFERRAL = "referral"
    BROKER = "broker"


class ProspectStage(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    TOUR_SCHEDULED = "tour_scheduled"
    TOURED = "toured"
    APPLIED = "applied"
    APPROVED = "approved"
    LEASED = "leased"
    LOST = "lost"


class TourType(StrEnum):
    IN_PERSON = "in_person"
    VIRTUAL = "virtual"
    SELF_GUIDED = "self_guided"


class TourStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


class ApplicationStatus(StrEnum):
    SUBMITTED = "submitted"
    SCREENING = "screening"
    APPROVED = "approved"
    CONDITIONALLY_APPROVED = "conditionally_approved"
    DENIED = "denied"
    WITHDRAWN = "withdrawn"


class BackgroundCheckStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FLAGGED = "flagged"
    FAILED = "failed"


MIN_SEEDED_PROSPECTS = 2
MIN_INCOME_RATIO = 3.0
CONDITIONAL_INCOME_RATIO = 2.5
MIN_CREDIT_SCORE = 650
CONDITIONAL_CREDIT_SCORE = 600
DEFAULT_APPLICATION_FEE = 55.0


def _generate_prospect_id() -> str:
    return f"prs_{secrets.token_hex(4)}"


def _generate_tour_id() -> str:
    return f"tur_{secrets.token_hex(4)}"


def _generate_application_id() -> str:
    return f"app_{secrets.token_hex(4)}"


def _now_iso() -> str:
    return datetime.datetime.now(UTC).isoformat()


def _today_str() -> str:
    return datetime.datetime.now(UTC).strftime("%Y-%m-%d")

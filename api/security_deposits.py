"""Security deposit escrow, itemized deductions, statutory disposition, and dispute engine."""

from __future__ import annotations

import datetime
import secrets
from datetime import UTC
from enum import StrEnum


class DepositStatus(StrEnum):
    HELD = "held"
    ITEMIZED_PENDING = "itemized_pending"
    REFUNDED = "refunded"
    PARTIAL_REFUND = "partial_refund"
    FORFEITED = "forfeited"
    DISPUTED = "disputed"


class DepositType(StrEnum):
    STANDARD_SECURITY = "standard_security"
    PET_DEPOSIT = "pet_deposit"
    KEY_DEPOSIT = "key_deposit"
    LAST_MONTH_RENT = "last_month_rent"


class DeductionCategory(StrEnum):
    CLEANING = "cleaning"
    DAMAGE_REPAIR = "damage_repair"
    UNPAID_RENT = "unpaid_rent"
    KEY_REPLACEMENT = "key_replacement"
    UTILITY_BALANCE = "utility_balance"
    LEASE_BREAK_FEE = "lease_break_fee"
    OTHER = "other"


class RefundMethod(StrEnum):
    CHECK = "check"
    ACH = "ach"
    DIRECT_DEPOSIT = "direct_deposit"
    APPLIED_TO_BALANCE = "applied_to_balance"


class DisputeStatus(StrEnum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    RESOLVED_ADJUSTED = "resolved_adjusted"
    RESOLVED_UPHELD = "resolved_upheld"


DEFAULT_STATUTORY_DAYS = 21
MIN_SEEDED_DEPOSITS = 2


def _generate_deposit_id() -> str:
    return f"dep_{secrets.token_hex(4)}"


def _generate_deduction_id() -> str:
    return f"ded_{secrets.token_hex(4)}"


def _generate_dispute_id() -> str:
    return f"dsp_{secrets.token_hex(4)}"


def _now_iso() -> str:
    return datetime.datetime.now(UTC).isoformat()


def _today_str() -> str:
    return datetime.datetime.now(UTC).strftime("%Y-%m-%d")

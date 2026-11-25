"""Property owner portals, monthly disbursement statements, CapEx reserves, and approvals engine."""

from __future__ import annotations

import datetime
import secrets
from datetime import UTC
from enum import StrEnum


class OwnerStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ONBOARDING = "onboarding"


class DisbursementMethod(StrEnum):
    ACH = "ach"
    WIRE = "wire"
    CHECK = "check"


class StatementStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    DISBURSED = "disbursed"
    DISPUTED = "disputed"


class ApprovalCategory(StrEnum):
    CAPEX = "capex"
    MAJOR_REPAIR = "major_repair"
    VENDOR_CONTRACT = "vendor_contract"
    RENT_CONCESSION = "rent_concession"
    EVICTION_LEGAL = "eviction_legal"
    OTHER = "other"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MORE_INFO_REQUESTED = "more_info_requested"


MIN_SEEDED_OWNERS = 2
DEFAULT_MGMT_FEE_PCT = 8.0
MAX_MGMT_FEE_PCT = 50.0


def _generate_owner_id() -> str:
    return f"own_{secrets.token_hex(4)}"


def _generate_statement_id() -> str:
    return f"stm_{secrets.token_hex(4)}"


def _generate_approval_id() -> str:
    return f"apr_{secrets.token_hex(4)}"


def _now_iso() -> str:
    return datetime.datetime.now(UTC).isoformat()


def _current_period_month() -> str:
    return datetime.datetime.now(UTC).strftime("%Y-%m")

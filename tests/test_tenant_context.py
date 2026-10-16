"""Unit tests for tenant and property context grounding engine and macro variable resolution."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from api import db_utils
from api.macros import render_template
from api.tenant_context import (
    build_tenant_rag_context,
    extract_tenant_macro_variables,
    format_currency,
    inject_tenant_context_into_prompt,
)


@pytest.fixture(autouse=True)
def setup_temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Fixture providing an isolated temporary database for each test."""
    db_file = tmp_path / "test_tenant_context.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_file))
    with closing(sqlite3.connect(str(db_file))) as conn:
        conn.row_factory = sqlite3.Row
    db_utils.create_application_logs()
    db_utils.create_units()
    db_utils.create_tenants()
    db_utils.create_work_orders()
    db_utils.create_session_labels()
    db_utils.migrate_session_labels()
    yield


def test_format_currency():
    """Verify standard USD currency formatting and edge cases."""
    assert format_currency(None) == "$0.00"
    assert format_currency(0) == "$0.00"
    assert format_currency(1850) == "$1,850.00"
    assert format_currency(2450.75) == "$2,450.75"
    assert format_currency(1234567.89) == "$1,234,567.89"


def test_build_tenant_rag_context_empty():
    """Verify that build_tenant_rag_context returns empty string when no profile is found."""
    assert build_tenant_rag_context() == ""
    assert build_tenant_rag_context(tenant_id="non_existent") == ""
    assert build_tenant_rag_context(unit_id="non_existent") == ""
    assert build_tenant_rag_context(session_id="empty-session") == ""


def test_build_tenant_rag_context_with_tenant_and_unit():
    """Verify structured Markdown grounding block for pre-seeded tenant_1 and unit_101."""
    block = build_tenant_rag_context(tenant_id="tenant_1")
    assert "[VERIFIED RESIDENT & PROPERTY UNIT PROFILE]" in block
    assert "Resident Name: Sarah Connor" in block
    assert "Email: sarah.connor@example.com" in block
    assert "Phone: +1-555-0199" in block
    assert "Unit: 101" in block
    assert "Building: Building A" in block
    assert "Floor: 1" in block
    assert "Type: Apartment" in block
    assert "Lease Term: 2026-01-01 to 2026-12-31 (Status: active)" in block
    assert "Monthly Rent: $1,450.00 | Current Balance Due: $0.00" in block
    assert "Property Amenities & Access:" in block
    assert "- Parking Spot: P-12" in block
    assert "- Gate / Access Code: #1010" in block
    assert "- Trash Pickup: Tuesday" in block
    assert "Emergency Contact: John Connor (+1-555-0198)" in block
    assert "Tenant Account Notes: Prefers email notifications for routine maintenance." in block
    assert "[END RESIDENT & PROPERTY UNIT PROFILE]" in block
    assert "[ACTIVE MAINTENANCE WORK ORDERS]" in block
    assert "[wo_101] Kitchen faucet leaking constantly" in block
    assert "Status: scheduled" in block
    assert "[END ACTIVE MAINTENANCE WORK ORDERS]" in block


def test_build_tenant_rag_context_from_session():
    """Verify resident grounding block resolved directly from linked session_id."""
    sid = "sess-rag-context"
    db_utils.insert_application_logs(sid, "When is rent due?", "First of month", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_2")

    block = build_tenant_rag_context(session_id=sid)
    assert "Resident Name: Marcus Vance" in block
    assert "Unit: 204" in block
    assert "Monthly Rent: $1,850.00 | Current Balance Due: $1,850.00" in block
    assert "- Parking Spot: P-24" in block
    assert "- Gate / Access Code: #2040" in block


def test_build_tenant_rag_context_unit_only():
    """Verify grounding block when only unit_id is provided without tenant."""
    block = build_tenant_rag_context(unit_id="unit_PH1")
    assert "[VERIFIED RESIDENT & PROPERTY UNIT PROFILE]" in block
    assert "Resident Name" not in block
    assert "Unit: PH1" in block
    assert "Building: Main Tower" in block
    assert "Floor: 12" in block
    assert "- Gate / Access Code: *9988" in block


def test_inject_tenant_context_into_prompt():
    """Verify prompt augmentation prepends resident context block."""
    raw_query = "What is my parking spot and access code?"

    # Unlinked session returns raw query unmodified
    unlinked = inject_tenant_context_into_prompt(raw_query, session_id="unlinked-sess")
    assert unlinked == raw_query

    # Linked session prepends resident context
    sid = "sess-inject-test"
    db_utils.insert_application_logs(sid, "Hi", "Hello", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_1")

    augmented = inject_tenant_context_into_prompt(raw_query, session_id=sid)
    assert "[VERIFIED RESIDENT & PROPERTY UNIT PROFILE]" in augmented
    assert "Resident Name: Sarah Connor" in augmented
    assert "Parking Spot: P-12" in augmented
    assert "Resident Inquiry / Question:\n" in augmented
    assert raw_query in augmented


def test_extract_tenant_macro_variables():
    """Verify macro variable dictionary extraction from tenant and unit profiles."""
    # From tenant_1 (with linked unit_101)
    vars_dict = extract_tenant_macro_variables(tenant_id="tenant_1")
    assert vars_dict["customer_name"] == "Sarah Connor"
    assert vars_dict["tenant_first_name"] == "Sarah"
    assert vars_dict["tenant_last_name"] == "Connor"
    assert vars_dict["tenant_email"] == "sarah.connor@example.com"
    assert vars_dict["tenant_phone"] == "+1-555-0199"
    assert vars_dict["unit_id"] == "101"
    assert vars_dict["unit_number"] == "101"
    assert vars_dict["building"] == "Building A"
    assert vars_dict["floor"] == "1"
    assert vars_dict["unit_type"] == "Apartment"
    assert vars_dict["monthly_rent"] == "$1,450.00"
    assert vars_dict["balance_due"] == "$0.00"
    assert vars_dict["lease_start"] == "2026-01-01"
    assert vars_dict["lease_end"] == "2026-12-31"
    assert vars_dict["lease_status"] == "active"
    assert vars_dict["parking_spot"] == "P-12"
    assert vars_dict["gate_code"] == "#1010"
    assert vars_dict["access_code"] == "#1010"
    assert vars_dict["trash_day"] == "Tuesday"
    assert vars_dict["emergency_contact_name"] == "John Connor"
    assert vars_dict["emergency_contact_phone"] == "+1-555-0198"
    assert vars_dict["open_work_orders_count"] == "1"
    assert vars_dict["latest_work_order_id"] == "wo_101"
    assert vars_dict["latest_work_order_title"] == "Kitchen faucet leaking constantly"
    assert vars_dict["latest_work_order_status"] == "scheduled"


def test_build_tenant_rag_context_work_orders_grounding():
    """Verify that open work orders are grounded and completed orders are omitted."""
    # tenant_2 has open work order wo_102
    block = build_tenant_rag_context(tenant_id="tenant_2")
    assert "[ACTIVE MAINTENANCE WORK ORDERS]" in block
    assert "[wo_102] Living room AC blowing ambient air" in block
    assert "Priority: high" in block
    assert "Status: in_progress" in block

    # tenant_3 only has completed work order wo_103, so no active orders
    t3_block = build_tenant_rag_context(tenant_id="tenant_3")
    assert "[ACTIVE MAINTENANCE WORK ORDERS]" not in t3_block

    # include_work_orders=False suppresses work orders block
    suppressed = build_tenant_rag_context(tenant_id="tenant_2", include_work_orders=False)
    assert "[ACTIVE MAINTENANCE WORK ORDERS]" not in suppressed
    assert "[VERIFIED RESIDENT & PROPERTY UNIT PROFILE]" in suppressed


def test_render_template_with_work_orders():
    """Verify macro template rendering with work order variables from linked session."""
    sid = "sess-macro-wo"
    db_utils.insert_application_logs(sid, "When is repair?", "Tomorrow", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_1")

    template = (
        "Hi {customer_name}, you have {open_work_orders_count} open ticket: "
        "{latest_work_order_id} ({latest_work_order_title}) is "
        "currently {latest_work_order_status}."
    )
    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Hi Sarah Connor, you have 1 open ticket:" in rendered
    assert "wo_101 (Kitchen faucet leaking constantly) is currently scheduled." in rendered


def test_render_template_with_session_tenant_resolution():
    """Verify render_template automatically resolves tenant placeholders from session_id."""
    sid = "sess-macro-render"
    db_utils.insert_application_logs(sid, "Payment question", "Details", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_2")

    template = (
        "Hello {customer_name}, your balance for unit {unit_id} is {balance_due}. "
        "Your assigned parking spot is {parking_spot} and gate code is {gate_code}."
    )

    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Hello Marcus Vance" in rendered
    assert "unit 204 is $1,850.00" in rendered
    assert "parking spot is P-24" in rendered
    assert "gate code is #2040" in rendered


def test_render_template_overrides_tenant_variables():
    """Verify that explicitly passed variables take precedence over tenant profile defaults."""
    sid = "sess-macro-override"
    db_utils.insert_application_logs(sid, "Query", "Answer", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_1")

    template = "Resident {customer_name}, rent balance is {balance_due}."
    custom_vars = {"customer_name": "Ms. Sarah Connor, VIP", "balance_due": "$100.00"}

    rendered, unresolved = render_template(template, variables=custom_vars, session_id=sid)
    assert unresolved == []
    assert rendered == "Resident Ms. Sarah Connor, VIP, rent balance is $100.00."


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
    db_utils.create_billing_transactions()
    db_utils.create_lease_renewals()
    db_utils.create_inspections()
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


def test_build_tenant_rag_context_billing_grounding():
    """Verify that billing ledger and payment history are grounded in RAG prompt context."""
    # tenant_1 has recorded ACH payment and zero balance
    t1_block = build_tenant_rag_context(tenant_id="tenant_1")
    assert "[RESIDENT BILLING & PAYMENT LEDGER]" in t1_block
    assert "Current Balance Due: $0.00 | Monthly Rent: $1,450.00" in t1_block
    assert "Last Payment: $1,450.00 on 2026-10-01T09:30:00Z via ach (Ref: ACH-88412)" in t1_block
    assert "[END RESIDENT BILLING & PAYMENT LEDGER]" in t1_block

    # tenant_2 has overdue rent and late fee
    t2_block = build_tenant_rag_context(tenant_id="tenant_2")
    assert "[RESIDENT BILLING & PAYMENT LEDGER]" in t2_block
    assert "Overdue Amount:" in t2_block
    assert "overdue charge(s)" in t2_block

    # include_billing=False suppresses billing block
    suppressed = build_tenant_rag_context(tenant_id="tenant_1", include_billing=False)
    assert "[RESIDENT BILLING & PAYMENT LEDGER]" not in suppressed
    assert "[VERIFIED RESIDENT & PROPERTY UNIT PROFILE]" in suppressed


def test_render_template_with_billing_variables():
    """Verify macro template rendering with financial and billing variables."""
    sid = "sess-macro-billing"
    db_utils.insert_application_logs(sid, "Payment info", "Here is your statement", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_1")

    template = (
        "Dear {customer_name}, your last payment of {last_payment_amount} "
        "was received on {last_payment_date} via {last_payment_method} "
        "(Ref: {last_payment_reference}). Overdue balance: {overdue_balance}."
    )
    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Dear Sarah Connor" in rendered
    assert "payment of $1,450.00" in rendered
    assert "via ach" in rendered
    assert "Overdue balance: $0.00" in rendered


def test_build_tenant_rag_context_renewals_grounding():
    """Verify that lease renewal offers and status are grounded in RAG prompt context."""
    # tenant_1 has offered renewal lr_101
    t1_block = build_tenant_rag_context(tenant_id="tenant_1")
    assert "[LEASE RENEWAL OFFERS & AGREEMENTS]" in t1_block
    assert "[lr_101] Status: OFFERED" in t1_block
    assert "Current Rent: $1,450.00 -> Proposed Rent: $1,500.00" in t1_block
    assert "Incentive: $100.00" in t1_block
    assert "[END LEASE RENEWAL OFFERS & AGREEMENTS]" in t1_block

    # tenant_3 has signed renewal lr_103
    t3_block = build_tenant_rag_context(tenant_id="tenant_3")
    assert "[LEASE RENEWAL OFFERS & AGREEMENTS]" in t3_block
    assert "[lr_103] Status: SIGNED" in t3_block
    assert "Signed By: Eleanor Vance" in t3_block

    # include_renewals=False suppresses renewals block
    suppressed = build_tenant_rag_context(tenant_id="tenant_1", include_renewals=False)
    assert "[LEASE RENEWAL OFFERS & AGREEMENTS]" not in suppressed
    assert "[VERIFIED RESIDENT & PROPERTY UNIT PROFILE]" in suppressed


def test_render_template_with_renewal_variables():
    """Verify macro template rendering with lease renewal variables."""
    sid = "sess-macro-renewal"
    db_utils.insert_application_logs(sid, "Renewal inquiry", "Here is your offer", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_1")

    template = (
        "Hello {customer_name}, your renewal offer ({renewal_id}) is {renewal_status}. "
        "Proposed rent: {renewal_proposed_rent} for {renewal_term_months} months. "
        "Offer expires on {renewal_expires_at}."
    )
    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Hello Sarah Connor" in rendered
    assert "renewal offer (lr_101) is offered" in rendered
    assert "Proposed rent: $1,500.00 for 12 months" in rendered
    assert "Offer expires on 2026-10-31" in rendered


def test_build_tenant_rag_context_inspections_grounding():
    """Verify that resident move-in/out inspections and deposit settlements are grounded."""
    # tenant_2 has scheduled pre-move-out inspection insp_102
    t2_block = build_tenant_rag_context(tenant_id="tenant_2")
    assert "[RESIDENT INSPECTIONS, MOVE-IN/OUT & DEPOSIT SETTLEMENT]" in t2_block
    assert "[insp_102] Type: PRE-MOVE-OUT" in t2_block
    assert "Status: SCHEDULED" in t2_block
    assert "Condition: GOOD" in t2_block
    assert "Inspector: Alex Rivera" in t2_block
    assert "Keys: PENDING" in t2_block
    assert "Kitchen:Oven & Stove(clean)" in t2_block
    assert "[END RESIDENT INSPECTIONS, MOVE-IN/OUT & DEPOSIT SETTLEMENT]" in t2_block

    # tenant_3 has completed move-out inspection insp_103 with deductions
    t3_block = build_tenant_rag_context(tenant_id="tenant_3")
    assert "[RESIDENT INSPECTIONS, MOVE-IN/OUT & DEPOSIT SETTLEMENT]" in t3_block
    assert "[insp_103] Type: MOVE-OUT" in t3_block
    assert "Status: COMPLETED" in t3_block
    assert "Condition: FAIR" in t3_block
    assert "Deductions: $150.00" in t3_block
    assert "Net Refund: $1,850.00" in t3_block
    assert "Keys: RETURNED" in t3_block
    assert "Living Room:Drywall(repair)" in t3_block

    # include_inspections=False suppresses inspection block
    suppressed = build_tenant_rag_context(tenant_id="tenant_2", include_inspections=False)
    assert "[RESIDENT INSPECTIONS, MOVE-IN/OUT & DEPOSIT SETTLEMENT]" not in suppressed
    assert "[VERIFIED RESIDENT & PROPERTY UNIT PROFILE]" in suppressed


def test_render_template_with_inspection_variables():
    """Verify macro template rendering with inspection and deposit settlement variables."""
    sid = "sess-macro-inspection"
    db_utils.insert_application_logs(sid, "Inspection inquiry", "Here is your inspection", "gpt-4o")
    db_utils.link_session_tenant(sid, tenant_id="tenant_3")

    template = (
        "Dear {customer_name}, inspection {inspection_id} ({inspection_type}) "
        "is {inspection_status}. Total deductions: {inspection_deposit_deductions}, "
        "net refund: {inspection_deposit_refund}, keys: {key_return_status}."
    )
    rendered, unresolved = render_template(template, session_id=sid)
    assert unresolved == []
    assert "Dear Elena Rostova" in rendered
    assert "inspection insp_103 (move_out) is completed" in rendered
    assert "Total deductions: $150.00" in rendered
    assert "net refund: $1,850.00" in rendered
    assert "keys: returned" in rendered

"""Tenant and Property Unit Context Grounding Engine.

Provides context extraction, structured prompt grounding blocks, and macro variable
resolution for personalized customer support in property management workflows.
"""

from __future__ import annotations

import logging
from typing import Any

from api.db_utils import (
    get_session_tenant_context,
    get_tenant,
    get_tenant_ledger_summary,
    get_tenant_work_orders,
    get_unit,
    get_unit_work_orders,
)

logger = logging.getLogger(__name__)


def format_currency(value: float | int | None) -> str:
    """Format numeric amount into standard USD currency string ($X,XXX.XX)."""
    if value is None:
        return "$0.00"
    try:
        val = float(value)
        return f"${val:,.2f}"
    except (ValueError, TypeError):
        return f"${value}"


def _resolve_tenant_and_unit(
    session_id: str | None = None,
    tenant_id: str | None = None,
    unit_id: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Look up tenant and unit dictionaries based on session, tenant, or unit ID."""
    tenant: dict[str, Any] | None = None
    unit: dict[str, Any] | None = None

    if session_id and not tenant_id:
        ctx = get_session_tenant_context(session_id)
        if ctx:
            tenant = ctx.get("tenant")
            unit = ctx.get("unit")
            tenant_id = ctx.get("tenant_id")
            unit_id = ctx.get("unit_id")

    if tenant_id and not tenant:
        tenant = get_tenant(tenant_id)
        if tenant and not unit_id:
            unit_id = tenant.get("unit_id")

    if unit_id and not unit:
        unit = get_unit(unit_id)

    return tenant, unit


def _format_unit_lines(unit: dict[str, Any]) -> list[str]:
    """Format unit physical details and amenities."""
    lines: list[str] = []
    unit_num = unit.get("unit_number", "Unknown")
    bldg = unit.get("building") or unit.get("building_name")
    floor = unit.get("floor")
    u_type = unit.get("unit_type") or "Apartment"

    loc_parts: list[str] = []
    if bldg:
        loc_parts.append(f"Building: {bldg}")
    if floor is not None:
        loc_parts.append(f"Floor: {floor}")
    loc_parts.append(f"Type: {u_type}")
    lines.append(f"Unit: {unit_num} ({', '.join(loc_parts)})")

    amenities: list[str] = []
    if unit.get("parking_spot"):
        amenities.append(f"Parking Spot: {unit['parking_spot']}")
    gate = unit.get("access_code") or unit.get("gate_code")
    if gate:
        amenities.append(f"Gate / Access Code: {gate}")
    if unit.get("trash_day"):
        amenities.append(f"Trash Pickup: {unit['trash_day']}")
    if amenities:
        lines.append("Property Amenities & Access:")
        for a in amenities:
            lines.append(f"  - {a}")
    return lines


def _format_tenant_lines(tenant: dict[str, Any], has_unit: bool) -> list[str]:
    """Format tenant contact, lease, balance, and emergency contact details."""
    lines: list[str] = []
    full_name = f"{tenant.get('first_name', '')} {tenant.get('last_name', '')}".strip()
    lines.append(f"Resident Name: {full_name or 'Unknown'}")
    if tenant.get("email"):
        lines.append(f"Email: {tenant['email']}")
    if tenant.get("phone"):
        lines.append(f"Phone: {tenant['phone']}")
    if not has_unit and tenant.get("unit_id"):
        lines.append(f"Unit ID: {tenant['unit_id']}")

    start = tenant.get("lease_start") or "N/A"
    end = tenant.get("lease_end") or "N/A"
    status = tenant.get("status") or "active"
    lines.append(f"Lease Term: {start} to {end} (Status: {status})")

    rent_str = format_currency(tenant.get("monthly_rent"))
    balance_str = format_currency(tenant.get("balance_due"))
    lines.append(f"Monthly Rent: {rent_str} | Current Balance Due: {balance_str}")

    em_name = tenant.get("emergency_contact_name")
    em_phone = tenant.get("emergency_contact_phone")
    if em_name or em_phone:
        lines.append(f"Emergency Contact: {em_name or 'N/A'} ({em_phone or 'N/A'})")
    if tenant.get("notes"):
        lines.append(f"Tenant Account Notes: {tenant['notes']}")
    return lines


def _format_work_orders_lines(work_orders: list[dict[str, Any]]) -> list[str]:
    """Format active maintenance work order tickets."""
    lines: list[str] = ["[ACTIVE MAINTENANCE WORK ORDERS]"]
    for wo in work_orders:
        wo_id = wo.get("id", "Unknown")
        title = wo.get("title", "Untitled")
        cat = wo.get("category", "general")
        prio = wo.get("priority", "medium")
        status = wo.get("status", "submitted")
        assignee = wo.get("assigned_to") or "Unassigned"
        sched = wo.get("scheduled_date")
        entry = wo.get("entry_permission") or "permission_granted"

        parts = [
            f"[{wo_id}] {title}",
            f"Category: {cat}",
            f"Priority: {prio}",
            f"Status: {status}",
            f"Assigned To: {assignee}",
        ]
        if sched:
            parts.append(f"Scheduled: {sched}")
        parts.append(f"Entry: {entry}")
        if wo.get("resolution_notes"):
            parts.append(f"Notes: {wo['resolution_notes']}")
        lines.append("  - " + " | ".join(parts))
    lines.append("[END ACTIVE MAINTENANCE WORK ORDERS]")
    return lines


def _format_billing_lines(ledger_summary: dict[str, Any]) -> list[str]:
    """Format resident billing ledger statement and overdue charges."""
    lines: list[str] = ["[RESIDENT BILLING & PAYMENT LEDGER]"]
    cur_bal = format_currency(ledger_summary.get("current_balance"))
    rent = format_currency(ledger_summary.get("monthly_rent"))
    lines.append(f"Current Balance Due: {cur_bal} | Monthly Rent: {rent}")
    if ledger_summary.get("overdue_amount", 0) > 0:
        overdue_amt = format_currency(ledger_summary.get("overdue_amount"))
        count = ledger_summary.get("overdue_count", 0)
        lines.append(f"Overdue Amount: {overdue_amt} ({count} overdue charge(s))")

    last_pay = ledger_summary.get("last_payment")
    if last_pay:
        pay_amt = format_currency(last_pay.get("amount"))
        pay_date = last_pay.get("paid_at") or last_pay.get("due_date") or "N/A"
        pay_method = last_pay.get("payment_method") or "N/A"
        pay_ref = last_pay.get("reference_number") or "N/A"
        lines.append(
            f"Last Payment: {pay_amt} on {pay_date} via {pay_method} (Ref: {pay_ref})"
        )
    else:
        lines.append("Last Payment: No recorded payments")

    recent = ledger_summary.get("recent_transactions", [])
    if recent:
        lines.append("Recent Transactions:")
        for tx in recent[:3]:
            tx_id = tx.get("id", "")
            tx_type = tx.get("transaction_type", "")
            amt = format_currency(tx.get("amount"))
            st = tx.get("status", "")
            desc = tx.get("description", "")
            dt = tx.get("due_date") or tx.get("created_at") or ""
            lines.append(
                f"  - [{tx_id}] {dt} | {tx_type.upper()} | {amt} | Status: {st} | {desc}"
            )
    lines.append("[END RESIDENT BILLING & PAYMENT LEDGER]")
    return lines


def build_tenant_rag_context(
    tenant_id: str | None = None,
    unit_id: str | None = None,
    session_id: str | None = None,
    include_work_orders: bool = True,
    include_billing: bool = True,
) -> str:
    """Build structured Markdown block of verified tenant, unit, work orders, and billing."""
    tenant, unit = _resolve_tenant_and_unit(session_id, tenant_id, unit_id)
    resolved_tenant_id = tenant.get("id") if tenant else tenant_id
    resolved_unit_id = unit.get("id") if unit else unit_id

    work_orders: list[dict[str, Any]] = []
    if include_work_orders:
        if resolved_tenant_id:
            work_orders = get_tenant_work_orders(resolved_tenant_id, open_only=True)
        elif resolved_unit_id:
            work_orders = get_unit_work_orders(resolved_unit_id, open_only=True)

    ledger_summary: dict[str, Any] | None = None
    if include_billing and resolved_tenant_id:
        ledger_summary = get_tenant_ledger_summary(resolved_tenant_id)

    if not tenant and not unit and not work_orders and not ledger_summary:
        return ""

    lines: list[str] = []
    if tenant or unit:
        lines.append("[VERIFIED RESIDENT & PROPERTY UNIT PROFILE]")
        if tenant:
            lines.extend(_format_tenant_lines(tenant, has_unit=bool(unit)))
        if unit:
            lines.extend(_format_unit_lines(unit))
        lines.append("[END RESIDENT & PROPERTY UNIT PROFILE]")

    if work_orders:
        if lines:
            lines.append("")
        lines.extend(_format_work_orders_lines(work_orders))

    if ledger_summary:
        if lines:
            lines.append("")
        lines.extend(_format_billing_lines(ledger_summary))

    return "\n".join(lines)


def inject_tenant_context_into_prompt(
    query: str,
    session_id: str | None = None,
    tenant_id: str | None = None,
    unit_id: str | None = None,
) -> str:
    """Prepend verified resident context to a customer support user query."""
    context_block = build_tenant_rag_context(
        tenant_id=tenant_id, unit_id=unit_id, session_id=session_id
    )
    if not context_block:
        return query

    return (
        f"{context_block}\n\n"
        f"Resident Inquiry / Question:\n{query}"
    )


def _extract_tenant_vars(tenant: dict[str, Any]) -> dict[str, str]:
    """Extract string variables from tenant profile dictionary."""
    vars_dict: dict[str, str] = {}
    first = tenant.get("first_name", "")
    last = tenant.get("last_name", "")
    full_name = f"{first} {last}".strip()
    if full_name:
        vars_dict["customer_name"] = full_name
    if first:
        vars_dict["tenant_first_name"] = first
    if last:
        vars_dict["tenant_last_name"] = last

    str_fields = (
        ("email", "tenant_email"),
        ("phone", "tenant_phone"),
        ("lease_start", "lease_start"),
        ("lease_end", "lease_end"),
        ("status", "lease_status"),
        ("emergency_contact_name", "emergency_contact_name"),
        ("emergency_contact_phone", "emergency_contact_phone"),
        ("unit_id", "unit_id"),
    )
    for src, dst in str_fields:
        if tenant.get(src):
            vars_dict[dst] = str(tenant[src])

    if tenant.get("monthly_rent") is not None:
        vars_dict["monthly_rent"] = format_currency(tenant["monthly_rent"])
    if tenant.get("balance_due") is not None:
        vars_dict["balance_due"] = format_currency(tenant["balance_due"])
    return vars_dict


def _extract_unit_vars(unit: dict[str, Any]) -> dict[str, str]:
    """Extract string variables from unit profile dictionary."""
    vars_dict: dict[str, str] = {}
    unit_num = unit.get("unit_number", "")
    if unit_num:
        vars_dict["unit_id"] = unit_num
        vars_dict["unit_number"] = unit_num
    bldg = unit.get("building") or unit.get("building_name")
    if bldg:
        vars_dict["building"] = bldg
    if unit.get("floor") is not None:
        vars_dict["floor"] = str(unit["floor"])
    vars_dict["unit_type"] = unit.get("unit_type") or "Apartment"
    if unit.get("parking_spot"):
        vars_dict["parking_spot"] = unit["parking_spot"]
    gate = unit.get("access_code") or unit.get("gate_code")
    if gate:
        vars_dict["gate_code"] = gate
        vars_dict["access_code"] = gate
    if unit.get("trash_day"):
        vars_dict["trash_day"] = unit["trash_day"]
    return vars_dict


def extract_tenant_macro_variables(
    session_id: str | None = None,
    tenant_id: str | None = None,
    unit_id: str | None = None,
) -> dict[str, str]:
    """Extract macro template replacement variables from linked tenant and property profiles."""
    tenant, unit = _resolve_tenant_and_unit(session_id, tenant_id, unit_id)
    variables: dict[str, str] = {}
    if tenant:
        variables.update(_extract_tenant_vars(tenant))
    if unit:
        variables.update(_extract_unit_vars(unit))

    resolved_tenant_id = tenant.get("id") if tenant else tenant_id
    resolved_unit_id = unit.get("id") if unit else unit_id
    work_orders: list[dict[str, Any]] = []
    if resolved_tenant_id:
        work_orders = get_tenant_work_orders(resolved_tenant_id, open_only=True)
    elif resolved_unit_id:
        work_orders = get_unit_work_orders(resolved_unit_id, open_only=True)

    if work_orders:
        variables["open_work_orders_count"] = str(len(work_orders))
        latest = work_orders[0]
        variables["latest_work_order_id"] = str(latest.get("id", ""))
        variables["latest_work_order_title"] = str(latest.get("title", ""))
        variables["latest_work_order_status"] = str(latest.get("status", ""))
    else:
        variables["open_work_orders_count"] = "0"

    if resolved_tenant_id:
        ledger = get_tenant_ledger_summary(resolved_tenant_id)
        if ledger:
            last_pay = ledger.get("last_payment")
            if last_pay:
                variables["last_payment_amount"] = format_currency(last_pay.get("amount"))
                variables["last_payment_date"] = str(
                    last_pay.get("paid_at") or last_pay.get("due_date") or ""
                )
                variables["last_payment_method"] = str(last_pay.get("payment_method", ""))
                variables["last_payment_reference"] = str(last_pay.get("reference_number", ""))
            else:
                variables["last_payment_amount"] = "$0.00"
                variables["last_payment_date"] = ""
                variables["last_payment_method"] = ""
                variables["last_payment_reference"] = ""

            variables["overdue_balance"] = format_currency(ledger.get("overdue_amount", 0.0))
            variables["overdue_charges_count"] = str(ledger.get("overdue_count", 0))

    return variables

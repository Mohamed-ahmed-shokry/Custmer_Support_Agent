"""Resident Move-In/Move-Out Inspections, Turnover Punchlists & Security Deposit Accounting Engine.

Provides inspection report Markdown synthesis, turnover condition records,
and RAG knowledge base document publishing for property management unit inspections.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from api import db_utils
from api.chroma_utils import ChunkingOptions, ChunkingStrategy, reindex_chunks_in_chroma
from api.tenant_context import format_currency

logger = logging.getLogger(__name__)


def generate_inspection_report_markdown(inspection_id: str) -> str:
    """Generate a structured Markdown inspection condition report and deposit settlement statement.

    Args:
        inspection_id: ID of the inspection record.

    Returns:
        Formatted Markdown document ready for display or RAG knowledge indexing.
    """
    inspection = db_utils.get_inspection(inspection_id)
    if not inspection:
        raise ValueError(f"Inspection with ID '{inspection_id}' not found.")

    tenant = db_utils.get_tenant(inspection["tenant_id"]) or {}
    unit = db_utils.get_unit(inspection["unit_id"]) or {}

    tenant_name = (
        f"{tenant.get('first_name', '')} {tenant.get('last_name', '')}".strip()
        or "Valued Resident"
    )
    tenant_email = tenant.get("email", "N/A")
    tenant_phone = tenant.get("phone", "N/A")

    property_name = unit.get("property_name") or "Residential Community"
    unit_number = unit.get("unit_number") or inspection["unit_id"]
    address = unit.get("address", "")
    city = unit.get("city", "")
    state = unit.get("state", "")
    zip_code = unit.get("zip_code", "")
    full_address = (
        f"{address}, Unit {unit_number}, {city}, {state} {zip_code}".strip(", ")
    )

    insp_type = str(inspection.get("inspection_type") or "move_out").upper().replace("_", "-")
    status = str(inspection.get("status") or "scheduled").upper()
    condition = str(inspection.get("overall_condition") or "good").upper()
    scheduled_date = inspection.get("scheduled_date") or "N/A"
    completed_date = inspection.get("completed_date") or "Pending"
    inspector = inspection.get("inspector_name") or "Property Inspector"
    key_return = str(inspection.get("key_return_status") or "pending").upper().replace("_", " ")

    deductions_total = float(inspection.get("deposit_deduction_total", 0.0))
    refund_amount = float(inspection.get("deposit_refund_amount", 0.0))
    deductions_str = format_currency(deductions_total)
    refund_str = format_currency(refund_amount)

    items = inspection.get("items", [])

    sections = [
        f"# RESIDENTIAL UNIT CONDITION & INSPECTION STATEMENT ({insp_type})",
        f"**Inspection Reference ID:** `{inspection['id']}`  ",
        f"**Inspection Status:** `{status}`  ",
        f"**Overall Condition:** `{condition}`  ",
        f"**Scheduled Date:** {scheduled_date} | **Completed Date:** {completed_date}  ",
        f"**Certified Inspector:** {inspector}  \n",
        "---",
        "## 1. DEMISED PREMISES & RESIDENT DETAILS",
        f"- **Property:** {property_name}",
        f"- **Premises Address:** {full_address} (Unit ID: `{inspection['unit_id']}`)",
        f"- **Resident Name:** {tenant_name}",
        f"- **Contact:** {tenant_email} | {tenant_phone}",
        f"- **Resident Account ID:** `{inspection['tenant_id']}`\n",
        "## 2. ROOM-BY-ROOM CONDITION CHECKLIST & PUNCHLIST",
    ]

    if not items:
        sections.append("*No itemized checklist records attached to this inspection.*")
    else:
        sections.append("| Room / Area | Item | Condition | Action Needed | Est. Cost | Notes |")
        sections.append("|-------------|------|-----------|---------------|-----------|-------|")
        for item in items:
            r = item.get("room", "General")
            name = item.get("item_name", "Item")
            c = item.get("condition", "good").capitalize()
            action = item.get("action_needed", "none").capitalize()
            cost = format_currency(float(item.get("estimated_cost", 0.0)))
            notes = item.get("notes", "").replace("|", "-")
            sections.append(f"| {r} | {name} | {c} | {action} | {cost} | {notes} |")

    sections.extend([
        "\n## 3. ACCESS DEVICES & KEY RETURN VERIFICATION",
        f"- **Key & Access Device Status:** `{key_return}`",
        (
            "- **Standard Turnover Requirements:** All unit keys, building fobs, mailbox keys, "
            "and parking gate clickers must be accounted for upon final departure.\n"
        ),
        "## 4. SECURITY DEPOSIT SETTLEMENT & DEDUCTION SUMMARY",
        f"- **Total Itemized Deductions:** {deductions_str}",
        f"- **Net Security Deposit Refund:** {refund_str}",
        (
            "- **Settlement Note:** In accordance with state residential tenancy regulations, "
            "allowable deductions are itemized above. Net refunds are disbursed to the resident "
            "forwarding payment method on record within statutory timeframes.\n"
        ),
        "## 5. GENERAL INSPECTION NOTES & OBSERVATIONS",
        (
            inspection.get("notes")
            or "Walkthrough completed in accordance with standard property turnover criteria."
        ),
        "\n---",
        (
            f"*Statement synthesized electronically on behalf of {property_name} Management. "
            f"Reference: {inspection['id']}*"
        ),
    ])

    return "\n".join(sections)


def publish_inspection_document(  # noqa: PLR0913
    inspection_id: str,
    collection: str = "default",
    chunking_strategy: str = "markdown",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> dict[str, Any]:
    """Publish an inspection condition and settlement report into the document store and Chroma.

    Args:
        inspection_id: Inspection ID to publish.
        collection: Target document collection name.
        chunking_strategy: Chunking strategy ('markdown', 'semantic', 'recursive').
        chunk_size: Chunk size in characters.
        chunk_overlap: Chunk overlap in characters.

    Returns:
        Summary dict containing document metadata and indexing status.
    """
    inspection = db_utils.get_inspection(inspection_id)
    if not inspection:
        raise ValueError(f"Inspection with ID '{inspection_id}' not found.")

    markdown_content = generate_inspection_report_markdown(inspection_id)
    target_col = db_utils.normalize_collection(collection)
    filename = f"inspection_{inspection_id}.md"

    content_bytes = markdown_content.encode("utf-8")
    content_hash = hashlib.sha256(content_bytes).hexdigest()

    existing_doc = db_utils.get_document_by_hash(content_hash)
    if existing_doc is not None:
        file_id = existing_doc["id"]
    else:
        file_id = db_utils.insert_document_record(filename, target_col, content_hash)

    strat_enum = ChunkingStrategy(chunking_strategy)
    options = ChunkingOptions(
        strategy=strat_enum,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    db_utils.save_document_source(
        file_id=file_id,
        source_text=markdown_content,
        strategy=strat_enum.value,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    indexed_in_chroma = False
    try:
        indexed_in_chroma = bool(
            reindex_chunks_in_chroma(
                file_id=file_id,
                source_text=markdown_content,
                filename=filename,
                collection=target_col,
                options=options,
            )
        )
    except Exception as exc:
        logger.warning(
            "Chroma vectorstore indexing skipped/failed for inspection #%s: %s",
            inspection_id,
            exc,
        )

    db_utils.update_inspection(
        insp_id=inspection_id,
        document_file_id=file_id,
    )

    return {
        "inspection_id": inspection_id,
        "file_id": file_id,
        "filename": filename,
        "collection": target_col,
        "sha256": content_hash,
        "content_length": len(markdown_content),
        "indexed_in_chroma": indexed_in_chroma,
    }

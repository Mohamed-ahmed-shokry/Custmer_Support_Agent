"""Lease Renewal Offers, Addenda, Digital Agreements & E-Sign Engine.

Provides agreement Markdown synthesis, RAG knowledge base document publishing,
and contract generation for property management lease renewals.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from api import db_utils
from api.chroma_utils import ChunkingOptions, ChunkingStrategy, reindex_chunks_in_chroma
from api.tenant_context import format_currency

logger = logging.getLogger(__name__)


def generate_lease_renewal_markdown(renewal_id: str) -> str:
    """Generate a structured Markdown legal lease renewal agreement and addendum.

    Args:
        renewal_id: ID of the lease renewal offer.

    Returns:
        Formatted Markdown document ready for display, signing, or knowledge indexing.
    """
    renewal = db_utils.get_lease_renewal(renewal_id)
    if not renewal:
        raise ValueError(f"Lease renewal with ID '{renewal_id}' not found.")

    tenant = db_utils.get_tenant(renewal["tenant_id"]) or {}
    unit = db_utils.get_unit(renewal["unit_id"]) or {}

    tenant_name = (
        f"{tenant.get('first_name', '')} {tenant.get('last_name', '')}".strip()
        or "Valued Resident"
    )
    tenant_email = tenant.get("email", "N/A")
    tenant_phone = tenant.get("phone", "N/A")

    property_name = unit.get("property_name") or "Residential Community"
    unit_number = unit.get("unit_number") or renewal["unit_id"]
    address = unit.get("address", "")
    city = unit.get("city", "")
    state = unit.get("state", "")
    zip_code = unit.get("zip_code", "")
    full_address = (
        f"{address}, Unit {unit_number}, {city}, {state} {zip_code}".strip(", ")
    )

    curr_rent = format_currency(renewal.get("current_rent", 0.0))
    prop_rent = format_currency(renewal.get("proposed_rent", 0.0))
    diff_val = renewal.get("proposed_rent", 0.0) - renewal.get("current_rent", 0.0)
    diff_rent = format_currency(abs(diff_val))
    diff_label = "Increase" if diff_val >= 0 else "Reduction"

    term_months = renewal.get("term_months", 12)
    start_date = renewal.get("start_date", "YYYY-MM-DD")
    end_date = renewal.get("end_date", "YYYY-MM-DD")
    expires_at = renewal.get("expires_at", "N/A")
    status = renewal.get("status", "offered").upper()

    concession_amount = renewal.get("concession_amount", 0.0)
    concession_str = format_currency(concession_amount)
    concession_notes = renewal.get("concession_notes", "").strip()
    sec_dep = renewal.get("security_deposit_change", 0.0)
    sec_dep_str = format_currency(abs(sec_dep))
    sec_dep_label = "Additional Deposit" if sec_dep >= 0 else "Deposit Refund"

    sig_name = renewal.get("signature_name") or "Pending Signature"
    sig_ip = renewal.get("signature_ip") or "N/A"
    signed_at = renewal.get("signed_at") or "Not yet signed"

    sections = [
        "# RESIDENTIAL LEASE RENEWAL AGREEMENT & EXTENSION ADDENDUM",
        f"**Agreement Reference ID:** `{renewal['id']}`  ",
        f"**Document Status:** `{status}`  ",
        f"**Offer Expiration Deadline:** {expires_at}  \n",
        "---",
        "## 1. PARTIES & DEMISED PREMISES",
        (
            f"This Lease Renewal Agreement ('Agreement') is entered into by and between the "
            f"Landlord/Property Management entity representing **{property_name}**, "
            "and the following Resident(s):"
        ),
        f"- **Resident Name:** {tenant_name}",
        f"- **Email:** {tenant_email} | **Phone:** {tenant_phone}",
        f"- **Resident Account ID:** `{renewal['tenant_id']}`",
        f"- **Demised Premises (Unit):** {full_address} (Unit ID: `{renewal['unit_id']}`)\n",
        "## 2. EXTENSION TERM & EFFECTIVE DATES",
        (
            "The existing lease agreement for the Demised Premises is hereby extended and "
            f"renewed for a term of **{term_months} months**:"
        ),
        f"- **Renewal Commencement Date:** {start_date}",
        f"- **Renewal Expiration Date:** {end_date}\n",
        "## 3. RENT SCHEDULE & FINANCIAL TERMS",
        (
            "Throughout the renewal term, the Resident agrees to remit monthly rent "
            "according to the following schedule:"
        ),
        f"- **Current Monthly Base Rent:** {curr_rent}",
        (
            f"- **New Proposed Monthly Base Rent:** **{prop_rent}** "
            f"({diff_label}: {diff_rent} / month)"
        ),
        "- **Rent Due Date:** 1st day of each calendar month",
        "- **Grace Period:** 5 days after due date before late fee assessment.\n",
    ]

    if concession_amount > 0:
        c_notes = concession_notes or "One-time renewal concession applied upon execution."
        sections.extend(
            [
                "## 4. SPECIAL CONCESSIONS & SIGNING INCENTIVES",
                f"- **Renewal Concession Credit:** **{concession_str}**",
                f"- **Terms / Notes:** {c_notes}\n",
            ]
        )
    else:
        sections.extend(
            [
                "## 4. SPECIAL CONCESSIONS",
                "No promotional concessions or rent discounts apply to this renewal agreement.\n",
            ]
        )

    if sec_dep != 0:
        sections.extend(
            [
                "## 5. SECURITY DEPOSIT ADJUSTMENT",
                f"- **{sec_dep_label}:** {sec_dep_str}",
                (
                    "- Any additional deposit requirement is due on or before "
                    "the Renewal Commencement Date.\n"
                ),
            ]
        )

    sections.extend(
        [
            "## 6. RATIFICATION OF ORIGINAL LEASE",
            (
                "Except as expressly modified herein, all covenants, representations, rules, "
                "community policies, and obligations set forth in the original Lease Agreement "
                "shall remain in full force and effect.\n"
            ),
            "## 7. EXECUTION & DIGITAL SIGNATURE AUDIT",
            (
                "By signing below electronically, the Resident confirms having read, understood, "
                "and voluntarily agreed to the renewal terms set forth in this Agreement."
            ),
            f"- **Resident Electronic Signature:** `{sig_name}`",
            f"- **Execution Timestamp:** {signed_at}",
            f"- **Digital Signer IP Address:** `{sig_ip}`\n",
            "---",
            f"*Generated by Customer Support Agent Platform. Agreement ID: {renewal['id']}*",
        ]
    )

    return "\n".join(sections)


def publish_lease_renewal_document(
    renewal_id: str,
    collection: str = "default",
    chunking_strategy: str = "markdown",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> dict[str, Any]:
    """Synthesize Markdown agreement, store into document_store/sources, and index in Chroma.

    Args:
        renewal_id: ID of the lease renewal offer.
        collection: Target document collection.
        chunking_strategy: Chunking strategy ('markdown', 'recursive', 'semantic').
        chunk_size: Chunk size in characters.
        chunk_overlap: Chunk overlap in characters.

    Returns:
        Summary dict containing document metadata and indexing status.
    """
    renewal = db_utils.get_lease_renewal(renewal_id)
    if not renewal:
        raise ValueError(f"Lease renewal with ID '{renewal_id}' not found.")

    markdown_content = generate_lease_renewal_markdown(renewal_id)
    target_col = db_utils.normalize_collection(collection)
    filename = f"lease_renewal_{renewal_id}.md"

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
            "Chroma vectorstore indexing skipped/failed for lease renewal #%s: %s",
            renewal_id,
            exc,
        )

    db_utils.update_lease_renewal(
        renewal_id=renewal_id,
        document_file_id=file_id,
    )

    return {
        "renewal_id": renewal_id,
        "file_id": file_id,
        "filename": filename,
        "collection": target_col,
        "sha256": content_hash,
        "content_length": len(markdown_content),
        "indexed_in_chroma": indexed_in_chroma,
    }

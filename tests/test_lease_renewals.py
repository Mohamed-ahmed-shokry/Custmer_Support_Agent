"""Unit tests for Lease Renewal Agreement Generation and RAG Publishing Engine."""

from unittest.mock import patch

import pytest
from api import db_utils, lease_renewals
from tests.test_db_utils import initialize_temp_db


def test_generate_lease_renewal_markdown(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    # 1. Error on unknown renewal
    with pytest.raises(ValueError, match="not found"):
        lease_renewals.generate_lease_renewal_markdown("non_existent_id")

    # 2. Generate markdown for seeded lr_101
    md_101 = lease_renewals.generate_lease_renewal_markdown("lr_101")
    assert "RESIDENTIAL LEASE RENEWAL AGREEMENT & EXTENSION ADDENDUM" in md_101
    assert "Reference ID" in md_101 and "lr_101" in md_101
    assert "Document Status" in md_101 and "OFFERED" in md_101
    assert "DEMISED PREMISES" in md_101
    assert "$1,450.00" in md_101
    assert "$1,500.00" in md_101
    assert "First month renewal credit of $100" in md_101
    assert "Pending Signature" in md_101

    # 3. Generate markdown for signed lr_103 with security deposit change
    md_103 = lease_renewals.generate_lease_renewal_markdown("lr_103")
    assert "Reference ID" in md_103 and "lr_103" in md_103
    assert "Document Status" in md_103 and "SIGNED" in md_103
    assert "SECURITY DEPOSIT ADJUSTMENT" in md_103
    assert "$150.00" in md_103
    assert "Eleanor Vance" in md_103
    assert "192.168.1.105" in md_103


def test_publish_lease_renewal_document(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    min_length_100 = 100
    # Mock Chroma indexing
    with patch("api.lease_renewals.reindex_chunks_in_chroma", return_value=True) as mock_chroma:
        res = lease_renewals.publish_lease_renewal_document("lr_101", collection="default")
        assert res["renewal_id"] == "lr_101"
        assert res["file_id"] > 0
        assert res["filename"] == "lease_renewal_lr_101.md"
        assert res["collection"] == "default"
        assert res["indexed_in_chroma"] is True
        assert res["content_length"] > min_length_100
        mock_chroma.assert_called_once()

    # Verify document_file_id was linked in db
    updated_lr = db_utils.get_lease_renewal("lr_101")
    assert updated_lr is not None
    assert updated_lr["document_file_id"] == res["file_id"]

    # Verify document sources row was written
    source = db_utils.get_document_source(res["file_id"])
    assert source is not None
    assert "RESIDENTIAL LEASE RENEWAL AGREEMENT" in source["source_text"]

    # Test Chroma exception fallback
    with patch(
        "api.lease_renewals.reindex_chunks_in_chroma",
        side_effect=RuntimeError("Chroma down"),
    ):
        res_fail = lease_renewals.publish_lease_renewal_document("lr_102")
        assert res_fail["indexed_in_chroma"] is False
        assert res_fail["file_id"] > 0

    # Error on unknown renewal
    with pytest.raises(ValueError, match="not found"):
        lease_renewals.publish_lease_renewal_document("missing_renewal_999")

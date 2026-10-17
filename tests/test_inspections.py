"""Unit tests for Unit Inspection Report Synthesis and RAG Publishing Engine."""

from unittest.mock import patch

import pytest
from api import db_utils, inspections
from tests.test_db_utils import initialize_temp_db


def test_generate_inspection_report_markdown(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    # 1. Error on unknown inspection
    with pytest.raises(ValueError, match="not found"):
        inspections.generate_inspection_report_markdown("non_existent_id")

    # 2. Generate markdown for seeded insp_101 (move_in)
    md_101 = inspections.generate_inspection_report_markdown("insp_101")
    assert "RESIDENTIAL UNIT CONDITION & INSPECTION STATEMENT (MOVE-IN)" in md_101
    assert "Reference ID" in md_101 and "insp_101" in md_101
    assert "Inspection Status" in md_101 and "COMPLETED" in md_101
    assert "Sarah Connor" in md_101
    assert "Hardwood Flooring" in md_101
    assert "Refrigerator & Freezer" in md_101
    assert "Window Blinds" in md_101
    assert "KEY RETURN VERIFICATION" in md_101

    # 3. Generate markdown for move_out insp_103 with deductions
    md_103 = inspections.generate_inspection_report_markdown("insp_103")
    assert "STATEMENT (MOVE-OUT)" in md_103
    assert "insp_103" in md_103
    assert "Drywall" in md_103
    assert "Smoke Detector" in md_103
    assert "$150.00" in md_103
    assert "$1,850.00" in md_103
    assert "RETURNED" in md_103


def test_publish_inspection_document(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    min_length_100 = 100
    # Mock Chroma indexing
    with patch("api.inspections.reindex_chunks_in_chroma", return_value=True) as mock_chroma:
        res = inspections.publish_inspection_document("insp_101", collection="default")
        assert res["inspection_id"] == "insp_101"
        assert res["file_id"] > 0
        assert res["filename"] == "inspection_insp_101.md"
        assert res["collection"] == "default"
        assert res["indexed_in_chroma"] is True
        assert res["content_length"] > min_length_100
        mock_chroma.assert_called_once()

    # Verify document_file_id was linked in db
    updated_insp = db_utils.get_inspection("insp_101")
    assert updated_insp is not None
    assert updated_insp["document_file_id"] == res["file_id"]

    # Verify document sources row was written
    source = db_utils.get_document_source(res["file_id"])
    assert source is not None
    assert "RESIDENTIAL UNIT CONDITION & INSPECTION STATEMENT" in source["source_text"]

    # Test Chroma exception fallback
    with patch(
        "api.inspections.reindex_chunks_in_chroma",
        side_effect=RuntimeError("Chroma down"),
    ):
        res_fail = inspections.publish_inspection_document("insp_102")
        assert res_fail["indexed_in_chroma"] is False
        assert res_fail["file_id"] > 0

    # Error on unknown inspection
    with pytest.raises(ValueError, match="not found"):
        inspections.publish_inspection_document("missing_insp_999")

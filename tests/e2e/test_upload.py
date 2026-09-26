"""End-to-end document upload tests."""

import os
import tempfile
import time

import pytest
from pages import Sidebar

pytestmark = pytest.mark.e2e


def _safe_remove(path: str) -> None:
    """Remove a temp file, retrying briefly on Windows file locks."""
    for _ in range(5):
        if not os.path.exists(path):
            return
        try:
            os.remove(path)
            return
        except OSError:
            time.sleep(0.2)


async def _wait_for_doc(sidebar: Sidebar, filename: str, attempts: int = 20) -> None:
    """Poll the document list until `filename` appears."""
    for _ in range(attempts):
        docs = await sidebar.get_documents()
        if any(filename in doc for doc in docs):
            return
        await sidebar.page.wait_for_timeout(500)
    docs = await sidebar.get_documents()
    assert any(filename in doc for doc in docs)


def _make_test_file(name: str, content: str) -> str:
    path = os.path.join(tempfile.gettempdir(), name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


async def test_upload_text_file(authenticated_page):
    """Test uploading a text file through the sidebar."""
    sidebar = Sidebar(authenticated_page)
    test_file = _make_test_file("test_upload.txt", "Test document content for e2e testing.")
    try:
        await sidebar.upload_files([test_file])
        await _wait_for_doc(sidebar, "test_upload.txt")
    finally:
        _safe_remove(test_file)


async def test_upload_multiple_files(authenticated_page):
    """Test uploading multiple files at once."""
    sidebar = Sidebar(authenticated_page)
    files = [_make_test_file(f"test_multi_{i}.txt", f"Test document {i}.") for i in range(3)]
    try:
        await sidebar.upload_files(files)
        for i in range(3):
            await _wait_for_doc(sidebar, f"test_multi_{i}.txt")
    finally:
        for test_file in files:
            _safe_remove(test_file)


async def test_upload_to_collection(authenticated_page):
    """Test uploading a document to a specific collection."""
    sidebar = Sidebar(authenticated_page)
    test_file = _make_test_file("test_collection_doc.txt", "Test document for collection.")
    try:
        collection_name = "e2e-collection"
        await sidebar.upload_files([test_file], collection=collection_name)
        await _wait_for_doc(sidebar, "test_collection_doc.txt")
    finally:
        _safe_remove(test_file)

"""End-to-end document management tests."""

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


def _make_test_file(name: str, content: str) -> str:
    path = os.path.join(tempfile.gettempdir(), name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


async def test_upload_document(authenticated_page):
    """Test uploading a document through the sidebar."""
    sidebar = Sidebar(authenticated_page)
    test_file = _make_test_file("test_doc.txt", "Test document content for e2e testing.")
    try:
        await sidebar.upload_files([test_file], collection="e2e-test")
        docs = await sidebar.get_documents()
        assert isinstance(docs, list)
    finally:
        _safe_remove(test_file)


async def test_list_documents(authenticated_page):
    """Test listing documents."""
    sidebar = Sidebar(authenticated_page)
    docs = await sidebar.get_documents()
    assert isinstance(docs, list)


async def test_select_documents_for_retrieval(authenticated_page):
    """Test selecting documents for retrieval filtering."""
    sidebar = Sidebar(authenticated_page)
    docs = await sidebar.get_documents()
    if docs:
        await sidebar.select_documents_for_retrieval(docs[:1])


async def test_collection_management(authenticated_page):
    """Test reading the active collection from the sidebar."""
    sidebar = Sidebar(authenticated_page)
    collection = await sidebar.get_active_collection()
    assert isinstance(collection, str)


async def test_upload_to_new_collection(authenticated_page):
    """Test uploading a document to a new collection."""
    sidebar = Sidebar(authenticated_page)
    test_file = _make_test_file(
        "test_collection_doc.txt", "Test document for new collection."
    )
    try:
        await sidebar.upload_files([test_file], collection="e2e-collection-test")
        docs = await sidebar.get_documents()
        assert isinstance(docs, list)
    finally:
        _safe_remove(test_file)

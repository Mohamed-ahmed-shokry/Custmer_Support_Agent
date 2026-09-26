"""End-to-end document management tests."""

import pytest
from helpers import make_test_file, probe_doc_upload, safe_remove, wait_for_doc
from pages import Sidebar

pytestmark = pytest.mark.e2e


async def test_upload_document(authenticated_page, api_base_url):
    """Test uploading a document into a new collection."""
    probe_doc_upload(api_base_url)
    sidebar = Sidebar(authenticated_page)
    test_file = make_test_file("test_doc.txt", "Test document content for e2e testing.")
    try:
        await sidebar.upload_files([test_file], collection="e2e-test")
        await sidebar.select_collection("e2e-test")
        await wait_for_doc(sidebar, "test_doc.txt")
    finally:
        safe_remove(test_file)


async def test_list_documents(authenticated_page, api_base_url):
    """Test listing documents."""
    sidebar = Sidebar(authenticated_page)
    docs = await sidebar.get_documents()
    assert isinstance(docs, list)


async def test_select_documents_for_retrieval(authenticated_page, api_base_url):
    """Test selecting documents for retrieval filtering."""
    sidebar = Sidebar(authenticated_page)
    docs = await sidebar.get_documents()
    if docs:
        await sidebar.select_documents_for_retrieval(docs[:1])


async def test_collection_management(authenticated_page, api_base_url):
    """Test reading the active collection from the sidebar."""
    sidebar = Sidebar(authenticated_page)
    collection = await sidebar.get_active_collection()
    assert isinstance(collection, str)


async def test_upload_to_new_collection(authenticated_page, api_base_url):
    """Test uploading a document to a second new collection."""
    probe_doc_upload(api_base_url)
    sidebar = Sidebar(authenticated_page)
    test_file = make_test_file(
        "test_collection_doc.txt", "Test document for new collection."
    )
    try:
        await sidebar.upload_files([test_file], collection="e2e-collection-test")
        await sidebar.select_collection("e2e-collection-test")
        await wait_for_doc(sidebar, "test_collection_doc.txt")
    finally:
        safe_remove(test_file)

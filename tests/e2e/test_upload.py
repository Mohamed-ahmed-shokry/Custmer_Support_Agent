"""End-to-end document upload tests."""

import pytest
from helpers import make_test_file, probe_doc_upload, safe_remove, wait_for_doc
from pages import Sidebar

pytestmark = pytest.mark.e2e


async def test_upload_text_file(authenticated_page, api_base_url):
    """Test uploading a text file through the sidebar."""
    probe_doc_upload(api_base_url)
    sidebar = Sidebar(authenticated_page)
    test_file = make_test_file("test_upload.txt", "Test document content for e2e testing.")
    try:
        await sidebar.upload_files([test_file])
        await wait_for_doc(sidebar, "test_upload.txt")
    finally:
        safe_remove(test_file)


async def test_upload_multiple_files(authenticated_page, api_base_url):
    """Test uploading multiple files at once."""
    probe_doc_upload(api_base_url)
    sidebar = Sidebar(authenticated_page)
    files = [make_test_file(f"test_multi_{i}.txt", f"Test document {i}.") for i in range(3)]
    try:
        await sidebar.upload_files(files)
        for i in range(3):
            await wait_for_doc(sidebar, f"test_multi_{i}.txt")
    finally:
        for test_file in files:
            safe_remove(test_file)


async def test_upload_to_new_collection(authenticated_page, api_base_url):
    """Test uploading a document into a new collection."""
    probe_doc_upload(api_base_url)
    sidebar = Sidebar(authenticated_page)
    test_file = make_test_file("test_collection_doc.txt", "Test document for collection.")
    try:
        collection_name = "e2e-collection"
        await sidebar.upload_files([test_file], collection=collection_name)
        # The document list shows the ACTIVE collection, so switch to the one
        # the upload just created before asserting the file appears.
        await sidebar.select_collection(collection_name)
        await wait_for_doc(sidebar, "test_collection_doc.txt")
    finally:
        safe_remove(test_file)

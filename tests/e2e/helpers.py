"""Shared helpers for the e2e upload and document-management tests."""

import os
import tempfile
import time

import pytest
import requests
from pages import Sidebar

HTTP_OK = 200
HTTP_CONFLICT = 409

_PROBE_FILENAME = "e2e_embeddings_probe.txt"
_PROBE_CONTENT = "Embedding availability probe for the e2e test suite."
_PROBE_COLLECTION = "e2e-probe"


def make_test_file(name: str, content: str) -> str:
    """Create a temporary upload file and return its path."""
    path = os.path.join(tempfile.gettempdir(), name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


def safe_remove(path: str) -> None:
    """Remove a temp file, retrying briefly on Windows file locks."""
    for _ in range(5):
        if not os.path.exists(path):
            return
        try:
            os.remove(path)
            return
        except OSError:
            time.sleep(0.2)


async def wait_for_doc(sidebar: Sidebar, filename: str, attempts: int = 20) -> None:
    """Poll the document list until `filename` appears."""
    for _ in range(attempts):
        docs = await sidebar.get_documents()
        if any(filename in doc for doc in docs):
            return
        await sidebar.page.wait_for_timeout(500)
    docs = await sidebar.get_documents()
    assert any(filename in doc for doc in docs)


def probe_doc_upload(api_base_url: str) -> None:
    """Skip when the backend cannot index documents.

    Uploads embed through the configured provider (OpenAI by default), which
    needs a funded key; index the probe once and treat a duplicate
    (HTTP 409) as healthy so repeated runs do not keep adding files.
    """
    path = make_test_file(_PROBE_FILENAME, _PROBE_CONTENT)
    try:
        with open(path, "rb") as handle:
            response = requests.post(
                f"{api_base_url}/upload-doc",
                params={"collection": _PROBE_COLLECTION},
                files={"file": (_PROBE_FILENAME, handle, "text/plain")},
                timeout=60,
            )
    except requests.RequestException as exc:
        pytest.skip(f"backend unreachable for document upload: {exc}")
    finally:
        safe_remove(path)
    if response.status_code not in {HTTP_OK, HTTP_CONFLICT}:
        pytest.skip(f"document embeddings unavailable: HTTP {response.status_code}")

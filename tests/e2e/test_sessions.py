"""End-to-end past-session management tests.

Session tests need at least one past session on the backend to exercise the
UI; they query the API (open in dev, no API key) and skip when empty.
"""

import uuid

import pytest
import requests
from pages import SessionsPanel

pytestmark = pytest.mark.e2e


def _list_sessions(api_base_url: str) -> list[str]:
    try:
        response = requests.get(f"{api_base_url}/sessions", timeout=10)
        response.raise_for_status()
    except (requests.RequestException, ValueError):
        return []
    return [session["session_id"] for session in response.json()]


async def _has_sessions(api_base_url: str) -> bool:
    return bool(_list_sessions(api_base_url))


async def test_session_panel_lists_sessions(authenticated_page, api_base_url):
    if not await _has_sessions(api_base_url):
        pytest.skip("no past sessions on the backend")
    panel = SessionsPanel(authenticated_page)
    assert await panel.session_options()


async def test_rename_session(authenticated_page, api_base_url):
    if not await _has_sessions(api_base_url):
        pytest.skip("no past sessions on the backend")
    panel = SessionsPanel(authenticated_page)
    session_id = (await panel.session_options())[0]
    unique_label = f"e2e-{uuid.uuid4().hex[:8]}"
    await panel.rename_session(session_id, unique_label)
    labels = await panel.session_options()
    assert any(unique_label in label for label in labels)


async def test_delete_session(authenticated_page, api_base_url):
    if not await _has_sessions(api_base_url):
        pytest.skip("no past sessions on the backend")
    panel = SessionsPanel(authenticated_page)
    options = await panel.session_options()
    session_id = options[0]
    await panel.delete_session(session_id)
    labels = await panel.session_options()
    assert all(session_id not in label for label in labels)

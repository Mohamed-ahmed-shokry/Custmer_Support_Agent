"""Smoke tests that verify the Streamlit UI renders against a live backend."""

import pytest
from pages import ChatInterface, Sidebar

pytestmark = pytest.mark.e2e


async def test_ui_renders(authenticated_page):
    await authenticated_page.wait_for_selector(".stApp", state="visible", timeout=30000)
    assert await authenticated_page.title()


async def test_backend_health_shown_in_sidebar(authenticated_page):
    sidebar = Sidebar(authenticated_page)
    await authenticated_page.wait_for_load_state("networkidle")
    assert "Backend" in await sidebar.health_status.inner_text()


async def test_chat_input_available(authenticated_page):
    chat = ChatInterface(authenticated_page)
    await chat.chat_input.wait_for(state="visible", timeout=30000)

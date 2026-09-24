"""End-to-end chat flow tests.

Toggle and option tests only need a running UI. The message round-trip and
reset tests require a configured model backend, so they are gated on an API
key (or the E2E_CHAT_ENABLED flag) and skip cleanly otherwise.
"""

import os

import pytest
from pages import ChatInterface, Sidebar

pytestmark = pytest.mark.e2e

CHAT_ENABLED = bool(os.getenv("OPENAI_API_KEY") or os.getenv("E2E_CHAT_ENABLED"))

no_chat_reason = "set OPENAI_API_KEY or E2E_CHAT_ENABLED=1 to run LLM round-trip tests"


async def test_default_chat_options_enabled(authenticated_page):
    chat = ChatInterface(authenticated_page)
    await authenticated_page.wait_for_load_state("networkidle")
    assert await chat.streaming_checkbox.locator("input").is_checked()
    assert not await chat.expand_query_checkbox.locator("input").is_checked()
    assert not await chat.rerank_checkbox.locator("input").is_checked()


async def test_toggle_expand_query(authenticated_page):
    chat = ChatInterface(authenticated_page)
    await authenticated_page.wait_for_load_state("networkidle")
    await chat.toggle_expand_query(enabled=True)
    assert await chat.expand_query_checkbox.locator("input").is_checked()
    await chat.toggle_expand_query(enabled=False)
    assert not await chat.expand_query_checkbox.locator("input").is_checked()


async def test_toggle_rerank(authenticated_page):
    chat = ChatInterface(authenticated_page)
    await authenticated_page.wait_for_load_state("networkidle")
    await chat.toggle_rerank(enabled=True)
    assert await chat.rerank_checkbox.locator("input").is_checked()
    await chat.toggle_rerank(enabled=False)
    assert not await chat.rerank_checkbox.locator("input").is_checked()


async def test_toggle_retrieval_filters(authenticated_page):
    sidebar = Sidebar(authenticated_page)
    await authenticated_page.wait_for_load_state("networkidle")
    await sidebar.toggle_hybrid_search(enabled=True)
    await sidebar.toggle_cross_encoder_rerank(enabled=True)


@pytest.mark.skipif(not CHAT_ENABLED, reason=no_chat_reason)
async def test_send_message_receives_response(authenticated_page):
    chat = ChatInterface(authenticated_page)
    await authenticated_page.wait_for_load_state("networkidle")
    await chat.send_message("What can you help me with?")
    response = await chat.wait_for_response()
    assert response.strip()


@pytest.mark.skipif(not CHAT_ENABLED, reason=no_chat_reason)
async def test_reset_chat_clears_messages(authenticated_page):
    sidebar = Sidebar(authenticated_page)
    chat = ChatInterface(authenticated_page)
    await authenticated_page.wait_for_load_state("networkidle")
    await chat.send_message("hello")
    await chat.wait_for_response()
    assert await chat.get_messages()
    await sidebar.reset_chat()
    assert not await chat.get_messages()

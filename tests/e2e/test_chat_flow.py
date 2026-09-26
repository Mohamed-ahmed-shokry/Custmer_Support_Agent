"""End-to-end chat flow tests.

Toggle and option tests only need a running UI. The message round-trip and
reset tests require a configured model backend, so they are gated on an API
key (or the E2E_CHAT_ENABLED flag) and skip cleanly otherwise.
"""
import os

import pytest
import requests
from pages import ChatInterface, Sidebar

pytestmark = pytest.mark.e2e

CHAT_ENABLED = bool(os.getenv("OPENAI_API_KEY") or os.getenv("E2E_CHAT_ENABLED"))

no_chat_reason = "set OPENAI_API_KEY or E2E_CHAT_ENABLED=1 to run LLM round-trip tests"

HTTP_OK = 200


async def _preflight_model(api_base_url: str) -> None:
    """Skip the chat tests when the backend model cannot answer.

    The OpenAI key may be present but out of credits (HTTP 429) or the model
    otherwise unavailable, which would make the chat tests fail noisily.
    """
    try:
        response = requests.post(
            f"{api_base_url}/chat",
            json={"question": "Ping", "model": "gpt-4o-mini"},
            timeout=30,
        )
    except requests.RequestException as exc:
        pytest.skip(f"backend unreachable for chat: {exc}")
    if response.status_code != HTTP_OK:
        pytest.skip(f"model backend unavailable: HTTP {response.status_code}")


async def _wait_for_chat(page) -> None:
    await page.wait_for_selector(
        '[data-testid="stChatInput"] textarea', state="visible", timeout=30000
    )


async def _assert_checked(checkbox, expected: bool, attempts: int = 20) -> None:
    """Poll a widget checkbox until it reaches the expected state."""
    for _ in range(attempts):
        input_locator = checkbox.locator("input")
        if await input_locator.is_checked() == expected:
            return
        await checkbox.page.wait_for_timeout(250)
    assert await checkbox.locator("input").is_checked() == expected


async def test_default_chat_options_enabled(authenticated_page):
    await _wait_for_chat(authenticated_page)
    chat = ChatInterface(authenticated_page)
    assert await chat.streaming_checkbox.locator("input").is_checked()
    assert not await chat.expand_query_checkbox.locator("input").is_checked()
    assert not await chat.rerank_checkbox.locator("input").is_checked()


async def test_toggle_streaming(authenticated_page):
    await _wait_for_chat(authenticated_page)
    chat = ChatInterface(authenticated_page)
    await chat.toggle_streaming(enabled=False)
    await _assert_checked(chat.streaming_checkbox, expected=False)
    await chat.toggle_streaming(enabled=True)
    await _assert_checked(chat.streaming_checkbox, expected=True)


async def test_toggle_expand_query(authenticated_page):
    await _wait_for_chat(authenticated_page)
    chat = ChatInterface(authenticated_page)
    await chat.toggle_expand_query(enabled=True)
    await _assert_checked(chat.expand_query_checkbox, expected=True)
    await chat.toggle_expand_query(enabled=False)
    await _assert_checked(chat.expand_query_checkbox, expected=False)


async def test_toggle_rerank(authenticated_page):
    await _wait_for_chat(authenticated_page)
    chat = ChatInterface(authenticated_page)
    await chat.toggle_rerank(enabled=True)
    await _assert_checked(chat.rerank_checkbox, expected=True)
    await chat.toggle_rerank(enabled=False)
    await _assert_checked(chat.rerank_checkbox, expected=False)


async def test_toggle_retrieval_filters(authenticated_page):
    await _wait_for_chat(authenticated_page)
    sidebar = Sidebar(authenticated_page)
    await sidebar.toggle_hybrid_search(enabled=True)
    await sidebar.toggle_cross_encoder_rerank(enabled=True)


@pytest.mark.skipif(not CHAT_ENABLED, reason=no_chat_reason)
async def test_send_message_receives_response(authenticated_page, api_base_url):
    await _preflight_model(api_base_url)
    chat = ChatInterface(authenticated_page)
    await _wait_for_chat(authenticated_page)
    await chat.send_message("What can you help me with?")
    response = await chat.wait_for_response()
    assert response.strip()


@pytest.mark.skipif(not CHAT_ENABLED, reason=no_chat_reason)
async def test_reset_chat_clears_messages(authenticated_page, api_base_url):
    await _preflight_model(api_base_url)
    sidebar = Sidebar(authenticated_page)
    chat = ChatInterface(authenticated_page)
    await _wait_for_chat(authenticated_page)
    await chat.send_message("hello")
    await chat.wait_for_response()
    assert await chat.get_messages()
    await sidebar.reset_chat()
    assert not await chat.get_messages()

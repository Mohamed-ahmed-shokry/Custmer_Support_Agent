"""Playwright test configuration and fixtures."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

# Get the base URLs from environment or use defaults
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
UI_BASE_URL = os.getenv("UI_BASE_URL", "http://localhost:8501")


@pytest.fixture(scope="session")
async def browser() -> AsyncGenerator[Browser, None]:
    """Create a browser instance for the test session."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        yield browser
        await browser.close()


@pytest.fixture(scope="function")
async def context(browser: Browser) -> AsyncGenerator[BrowserContext, None]:
    """Create a new browser context for each test."""
    context = await browser.new_context(
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True,
    )
    yield context
    await context.close()


@pytest.fixture(scope="function")
async def page(context: BrowserContext) -> AsyncGenerator[Page, None]:
    """Create a new page for each test."""
    page = await context.new_page()
    yield page
    await page.close()


@pytest.fixture(scope="session")
def api_base_url() -> str:
    """Return the API base URL."""
    return API_BASE_URL


@pytest.fixture(scope="session")
def ui_base_url() -> str:
    """Return the UI base URL."""
    return UI_BASE_URL


@pytest.fixture(scope="function")
async def authenticated_page(page: Page, ui_base_url: str) -> Page:
    """Navigate to the UI and wait for it to load."""
    await page.goto(ui_base_url)
    await page.wait_for_load_state("networkidle")
    # Wait for Streamlit to fully load
    await page.wait_for_selector(".stApp", state="visible", timeout=30000)
    return page

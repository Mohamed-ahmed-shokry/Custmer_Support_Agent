"""Page objects for the Streamlit app."""

from __future__ import annotations

from playwright.async_api import Page, Locator
from typing import List, Optional


class BasePage:
    """Base page object with common functionality."""

    def __init__(self, page: Page):
        self.page = page

    async def wait_for_load(self) -> None:
        """Wait for the page to fully load."""
        await self.page.wait_for_load_state("networkidle")
        await self.page.wait_for_selector(".stApp", state="visible", timeout=30000)


class Sidebar:
    """Sidebar component with all sidebar interactions."""

    def __init__(self, page: Page):
        self.page = page

    @property
    def sidebar(self) -> Locator:
        """Get the sidebar container."""
        return self.page.locator('[data-testid="stSidebar"]')

    @property
    def health_status(self) -> Locator:
        """Get the health status element."""
        return self.sidebar.locator('[data-testid="stSidebarContent"] >> text="Backend"')

    async def reset_chat(self) -> None:
        """Click the Reset Chat button."""
        await self.sidebar.get_by_role("button", name="Reset Chat").click()
        await self.page.wait_for_timeout(500)

    async def select_model(self, model: str) -> None:
        """Select a model from the dropdown."""
        await self.sidebar.locator('[data-testid="stSelectbox"]').filter(has_text="Select Model").click()
        await self.page.get_by_role("option", name=model).click()

    async def get_active_collection(self) -> str:
        """Get the currently active collection."""
        collection_picker = self.sidebar.locator('[data-testid="stSelectbox"]').filter(has_text="Active collection")
        return await collection_picker.locator('[data-testid="stSelectbox"]').inner_text()

    async def select_collection(self, collection: str) -> None:
        """Select a collection from the picker."""
        picker = self.sidebar.locator('[data-testid="stSelectbox"]').filter(has_text="Active collection")
        await picker.click()
        await self.page.get_by_role("option", name=collection).click()

    async def upload_files(self, file_paths: list[str], collection: Optional[str] = None) -> None:
        """Upload files through the sidebar."""
        file_input = self.sidebar.locator('[data-testid="stFileUploader"] input[type="file"]')
        await file_input.set_input_files(file_paths)

        if collection:
            collection_input = self.sidebar.locator('[data-testid="stTextInput"]').filter(has_text="New collection")
            await collection_input.fill(collection)

        await self.sidebar.get_by_role("button", name="Upload").click()
        await self.page.wait_for_load_state("networkidle")

    async def get_documents(self) -> List[str]:
        """Get list of uploaded document filenames."""
        docs = []
        doc_elements = await self.sidebar.locator('[data-testid="stMarkdown"]').filter(has_text="ID:").all()
        for elem in doc_elements:
            text = await elem.inner_text()
            if "**" in text:
                filename = text.split("**")[1].split("**")[0]
                docs.append(filename)
        return docs

    async def select_documents_for_retrieval(self, doc_names: List[str]) -> None:
        """Select documents for retrieval filtering."""
        multiselect = self.sidebar.locator('[data-testid="stMultiSelect"]').filter(has_text="Restrict to document")
        await multiselect.click()
        for name in doc_names:
            await self.page.get_by_role("option", name=name).click()
        await self.page.keyboard.press("Escape")

    async def toggle_hybrid_search(self, enabled: bool = True) -> None:
        """Toggle hybrid search checkbox."""
        checkbox = self.sidebar.locator('[data-testid="stCheckbox"]').filter(has_text="Hybrid search")
        is_checked = await checkbox.locator("input").is_checked()
        if is_checked != enabled:
            await checkbox.click()

    async def toggle_cross_encoder_rerank(self, enabled: bool = True) -> None:
        """Toggle cross-encoder rerank checkbox."""
        checkbox = self.sidebar.locator('[data-testid="stCheckbox"]').filter(has_text="Cross-encoder rerank")
        is_checked = await checkbox.locator("input").is_checked()
        if is_checked != enabled:
            await checkbox.click()


class ChatInterface:
    """Chat interface component."""

    def __init__(self, page: Page):
        self.page = page

    @property
    def chat_container(self) -> Locator:
        """Get the chat message container."""
        return self.page.locator('[data-testid="stChatMessageContainer"]')

    @property
    def chat_input(self) -> Locator:
        """Get the chat input field."""
        return self.page.locator('[data-testid="stChatInput"] textarea')

    @property
    def streaming_checkbox(self) -> Locator:
        """Get the streaming toggle checkbox."""
        return self.page.locator('[data-testid="stCheckbox"]').filter(has_text="Use Streaming")

    @property
    def expand_query_checkbox(self) -> Locator:
        """Get the expand query checkbox."""
        return self.page.locator('[data-testid="stCheckbox"]').filter(has_text="Expand query")

    @property
    def rerank_checkbox(self) -> Locator:
        """Get the rerank checkbox."""
        return self.page.locator('[data-testid="stCheckbox"]').filter(has_text="Rerank results")

    async def send_message(self, message: str) -> None:
        """Send a message through the chat interface."""
        await self.chat_input.fill(message)
        await self.chat_input.press("Enter")
        await self.page.wait_for_load_state("networkidle")

    async def wait_for_response(self) -> str:
        """Wait for the assistant response and return it."""
        # Wait for the assistant message to appear
        await self.page.wait_for_selector('[data-testid="stChatMessage"]:has-text("assistant")', timeout=60000)
        messages = await self.chat_container.locator('[data-testid="stChatMessage"]').all()
        if messages:
            return await messages[-1].inner_text()
        return ""

    async def toggle_streaming(self, enabled: bool = True) -> None:
        """Toggle streaming mode."""
        checkbox = self.streaming_checkbox
        is_checked = await checkbox.locator("input").is_checked()
        if is_checked != enabled:
            await checkbox.click()

    async def toggle_expand_query(self, enabled: bool = True) -> None:
        """Toggle expand query."""
        checkbox = self.expand_query_checkbox
        is_checked = await checkbox.locator("input").is_checked()
        if is_checked != enabled:
            await checkbox.click()

    async def toggle_rerank(self, enabled: bool = True) -> None:
        """Toggle rerank."""
        checkbox = self.rerank_checkbox
        is_checked = await checkbox.locator("input").is_checked()
        if is_checked != enabled:
            await checkbox.click()

    async def get_messages(self) -> List[dict]:
        """Get all messages in the chat."""
        messages = []
        elements = await self.chat_container.locator('[data-testid="stChatMessage"]').all()
        for elem in elements:
            role = "assistant" if "assistant" in await elem.get_attribute("data-testid") else "user"
            text = await elem.inner_text()
            messages.append({"role": role, "content": text})
        return messages


class SessionsPanel:
    """Past sessions panel in the sidebar."""

    def __init__(self, page: Page):
        self.page = page
        self.sidebar = Sidebar(page)

    async def open_session(self, session_id: str) -> None:
        """Open a past session by ID."""
        picker = self.sidebar.sidebar.locator('[data-testid="stSelectbox"]').filter(has_text="Open a session")
        await picker.click()
        await self.page.get_by_role("option", name=session_id).click()

    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        await self.open_session(session_id)
        await self.sidebar.sidebar.get_by_role(

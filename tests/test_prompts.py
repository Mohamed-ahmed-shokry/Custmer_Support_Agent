"""Prompt regression tests.

These read the prompt source as text instead of importing
``api.langchain_utils`` because the pinned ``langchain 0.3.x`` package fails
to import on Python 3.14 (see docs/adr/001-lazy-langchain-imports.md). The
assertions still guard the prompt invariants that shape every answer.
"""

from pathlib import Path

PROMPT_SOURCE = (
    Path(__file__).resolve().parent.parent / "api" / "langchain_utils.py"
).read_text(encoding="utf-8")

FALLBACK_MESSAGE = "I'm sorry, I couldn't find the information you're looking for"
CONTACT_EMAIL = "louisaghali@ghalirealty.com"


def test_prompt_requires_grounded_answers():
    assert "based solely on the retrieved" in PROMPT_SOURCE


def test_prompt_defines_unavailable_information_fallback():
    assert FALLBACK_MESSAGE in PROMPT_SOURCE


def test_prompt_includes_support_contact_details():
    assert CONTACT_EMAIL in PROMPT_SOURCE
    assert "407-776-4149" in PROMPT_SOURCE


def test_prompt_enforces_data_privacy():
    assert "Do not share personal information" in PROMPT_SOURCE


def test_qa_prompt_wires_context_and_history():
    assert "{context}" in PROMPT_SOURCE
    assert "chat_history" in PROMPT_SOURCE
    assert "{input}" in PROMPT_SOURCE

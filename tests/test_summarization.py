"""Unit tests for conversation summarization, sentiment detection, and tag suggestions."""

from unittest.mock import MagicMock

from api.summarization import (
    _truncate_snippet,
    detect_sentiment,
    suggest_tags,
    summarize_dialogue,
)


def test_detect_sentiment():
    assert detect_sentiment("Thank you so much! This was awesome, excellent and very helpful.") == (
        "positive"
    )
    assert detect_sentiment("I am extremely unhappy, this is broken and a terrible issue.") == (
        "negative"
    )
    assert detect_sentiment("What is the standard lease term?") == "neutral"
    assert detect_sentiment("") == "neutral"
    assert detect_sentiment("   ") == "neutral"


def test_suggest_tags():
    tags = suggest_tags("Can you review my lease contract agreement and monthly rent invoice?")
    assert "lease" in tags
    assert "agreement" in tags
    assert "billing" in tags

    maintenance_tags = suggest_tags("There is an urgent leak in the plumbing.")
    assert "maintenance" in maintenance_tags
    assert "escalation" in maintenance_tags

    empty_tags = suggest_tags("The quick brown fox jumps over the lazy dog.")
    assert empty_tags == []


def test_truncate_snippet():
    assert _truncate_snippet("Short text", max_chars=50) == "Short text"
    long_text = "A" * 100
    max_len = 20
    truncated = _truncate_snippet(long_text, max_chars=max_len)
    assert len(truncated) <= max_len
    assert truncated.endswith("…")


def test_summarize_dialogue_empty_messages():
    result = summarize_dialogue([])
    assert result["summary"] == "No conversation messages recorded."
    assert result["key_points"] == []
    assert result["sentiment"] == "neutral"
    assert result["suggested_tags"] == []


def test_summarize_dialogue_single_turn():
    messages = [
        {"role": "human", "content": "How do I terminate my corporate lease agreement early?"},
        {
            "role": "ai",
            "content": (
                "Early termination requires a 30-day written notice and "
                "payment of one month rent fee."
            ),
        },
    ]
    result = summarize_dialogue(messages)

    assert "terminate my corporate lease agreement" in result["summary"]
    assert "30-day written notice" in result["summary"]
    expected_min_points = 2
    assert len(result["key_points"]) >= expected_min_points
    assert any("Customer inquiry:" in pt for pt in result["key_points"])
    assert any("Support response:" in pt for pt in result["key_points"])
    assert "lease" in result["suggested_tags"]
    assert "agreement" in result["suggested_tags"]


def test_summarize_dialogue_multi_turn_with_sentiment():
    messages = [
        {
            "role": "human",
            "content": "I am having a terrible issue with an unexpected billing fee.",
        },
        {"role": "ai", "content": "I apologize for the confusion. Let me check your invoice."},
        {"role": "human", "content": "Thank you, I appreciate you resolving this quickly!"},
        {"role": "ai", "content": "The fee has been refunded in full to your account."},
    ]
    result = summarize_dialogue(messages)

    expected_min_points = 4
    assert len(result["key_points"]) >= expected_min_points
    assert any("Follow-up query:" in pt for pt in result["key_points"])
    assert any("Resolution details:" in pt for pt in result["key_points"])
    assert "billing" in result["suggested_tags"]
    assert result["sentiment"] in {"positive", "negative", "neutral"}


def test_summarize_dialogue_human_only_and_ai_only():
    human_only = [{"role": "human", "content": "Need help with apartment maintenance."}]
    res_human = summarize_dialogue(human_only)
    assert "Awaiting response" in res_human["summary"]
    assert "maintenance" in res_human["suggested_tags"]

    ai_only = [{"role": "ai", "content": "Support system is currently online."}]
    res_ai = summarize_dialogue(ai_only)
    assert "Support message:" in res_ai["summary"]


def test_summarize_dialogue_with_mock_llm():
    messages = [
        {"role": "human", "content": "What is the pet policy for the lease?"},
        {"role": "ai", "content": "Pets up to 25 pounds are allowed with a deposit."},
    ]
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "Customer asked about pet policy. Support confirmed 25-pound limit."
    mock_llm.invoke.return_value = mock_response

    result = summarize_dialogue(messages, llm=mock_llm)
    assert result["summary"] == "Customer asked about pet policy. Support confirmed 25-pound limit."
    assert "lease" in result["suggested_tags"]
    assert "policy" in result["suggested_tags"]
    mock_llm.invoke.assert_called_once()


def test_summarize_dialogue_llm_failure_falls_back():
    messages = [
        {"role": "human", "content": "Can I sublease my apartment?"},
        {"role": "ai", "content": "Subleasing is permitted with landlord approval."},
    ]
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = RuntimeError("OpenAI rate limit or timeout")

    result = summarize_dialogue(messages, llm=mock_llm)
    # Extractive summary is returned despite LLM failure
    assert "sublease" in result["summary"].lower()
    assert "lease" in result["suggested_tags"]

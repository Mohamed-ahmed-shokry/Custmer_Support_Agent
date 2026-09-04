from api.pii import redact_pii


def test_redact_pii_masks_email():
    assert redact_pii("contact louisaghali@ghalirealty.com today") == (
        "contact [REDACTED_EMAIL] today"
    )


def test_redact_pii_masks_phone_formats():
    assert redact_pii("call 407-776-4149") == "call [REDACTED_PHONE]"
    assert redact_pii("call (407) 776-4149") == "call [REDACTED_PHONE]"
    assert redact_pii("call +1 407.776.4149") == "call [REDACTED_PHONE]"


def test_redact_pii_masks_ssn():
    assert redact_pii("ssn 123-45-6789 here") == "ssn [REDACTED_SSN] here"


def test_redact_pii_leaves_plain_text_untouched():
    text = "How do I request maintenance for the Orlando property?"
    assert redact_pii(text) == text

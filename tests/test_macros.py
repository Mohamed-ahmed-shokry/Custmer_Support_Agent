"""Unit tests for the macro template rendering engine."""

from api.macros import (
    DEFAULT_SUPPORT_CONTACT,
    extract_template_variables,
    get_system_defaults,
    render_template,
)


def test_extract_template_variables_empty_and_none():
    assert extract_template_variables("") == []
    assert extract_template_variables("No variables here.") == []


def test_extract_template_variables_dedup_and_sort():
    template = "Hello {customer_name}, unit {unit_id} has issue. Contact {customer_name}."
    variables = extract_template_variables(template)
    assert variables == ["customer_name", "unit_id"]


def test_get_system_defaults():
    defaults = get_system_defaults()
    assert "date" in defaults
    assert "current_time" in defaults
    assert defaults["support_contact"] == DEFAULT_SUPPORT_CONTACT
    assert defaults["agent_name"] == "Support Agent"
    assert defaults["customer_name"] == "Valued Resident"


def test_render_template_with_exact_variables():
    template = "Hello {customer_name}, unit {unit_id} rent is ${amount}."
    vars_dict = {
        "customer_name": "Alice Smith",
        "unit_id": "4B",
        "amount": "1,450",
    }
    rendered, unresolved = render_template(template, vars_dict)
    assert rendered == "Hello Alice Smith, unit 4B rent is $1,450."
    assert unresolved == []


def test_render_template_with_system_defaults():
    template = "Dear {customer_name}, please call {support_contact} on {date}."
    rendered, unresolved = render_template(template, variables={"customer_name": "Bob"})
    assert "Dear Bob, please call " in rendered
    assert DEFAULT_SUPPORT_CONTACT in rendered
    assert unresolved == []


def test_render_template_without_defaults_leaves_unresolved():
    template = "Hello {customer_name}, unit {unit_id}, date {date}."
    rendered, unresolved = render_template(
        template,
        variables={"customer_name": "Charlie"},
        fallback_defaults=False,
    )
    assert rendered == "Hello Charlie, unit {unit_id}, date {date}."
    assert unresolved == ["date", "unit_id"]


def test_render_template_safe_with_special_characters():
    template = "Note: {note} / Formula: {formula}"
    vars_dict = {
        "note": "Braces {like_this} and backslashes \\ test",
        "formula": "x = {y + z}",
    }
    rendered, unresolved = render_template(template, vars_dict)
    assert "Braces {like_this} and backslashes \\ test" in rendered
    assert "x = {y + z}" in rendered
    assert unresolved == []


def test_render_template_empty_string():
    rendered, unresolved = render_template("")
    assert rendered == ""
    assert unresolved == []

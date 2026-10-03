"""Macro template rendering engine for support canned responses.

Provides variable extraction, default placeholder resolution, and safe
string substitution for property management and customer support workflows.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

# Pattern matching variable placeholders like {customer_name}, {unit_id}
_VARIABLE_PATTERN = re.compile(r"\{([a-zA-Z0-9_]+)\}")

DEFAULT_SUPPORT_CONTACT = "+1 (800) 555-0199 / support@propertymanager.com"
DEFAULT_SYSTEM_VARIABLES: dict[str, str] = {
    "agent_name": "Support Agent",
    "customer_name": "Valued Resident",
    "unit_id": "Your Unit",
    "support_contact": DEFAULT_SUPPORT_CONTACT,
}


def extract_template_variables(template: str) -> list[str]:
    """Extract all unique variable names enclosed in braces from a template string.

    Args:
        template: Template string containing placeholders like ``{customer_name}``.

    Returns:
        Sorted list of unique variable names found in the template.
    """
    if not template:
        return []
    matches = _VARIABLE_PATTERN.findall(template)
    return sorted(set(matches))


def get_system_defaults() -> dict[str, str]:
    """Return dynamic system default variables including current date and time."""
    now = datetime.now(UTC)
    return {
        **DEFAULT_SYSTEM_VARIABLES,
        "date": now.strftime("%Y-%m-%d"),
        "current_time": now.strftime("%H:%M:%S UTC"),
    }


def render_template(
    template: str,
    variables: dict[str, Any] | None = None,
    fallback_defaults: bool = True,
) -> tuple[str, list[str]]:
    """Render a macro template by safely replacing variable placeholders.

    Args:
        template: Raw macro template text.
        variables: Key-value mapping of custom variable substitutions.
        fallback_defaults: When True, fills known standard placeholders
            (e.g., date, support_contact, customer_name) with sensible defaults.

    Returns:
        A tuple of ``(rendered_text, unresolved_variables)`` where
        ``unresolved_variables`` lists placeholders that had no supplied value.
    """
    if not template:
        return "", []

    merged_vars: dict[str, str] = {}
    if fallback_defaults:
        merged_vars.update(get_system_defaults())

    if variables:
        for k, v in variables.items():
            if v is not None:
                merged_vars[str(k).strip()] = str(v)

    unresolved: list[str] = []

    def _replace_match(match: re.Match[str]) -> str:
        var_name = match.group(1)
        if var_name in merged_vars:
            return merged_vars[var_name]
        unresolved.append(var_name)
        return match.group(0)

    rendered = _VARIABLE_PATTERN.sub(_replace_match, template)
    return rendered, sorted(set(unresolved))

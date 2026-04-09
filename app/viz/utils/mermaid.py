"""Mermaid sanitization helpers.

Mermaid's gantt and flowchart parsers choke on unescaped colons, quotes,
angle brackets, and unmatched parentheses in free-form labels. These helpers
produce labels that are guaranteed to parse.
"""

from __future__ import annotations

import re

__all__ = ["safe_label", "is_valid_iso_date"]

# Characters Mermaid treats as syntax in label positions. Strip them.
_MERMAID_FORBIDDEN = re.compile(r'[:"<>()\[\]{};]')

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def safe_label(value: object, max_length: int = 50) -> str:
    """Produce a Mermaid-safe label from any input.

    - Coerces to str
    - Strips characters that Mermaid uses as syntax (``:"<>()[]{};``)
    - Collapses whitespace
    - Truncates to ``max_length`` chars (default 50)
    - Returns ``"(untitled)"`` if the result is empty
    """
    if value is None:
        return "(untitled)"
    text = str(value)
    text = _MERMAID_FORBIDDEN.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "(untitled)"
    if len(text) > max_length:
        text = text[: max_length - 1].rstrip() + "…"
    return text


def is_valid_iso_date(value: object) -> bool:
    """Return True if `value` is a YYYY-MM-DD date string Mermaid's gantt
    parser will accept."""
    if not isinstance(value, str):
        return False
    return bool(_ISO_DATE.match(value))

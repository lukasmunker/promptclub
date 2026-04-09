"""HTML sanitization helpers for app.viz HTML recipes.

The Tailwind Play CDN preloaded in LibreChat's `text/html` artifact sandbox
accepts arbitrary utility classes, so we build HTML as plain strings. All
user-interpolated values MUST pass through `escape_html()` to prevent XSS —
the artifact runs in a sandbox but we don't rely on the sandbox for safety.
"""

from __future__ import annotations

import html as _html
import re

__all__ = ["escape_html", "strip_dangerous_html", "assert_safe_html"]


def escape_html(value: object) -> str:
    """HTML-escape any value. Accepts non-str inputs for convenience (numbers,
    dates, etc.) and coerces them to ``str()`` first."""
    if value is None:
        return ""
    return _html.escape(str(value), quote=True)


# Patterns we actively strip from any raw HTML that leaks through. These are
# defensive — recipes should never generate these in the first place.
_DANGEROUS_PATTERNS = [
    # Inline scripts
    re.compile(r"<\s*script\b[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<\s*script\b[^>]*/?>", re.IGNORECASE),
    # Iframes, objects, embeds
    re.compile(r"<\s*iframe\b[^>]*>.*?<\s*/\s*iframe\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<\s*(object|embed|applet)\b[^>]*>", re.IGNORECASE),
    # Inline event handlers (onclick=, onload=, etc.)
    re.compile(r"\s+on[a-z]+\s*=\s*\"[^\"]*\"", re.IGNORECASE),
    re.compile(r"\s+on[a-z]+\s*=\s*'[^']*'", re.IGNORECASE),
    # javascript: URLs
    re.compile(r"(href|src)\s*=\s*\"\s*javascript:[^\"]*\"", re.IGNORECASE),
    re.compile(r"(href|src)\s*=\s*'\s*javascript:[^']*'", re.IGNORECASE),
]


def strip_dangerous_html(body: str) -> str:
    """Strip known-dangerous constructs from an HTML string. Defensive last
    resort — recipes should never emit these."""
    for pattern in _DANGEROUS_PATTERNS:
        body = pattern.sub("", body)
    return body


def assert_safe_html(body: str) -> None:
    """Raise ValueError if `body` contains constructs that are forbidden in
    our text/html artifacts. Used by tests and the build pipeline as a final
    compliance check."""
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(body):
            raise ValueError(
                f"HTML body contains forbidden pattern: {pattern.pattern!r}"
            )

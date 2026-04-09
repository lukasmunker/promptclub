"""Shared utilities for app.viz recipes."""

from app.viz.utils.html import escape_html, strip_dangerous_html
from app.viz.utils.identifiers import make_identifier, slug, today_iso
from app.viz.utils.mermaid import safe_label

__all__ = [
    "escape_html",
    "strip_dangerous_html",
    "make_identifier",
    "slug",
    "today_iso",
    "safe_label",
]

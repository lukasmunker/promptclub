"""Shared utilities for app.viz recipes."""

from app.viz.utils.citations import (
    format_source_footer,
    format_source_footer_text,
    group_sources_by_kind,
)
from app.viz.utils.emoji import (
    format_phase,
    format_status,
    phase_emoji,
    source_emoji,
    status_emoji,
)
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
    "format_source_footer",
    "format_source_footer_text",
    "group_sources_by_kind",
    "format_phase",
    "format_status",
    "phase_emoji",
    "source_emoji",
    "status_emoji",
]

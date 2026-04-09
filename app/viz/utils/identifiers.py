"""Identifier helpers: slugs, dates, deterministic artifact IDs."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

__all__ = ["slug", "today_iso", "make_identifier"]

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slug(value: object, max_length: int = 40) -> str:
    """Lowercase, hyphenated, ASCII-safe slug for identifiers and URLs.

    Examples:
        >>> slug("Phase 3 Melanoma Trials")
        'phase-3-melanoma-trials'
        >>> slug("NSCLC / NSCLC-adeno")
        'nsclc-nsclc-adeno'
        >>> slug("")
        'untitled'
    """
    if value is None:
        return "untitled"
    text = str(value).lower()
    text = _SLUG_STRIP.sub("-", text).strip("-")
    if not text:
        return "untitled"
    if len(text) > max_length:
        text = text[:max_length].rstrip("-")
    return text


def today_iso(clock: datetime | None = None) -> str:
    """Return today's date as ``YYYY-MM-DD`` in UTC. The optional `clock`
    argument is a seam for deterministic tests."""
    now = clock or datetime.now(timezone.utc)
    return now.date().isoformat()


def make_identifier(
    recipe: str,
    query: object,
    clock: datetime | None = None,
) -> str:
    """Build a deterministic artifact identifier for a response.

    Format: ``<recipe>-<query-slug>-<YYYY-MM-DD>``

    Examples:
        >>> make_identifier("trial_search_results", "melanoma phase 3",
        ...                 clock=datetime(2026, 4, 9, tzinfo=timezone.utc))
        'trial_search_results-melanoma-phase-3-2026-04-09'
    """
    return f"{recipe}-{slug(query)}-{today_iso(clock)}"

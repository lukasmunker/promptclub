"""Source-attribution footer helpers.

Every pharmafuse-mcp viz recipe embeds a 1-line citation footer directly into its
rendered output so viewers see "where did this data come from?" inline with
the visualization itself — independent of whatever the LLM adds in
surrounding prose. This supports the [Company] challenge's "Source citation
and transparency" bonus-point criterion.

The helpers here are deliberately format-agnostic: they take a list of
``Source`` objects (or equivalent dicts) and return either a markdown string
(for the 5 inline recipes) or a structured dict useful for building React
BlueprintNodes (for the 2 artifact-side-pane recipes).
"""

from __future__ import annotations

from typing import Any, Iterable

__all__ = [
    "format_source_footer",
    "format_source_footer_text",
    "group_sources_by_kind",
]


# Display names for each SourceKind literal. Anything not in this map falls
# back to the raw kind string.
_DISPLAY_NAMES: dict[str, str] = {
    "clinicaltrials.gov": "ClinicalTrials.gov",
    "pubmed": "PubMed",
    "openfda": "openFDA",
    "opentargets": "Open Targets",
    "web": "Web",
}

# Canonical "hub" URL per source kind — used as the link target when we have
# multiple citations of that kind and want to link to the source *site*, not
# to an individual record.
_HUB_URLS: dict[str, str] = {
    "clinicaltrials.gov": "https://clinicaltrials.gov",
    "pubmed": "https://pubmed.ncbi.nlm.nih.gov",
    "openfda": "https://open.fda.gov",
    "opentargets": "https://platform.opentargets.org",
    "web": "",
}


def group_sources_by_kind(
    sources: Iterable[Any] | None,
) -> dict[str, int]:
    """Count sources per kind, returning a dict ordered by count desc.

    Accepts a mix of ``Source`` Pydantic models and plain dicts.
    """
    if not sources:
        return {}
    counts: dict[str, int] = {}
    for s in sources:
        kind = _get(s, "kind", "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    # Sort by count desc, then alphabetically
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def format_source_footer_text(
    sources: Iterable[Any] | None,
) -> str:
    """Plain-text footer (no markdown emphasis), suitable for React
    ``BlueprintNode(component="p", text=...)``.

    Example:
        'Source: ClinicalTrials.gov (8) · PubMed (3) · Retrieved 2026-04-09'
    """
    if not sources:
        return ""
    sources_list = list(sources)
    if not sources_list:
        return ""

    counts = group_sources_by_kind(sources_list)
    parts: list[str] = []
    for kind, count in counts.items():
        display = _DISPLAY_NAMES.get(kind, kind)
        if count > 1:
            parts.append(f"{display} ({count})")
        else:
            parts.append(display)

    retrieved = _most_recent_date(sources_list)
    source_list = " · ".join(parts)

    if retrieved:
        return f"Source: {source_list} · Retrieved {retrieved}"
    return f"Source: {source_list}"


def format_source_footer(
    sources: Iterable[Any] | None,
) -> str:
    """Markdown footer for the 5 inline recipes.

    Renders as an italicized line with hub-URL links for each source kind.

    Example output::

        \\n_Source: [ClinicalTrials.gov](https://clinicaltrials.gov) (8) ·
        [PubMed](https://pubmed.ncbi.nlm.nih.gov) (3) · Retrieved 2026-04-09_\\n

    Returns an empty string when ``sources`` is None or empty so recipes can
    append the result unconditionally without inserting spurious whitespace.
    """
    if not sources:
        return ""
    sources_list = list(sources)
    if not sources_list:
        return ""

    counts = group_sources_by_kind(sources_list)
    parts: list[str] = []
    for kind, count in counts.items():
        display = _DISPLAY_NAMES.get(kind, kind)
        hub = _HUB_URLS.get(kind, "")
        if hub:
            linked = f"[{display}]({hub})"
        else:
            linked = display
        if count > 1:
            parts.append(f"{linked} ({count})")
        else:
            parts.append(linked)

    retrieved = _most_recent_date(sources_list)
    source_list = " · ".join(parts)

    if retrieved:
        return f"\n_Source: {source_list} · Retrieved {retrieved}_\n"
    return f"\n_Source: {source_list}_\n"


# --- Internals --------------------------------------------------------------


def _get(obj: Any, attr: str, default: Any = None) -> Any:
    """Read a key from either a Pydantic model or a dict."""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _most_recent_date(sources: list[Any]) -> str:
    """Return the YYYY-MM-DD portion of the most recent ``retrieved_at``, or
    an empty string if none of the sources have one."""
    dates: list[str] = []
    for s in sources:
        value = _get(s, "retrieved_at")
        if value is None:
            continue
        # Pydantic Source models use datetime; serialized dicts use ISO strings.
        if hasattr(value, "isoformat"):
            iso = value.isoformat()
        else:
            iso = str(value)
        dates.append(iso)

    if not dates:
        return ""
    # ISO 8601 strings sort lexicographically into chronological order
    latest = max(dates)
    # Take just the date portion (first 10 chars of YYYY-MM-DDTHH:MM:SS...)
    return latest[:10]

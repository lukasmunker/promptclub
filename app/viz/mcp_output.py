"""Convert an envelope dict into LLM-ready text for MCP tool returns.

Previously the MCP tools in app.main returned the envelope dict directly —
FastMCP serialized it to JSON, and the LLM had to parse that JSON, find
``ui.raw``, construct a ``:::artifact{…}:::`` block, and paste it. In
practice the LLM frequently skipped the transformation and wrote its own
prose summary into the artifact pane instead (see user bug report April
2026 where a three-trial comparison came back as a hand-written markdown
report instead of the pre-rendered HTML cards).

This module flips the responsibility: the server pre-assembles the
``:::artifact{…}:::`` directive with ``ui.raw`` as its body and returns it
as plain text. The LLM reads the tool result as "the thing to paste" and
just includes it in its reply, optionally adding a few sentences of
commentary afterwards. No JSON parsing needed.

Three envelope shapes are supported:

- **Full visualization envelope** ``{render_hint, ui, data, sources, …}``
  → text starts with the ``:::artifact`` directive, followed by a
  one-line ``Sources:`` footer.

- **Text-only envelope** ``{render_hint, data, sources}`` (SKIP path)
  → a short ``[NO VISUALIZATION]`` notice followed by a compact JSON dump
  of ``data`` and the sources footer.

- **Legacy "no data" shortcircuit dict** from
  ``app.main._maybe_no_data()`` → a ``[NO DATA AVAILABLE]`` notice
  echoing the source and query, plus the ``do_not_supplement`` guardrail.

Every variant ends with a single compliance reminder so the LLM cannot
lose track of the "cite sources / no forward-looking" rules.
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["envelope_to_llm_text"]


# Cap the sources footer length — the full citation list can be many
# dozens of entries, but the LLM only needs a handful for its commentary.
# The ``sources`` field is still there in the data blob for the SKIP path.
_MAX_SOURCES_IN_FOOTER = 10

# Cap the JSON dump in the SKIP path so a verbose tool response doesn't
# blow past the LLM context window.
_MAX_DATA_DUMP_CHARS = 3000


def envelope_to_llm_text(envelope: dict[str, Any]) -> str:
    """Render an envelope dict as the text payload an MCP tool should return.

    This is the single entrypoint every ``@mcp.tool()`` function in
    ``app.main`` calls as the last step before ``return``.

    Args:
        envelope: Either a visualization envelope from
            ``app.viz.build.build_response`` /
            ``app.viz.adapters.build_response_from_promptclub`` (with the
            ``attach_citation_layer`` extras), or the legacy "no data"
            dict from ``app.main._maybe_no_data``.

    Returns:
        A plain text string formatted for direct LLM consumption. The
        first non-metadata line is either a pre-assembled
        ``:::artifact{…}:::`` directive or a ``[NO …]`` marker.
    """
    if envelope.get("no_data"):
        return _format_no_data(envelope)

    ui = envelope.get("ui")
    sources = envelope.get("sources") or []
    data = envelope.get("data") or {}

    if ui:
        return _format_with_artifact(ui, sources)
    return _format_text_only(data, sources)


# --- Visualization path ----------------------------------------------------


def _format_with_artifact(
    ui: dict[str, Any], sources: list[dict[str, Any]]
) -> str:
    """Pre-assemble the :::artifact{…}::: block the LLM should paste."""
    artifact = ui["artifact"]
    identifier = artifact["identifier"]
    art_type = artifact["type"]
    title = _escape_attr(artifact["title"])
    raw = (ui.get("raw") or "").rstrip()

    artifact_block = (
        f':::artifact{{identifier="{identifier}" type="{art_type}" title="{title}"}}\n'
        f"{raw}\n"
        f":::"
    )

    footer = _sources_footer(sources)
    return f"{artifact_block}\n\n{footer}"


# --- Text-only / SKIP path -------------------------------------------------


def _format_text_only(
    data: dict[str, Any], sources: list[dict[str, Any]]
) -> str:
    """No-visualization path: ask the LLM to answer in plain prose."""
    data_json = json.dumps(data, indent=2, default=str, ensure_ascii=False)
    if len(data_json) > _MAX_DATA_DUMP_CHARS:
        data_json = data_json[: _MAX_DATA_DUMP_CHARS - 16] + "\n  …truncated…\n}"

    footer = _sources_footer(sources)
    return (
        "[NO VISUALIZATION — answer as plain text from the data and sources below]\n\n"
        "Data:\n"
        f"{data_json}\n\n"
        f"{footer}\n\n"
        "Compliance: Cite sources using NCT / PMID / URL. "
        "No forward-looking statements."
    )


# --- Legacy no-data path ---------------------------------------------------


def _format_no_data(envelope: dict[str, Any]) -> str:
    """Empty-result path: tell the LLM there are no records and it must not
    supplement from training knowledge."""
    source = envelope.get("source") or "unknown source"
    query = envelope.get("query") or "unknown query"
    guard = envelope.get("do_not_supplement") or (
        "Tell the user no data was found; do NOT answer from training knowledge."
    )
    return (
        "[NO DATA AVAILABLE]\n"
        f"Source: {source}\n"
        f"Query:  {query}\n\n"
        f"{guard}\n\n"
        "Compliance: Do NOT supplement from training knowledge. "
        "No forward-looking statements."
    )


# --- Helpers ---------------------------------------------------------------


def _sources_footer(sources: list[dict[str, Any]]) -> str:
    """Compact one-block citation list for the LLM's commentary section."""
    if not sources:
        return "Sources: (none returned by this tool)"
    lines = ["Sources:"]
    for s in sources[:_MAX_SOURCES_IN_FOOTER]:
        kind = s.get("kind", "?")
        sid = s.get("id", "?")
        url = s.get("url", "")
        lines.append(f"  - [{kind}] {sid} {url}".rstrip())
    extra = len(sources) - _MAX_SOURCES_IN_FOOTER
    if extra > 0:
        lines.append(f"  (+{extra} more)")
    return "\n".join(lines)


def _escape_attr(value: object) -> str:
    """Escape double quotes for safe inclusion inside an artifact attribute."""
    if value is None:
        return ""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')

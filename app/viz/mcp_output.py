"""Convert an envelope dict into LLM-ready text for MCP tool returns.

This module pre-assembles the ``:::artifact{…}:::`` directive with
``ui.raw`` as its body and returns it as plain text wrapped in an
"ACTION REQUIRED" preamble. The LLM reads the tool result as "the
thing to paste" and just includes it in its reply, optionally adding
a few sentences of commentary afterwards. No JSON parsing needed.

Coverage guarantee: every envelope produced by
``app.viz.build.build_response`` contains a populated ``ui`` field.
There is no longer a SKIP path or a ``[NO DATA AVAILABLE]``
shortcircuit — the legacy ``_format_text_only`` and ``_format_no_data``
branches have been removed.
"""

from __future__ import annotations

from typing import Any

__all__ = ["envelope_to_llm_text"]


# Cap the sources footer length — the full citation list can be many
# dozens of entries, but the LLM only needs a handful for its commentary.
_MAX_SOURCES_IN_FOOTER = 10


def envelope_to_llm_text(envelope: dict[str, Any]) -> str:
    """Render an envelope dict as the text payload an MCP tool should return.

    The envelope MUST contain a populated ``ui`` field. ``build_response``
    guarantees this; any caller bypassing ``build_response`` is a bug.
    """
    ui = envelope.get("ui")
    if ui is None:
        raise ValueError(
            "envelope_to_llm_text received an envelope without a ui field. "
            "All envelopes must come from build_response, which guarantees ui."
        )
    sources = envelope.get("sources") or []
    return _format_with_artifact(ui, sources)


# --- Visualization path ----------------------------------------------------


def _format_with_artifact(
    ui: dict[str, Any], sources: list[dict[str, Any]]
) -> str:
    """Pre-assemble the :::artifact{…}::: block the LLM should paste.

    The tool result deliberately STARTS with a one-line imperative
    telling the LLM to paste the block below verbatim. We tried system-
    prompt-level instructions ("MANDATORY: always include the artifact")
    and still saw the LLM skip the block unless the user explicitly
    asked for a visualization. Putting the instruction in-band — right
    next to the thing it should copy — gets the LLM to reliably forward
    the artifact to LibreChat's side pane.
    """
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

    # In-band instruction. The LLM sees this BEFORE the artifact block and
    # treats it as guidance-for-this-tool-result, not as content to echo.
    # Phrasing:
    #   - "ACTION REQUIRED" is a strong trigger phrase for tool-following
    #   - The explicit "paste the :::artifact block below verbatim at the
    #     start of your reply" tells it exactly what to do
    #   - "do NOT write your own visualization / do NOT skip the block"
    #     closes the two failure modes we saw in production
    preamble = (
        "ACTION REQUIRED — copy the :::artifact{…}::: block below into your "
        "reply VERBATIM, as the very first thing you write. Do not rewrite "
        "the HTML, do not paraphrase it, do not build your own alternative "
        "visualization, and do not skip the block because you think prose "
        "is enough. LibreChat only opens the side pane when the artifact "
        "directive appears in your reply, so omitting it means the user "
        "sees nothing. AFTER the artifact block you MAY add 2–5 sentences "
        "of analysis that interpret the visualization. This applies to "
        "every single tool call — the user does NOT need to ask for a "
        "visualization, it is the default whenever a tool returns one."
    )

    return f"{preamble}\n\n{artifact_block}\n\n{footer}"


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

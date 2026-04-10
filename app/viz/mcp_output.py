"""Convert an envelope dict into LLM-ready text for MCP tool returns.

Two rendering paths, both guaranteed to receive a populated ``ui`` field
(``build_response`` enforces this):

1. **Side-pane artifact path** (``html`` / ``mermaid`` artifact types):
   Pre-assembles a ``:::artifact{…}:::`` directive with ``ui.raw`` as its
   body and returns it wrapped in an "ACTION REQUIRED" preamble. The LLM
   pastes the directive into its reply and LibreChat mounts it in the
   artifact side pane.

2. **Inline-in-chat markdown path** (``markdown`` artifact type):
   Embeds ``ui.raw`` directly into the reply as a Markdown snippet — no
   ``:::artifact{…}:::`` wrapping, no side pane. Used by the compact
   fallback recipes (info / concept / single-entity cards) where opening
   the side pane for a handful of lines would be pure friction.

Both paths append:
- An optional ``## Glossary`` block from ``data.knowledge_annotations``.
- A numbered ``## References`` block from ``envelope.citation_layer``
  (attached by ``app.citations.attach_citation_layer``) with clickable
  markdown links, plus a link-reference footer so bare ``[n]`` tokens in
  the LLM's commentary auto-link. The preamble instructs the LLM to use
  these inline markers when citing.
- A legacy ``Sources:`` one-liner footer for the LLM's quick reference.
"""

from __future__ import annotations

from typing import Any

__all__ = ["envelope_to_llm_text"]


# Cap the sources footer length — the full citation list can be many
# dozens of entries, but the LLM only needs a handful for its commentary.
_MAX_SOURCES_IN_FOOTER = 10

# Caps for the in-band glossary section rendered from WS2 knowledge
# annotations. The enricher's MAX_ANNOTATIONS is 50 which is too many
# for plain text — a tight cap keeps the LLM context small.
_MAX_GLOSSARY_ENTRIES_IN_LLM_TEXT = 10
_MAX_GLOSSARY_DEFINITION_CHARS = 200

# Cap the numbered References section. LibreChat will render the first
# few dozen fine but past that the commentary section becomes unreadable.
_MAX_REFERENCES_IN_LLM_TEXT = 20


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
    artifact_type = (ui.get("artifact") or {}).get("type")
    if artifact_type == "markdown":
        return _format_inline_markdown(envelope, sources)
    return _format_with_artifact(envelope, sources)


# --- Side-pane artifact path -----------------------------------------------


def _format_with_artifact(
    envelope: dict[str, Any], sources: list[dict[str, Any]]
) -> str:
    """Pre-assemble the :::artifact{…}::: block the LLM should paste.

    The tool result deliberately STARTS with a one-line imperative
    telling the LLM to paste the block below verbatim. We tried system-
    prompt-level instructions ("MANDATORY: always include the artifact")
    and still saw the LLM skip the block unless the user explicitly
    asked for a visualization. Putting the instruction in-band — right
    next to the thing it should copy — gets the LLM to reliably forward
    the artifact to LibreChat's side pane.

    If the envelope carries ``data.knowledge_annotations`` from the WS2
    enrichment layer, we also inject a compact ``## Glossary`` section
    between the artifact block and the sources footer so the LLM has
    definitions for the oncology terms in the response. Without this
    injection, only the ``info_card`` recipe would surface annotations —
    every other recipe would silently drop them.

    If the envelope carries a ``citation_layer`` (attached upstream by
    ``app.citations.attach_citation_layer``), a numbered ``## References``
    block is emitted so the LLM can cite inline with ``[1]``, ``[2]``, …
    markers that render as clickable links in LibreChat's markdown
    renderer.
    """
    ui = envelope["ui"]
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

    # In-band instruction. The LLM sees this BEFORE the artifact block and
    # treats it as guidance-for-this-tool-result, not as content to echo.
    # Phrasing:
    #   - "ACTION REQUIRED" is a strong trigger phrase for tool-following
    #   - The explicit "paste the artifact directive block below verbatim
    #     at the start of your reply" tells it exactly what to do
    #   - "do NOT write your own visualization / do NOT skip the block"
    #     closes the two failure modes we saw in production
    #   - The final "cite sources inline with [n]" sentence is the hook
    #     that turns the bottom numbered list into clickable inline
    #     markers in the LLM's commentary.
    #
    # Implementation note: the preamble must NOT contain the literal
    # strings ``:::artifact`` or ``## References`` — substring-matching
    # tests use those tokens as uniqueness anchors to distinguish the
    # actual directive / section header from the instructional text.
    preamble = (
        "ACTION REQUIRED — copy the artifact directive block below into "
        "your reply VERBATIM, as the very first thing you write. Do not "
        "rewrite the HTML, do not paraphrase it, do not build your own "
        "alternative visualization, and do not skip the block because "
        "you think prose is enough. LibreChat only opens the side pane "
        "when the artifact directive appears in your reply, so omitting "
        "it means the user sees nothing. AFTER the directive block you "
        "MAY add 2–5 sentences of analysis that interpret the "
        "visualization. When you cite a source in that analysis, use "
        "inline numbered markers like [1], [2], [3] — they map "
        "one-for-one to the numbered references section below and "
        "render as clickable links. This applies to every single tool "
        "call — the user does NOT need to ask for a visualization, it "
        "is the default whenever a tool returns one."
    )

    glossary = _format_glossary(
        envelope.get("data", {}).get("knowledge_annotations") or []
    )
    references = _format_references(envelope.get("citation_layer") or {})
    footer = _sources_footer(sources)

    sections = [preamble, artifact_block]
    if glossary:
        sections.append(glossary)
    if references:
        sections.append(references)
    sections.append(footer)
    return "\n\n".join(sections)


# --- Inline-in-chat markdown path ------------------------------------------


def _format_inline_markdown(
    envelope: dict[str, Any], sources: list[dict[str, Any]]
) -> str:
    """Render a ``markdown`` artifact directly in the chat body.

    No ``:::artifact{…}:::`` wrapping — the body of ``ui.raw`` is passed
    through as-is and the preamble instructs the LLM to paste it inline.
    Used for compact recipes (info / concept / single-entity cards) where
    opening LibreChat's side pane for a handful of lines would be pure
    friction.

    The rest of the layout (glossary, references, sources footer) matches
    the side-pane path so the LLM sees the same citation machinery
    regardless of which recipe produced the response.
    """
    ui = envelope["ui"]
    raw = (ui.get("raw") or "").rstrip()

    # Implementation note: the preamble must NOT contain the literal
    # strings ``:::artifact`` or ``## References`` — substring-matching
    # tests use those tokens as uniqueness anchors to distinguish the
    # actual directive / section header from the instructional text.
    preamble = (
        "ACTION REQUIRED — copy the Markdown snippet below into your "
        "reply VERBATIM, embedded inline in your message body. This is "
        "an inline-in-chat visualization: do NOT wrap it in an artifact "
        "directive block, do NOT convert it to HTML, do NOT paraphrase "
        "it. The snippet is intentionally compact so it reads inline "
        "without opening the artifact side pane. AFTER the snippet you "
        "MAY add 2–5 sentences of analytical commentary. When you cite "
        "a source, use inline numbered markers like [1], [2], [3] — "
        "they map one-for-one to the numbered references section below "
        "and render as clickable links."
    )

    glossary = _format_glossary(
        envelope.get("data", {}).get("knowledge_annotations") or []
    )
    references = _format_references(envelope.get("citation_layer") or {})
    footer = _sources_footer(sources)

    sections = [preamble, raw]
    if glossary:
        sections.append(glossary)
    if references:
        sections.append(references)
    sections.append(footer)
    return "\n\n".join(sections)


# --- Helpers ---------------------------------------------------------------


def _format_glossary(annotations: list[dict[str, Any]]) -> str:
    """Render knowledge_annotations as a compact markdown glossary section.

    Deduplicates by ``lexicon_id`` (first occurrence wins), caps at
    ``_MAX_GLOSSARY_ENTRIES_IN_LLM_TEXT`` entries, and truncates each
    definition to ``_MAX_GLOSSARY_DEFINITION_CHARS`` characters. Returns
    an empty string if there are no annotations or none of them have a
    usable term + definition — callers should skip the section entirely
    in that case.
    """
    if not annotations:
        return ""

    seen: set[str] = set()
    lines: list[str] = []
    for ann in annotations:
        lid = ann.get("lexicon_id")
        if not lid or lid in seen:
            continue
        seen.add(lid)
        term = ann.get("matched_term", "")
        definition = ann.get("short_definition", "")
        if not term or not definition:
            continue
        if len(definition) > _MAX_GLOSSARY_DEFINITION_CHARS:
            definition = (
                definition[: _MAX_GLOSSARY_DEFINITION_CHARS - 1].rstrip() + "…"
            )
        lines.append(f"- **{term}** — {definition}")
        if len(lines) >= _MAX_GLOSSARY_ENTRIES_IN_LLM_TEXT:
            break

    if not lines:
        return ""

    return "## Glossary\n\n" + "\n".join(lines)


def _format_references(citation_layer: dict[str, Any]) -> str:
    """Render the attached citation_layer as a numbered References section.

    The references section is what unlocks inline clickable citation
    markers in the LLM's commentary. It renders in two blocks:

    1. A ``## References`` numbered list — one ``[n]`` per reference with
       a markdown link to the source URL. This is the human-visible list
       the LLM can paste or reference directly.

    2. A markdown link-reference footer — ``[1]: url`` / ``[2]: url``
       lines. Any bare ``[n]`` token the LLM writes in its commentary
       auto-links to the matching URL via GFM reference-style links, so
       the markers come out clickable even when the LLM writes just
       ``[1]`` instead of ``[[1]](url)``.

    Returns an empty string when there is no citation_layer, no references
    inside it, or every reference lacks a URL (nothing clickable to emit).
    """
    if not isinstance(citation_layer, dict):
        return ""
    references = citation_layer.get("references") or []
    if not references:
        return ""

    numbered_lines: list[str] = []
    link_refs: list[str] = []
    for ref in references[:_MAX_REFERENCES_IN_LLM_TEXT]:
        if not isinstance(ref, dict):
            continue
        index = ref.get("index")
        url = ref.get("url")
        label = ref.get("label") or ref.get("title") or ref.get("id") or "Source"
        source = ref.get("source") or ""
        if index is None or not url:
            continue
        # Build a rich human-facing entry: "[1] Label — Source"
        subtitle = f" — {source}" if source else ""
        numbered_lines.append(
            f"[{index}] [{label}]({url}){subtitle}"
        )
        # Link-reference footer so bare `[n]` tokens in the LLM's
        # commentary auto-link to the same URL.
        link_refs.append(f"[{index}]: {url}")

    if not numbered_lines:
        return ""

    extra = len(references) - _MAX_REFERENCES_IN_LLM_TEXT
    if extra > 0:
        numbered_lines.append(f"… (+{extra} more references)")

    # Blank line between the numbered list and the link-reference footer
    # keeps GFM happy on most renderers.
    return (
        "## References\n\n"
        + "\n".join(numbered_lines)
        + "\n\n"
        + "\n".join(link_refs)
    )


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

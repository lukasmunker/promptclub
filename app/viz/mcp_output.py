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
    #   - Citation rules give the LLM the EXACT inline-link format it
    #     should use (`[N](URL)`) plus a DO/DON'T example so it doesn't
    #     fall back to academic compound brackets like `[1, 9]` (which
    #     don't render as clickable links).
    #   - Inline-diagram guidance unlocks the "combine inline + side
    #     pane" pattern: pre-built tool artifact in the side pane plus
    #     supporting mermaid diagrams / GFM tables in the chat prose.
    #
    # Implementation note: the preamble must NOT contain the literal
    # strings ``:::artifact`` or ``## References`` — substring-matching
    # tests use those tokens as uniqueness anchors to distinguish the
    # actual directive / section header from the instructional text.
    preamble = (
        "ACTION REQUIRED — Three rules for this tool result:\n\n"
        "1) PASTE THE TOOL'S ARTIFACT. Copy the artifact directive "
        "block below into your reply VERBATIM, as the very first "
        "thing you write. Do not rewrite the HTML, do not paraphrase "
        "it, do not skip the block because you think prose is enough. "
        "LibreChat only opens the side pane when the artifact "
        "directive appears in your reply.\n\n"
        "2) CITE SOURCES AS CLICKABLE INLINE LINKS. The Sources "
        "section below lists each source as a ready-to-paste token "
        "of the form `[N](URL)`. When you cite a source in your "
        "prose, paste that exact token VERBATIM. DO write "
        "`[1](https://...)`. DON'T write bare `[1]` (no URL = not "
        "clickable). DON'T write compound markers like `[1, 9]` "
        "(the comma breaks the link). When citing two sources for "
        "one claim, write them as two separate tokens: "
        "`... [1](url1) [2](url2)`.\n\n"
        "3) ADD INLINE SUPPORTING DIAGRAMS WHERE USEFUL. After the "
        "artifact block and 2–5 sentences of analysis, you are "
        "encouraged to add inline supporting visualizations in the "
        "chat body — a ```mermaid code fence (flowchart, sequence "
        "diagram, mind map, simple chart) or a GFM table — that "
        "complement the side-pane artifact. Prefer inline markdown "
        "for supporting material because it renders directly in the "
        "chat without opening a second pane. You may also add a "
        "richer hand-written `:::artifact{…}:::` block of your own "
        "if a separate full-pane visualization genuinely adds value, "
        "but inline diagrams are the lighter-weight default for "
        "supporting context the tool's artifact doesn't already "
        "cover.\n\n"
        "This applies to every single tool call — the user does NOT "
        "need to ask for a visualization, it is the default whenever "
        "a tool returns one."
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
        "ACTION REQUIRED — Three rules for this tool result:\n\n"
        "1) PASTE THE SNIPPET INLINE. Copy the Markdown snippet below "
        "into your reply VERBATIM, embedded inline in your message "
        "body. This is an inline-in-chat visualization: do NOT wrap "
        "it in an artifact directive block, do NOT convert it to HTML, "
        "do NOT paraphrase it. The snippet is intentionally compact so "
        "it reads inline without opening the artifact side pane.\n\n"
        "2) CITE SOURCES AS CLICKABLE INLINE LINKS. The Sources "
        "section below lists each source as a ready-to-paste token of "
        "the form `[N](URL)`. When you cite a source in your prose, "
        "paste that exact token VERBATIM. DO write `[1](https://...)`. "
        "DON'T write bare `[1]` (no URL = not clickable). DON'T write "
        "compound markers like `[1, 9]` (the comma breaks the link). "
        "When citing two sources for one claim, write them as two "
        "separate tokens: `... [1](url1) [2](url2)`.\n\n"
        "3) ADD INLINE SUPPORTING DIAGRAMS WHERE USEFUL. After the "
        "snippet and 2–5 sentences of analysis, you are encouraged to "
        "add inline supporting visualizations — a ```mermaid code "
        "fence (flowchart, sequence diagram, mind map, simple chart) "
        "or a GFM table — that complement the snippet above. If a "
        "richer full-pane visualization genuinely adds value, you may "
        "also add a hand-written `:::artifact{…}:::` block of your "
        "own; otherwise prefer inline markdown for supporting context."
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
    markers in the LLM's commentary. The format is deliberately
    paste-friendly: each entry is itself a valid inline markdown link
    of the form ``[N](URL)``, so the LLM can copy the literal token
    into its prose and it will render as a clickable ``[N]`` link in
    LibreChat's markdown renderer.

    Earlier iterations of this function relied on GFM reference-style
    links (a ``## References`` list AND a footer of ``[1]: url`` link
    definitions). That approach failed in production for two reasons:
    (1) the LLM never copied the link-reference footer into its reply,
    so bare ``[N]`` tokens had no destinations to resolve to, and
    (2) the LLM groups citations academically as ``[1, 9]`` which is
    not valid GFM link syntax — neither ``[1]`` nor ``[9]`` matches.

    By emitting each reference as a self-contained ``[N](URL)`` inline
    link AND instructing the LLM (via the preamble) to paste that exact
    token into its prose, both failure modes go away. ``[1](url)`` always
    renders as a clickable link, regardless of compound usage or footer
    copying.

    Returns an empty string when there is no citation_layer, no
    references inside it, or every reference lacks a URL (nothing
    clickable to emit).
    """
    if not isinstance(citation_layer, dict):
        return ""
    references = citation_layer.get("references") or []
    if not references:
        return ""

    entries: list[str] = []
    for ref in references[:_MAX_REFERENCES_IN_LLM_TEXT]:
        if not isinstance(ref, dict):
            continue
        index = ref.get("index")
        url = ref.get("url")
        label = ref.get("label") or ref.get("title") or ref.get("id") or "Source"
        source = ref.get("source") or ""
        if index is None or not url:
            continue
        # Each entry is a literal inline markdown link the LLM can copy
        # verbatim into its prose. The trailing ``— Label, Source`` is
        # a hint for the LLM (and a useful preview if the LLM does
        # paste the entire references block at the end of its reply).
        descriptor_parts = [p for p in (label, source) if p]
        descriptor = ", ".join(descriptor_parts)
        if descriptor:
            entries.append(f"- [{index}]({url}) — {descriptor}")
        else:
            entries.append(f"- [{index}]({url})")

    if not entries:
        return ""

    extra = len(references) - _MAX_REFERENCES_IN_LLM_TEXT
    if extra > 0:
        entries.append(f"- … (+{extra} more references)")

    # Header doubles as a "how to use" hint. The hint must reference the
    # exact ``[N](URL)`` token format the entries below use, so the LLM
    # makes the connection between the list and how it should cite.
    instruction = (
        "Cite inline by pasting one of the `[N](URL)` tokens below VERBATIM "
        "into your prose. Each token is a self-contained clickable link. "
        "Do NOT bare-number `[N]` (no URL = not clickable). Do NOT combine "
        "markers like `[1, 2]` (the comma breaks the link)."
    )

    return (
        "## Sources\n\n"
        + instruction
        + "\n\n"
        + "\n".join(entries)
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

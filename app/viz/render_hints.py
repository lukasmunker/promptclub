"""The fixed render_hint strings the envelope uses.

These are the instructions the LLM reads to decide how to transform the
envelope's `ui` / `data` into either a ``:::artifact{…}:::`` block (rendered
in LibreChat's artifact side pane) or inline markdown in the chat bubble.

Every hint starts with a hard MUST directive so even models with a tendency
to paraphrase will forward the visualization verbatim. All hints end with
a compliance reminder ("Cite sources", "No forward-looking statements").
"""

REACT = (
    "MUST: Your reply MUST include a :::artifact{…}::: block of type "
    "application/vnd.react built from ui.artifact metadata, ui.components "
    "as imports (paths are absolute — e.g. /components/ui/card), and "
    "ui.blueprint as the component tree. Bind values from the 'data' field; "
    "do not invent values. After the artifact block you MAY add 2–5 "
    "sentences of analysis, but the artifact itself is non-optional — do "
    "not write a prose-only answer that omits the visualization. Cite "
    "sources from the 'sources' field. No forward-looking statements, no "
    "BioNTech strategic recommendations."
)

HTML = (
    "MUST: Your reply MUST include a :::artifact{…}::: block of type "
    "text/html using ui.artifact metadata, with ui.raw copied verbatim as "
    "the body. Do NOT paraphrase ui.raw. After the artifact block you MAY "
    "add 2–5 sentences of analysis, but the artifact itself is non-optional. "
    "Tailwind classes work via the preloaded CDN. Cite sources from the "
    "'sources' field in your chat text. No forward-looking statements."
)

MERMAID = (
    "MUST: Your reply MUST include a :::artifact{…}::: block of type "
    "application/vnd.mermaid using ui.artifact metadata, with ui.raw copied "
    "verbatim as the diagram source. Do NOT paraphrase ui.raw. After the "
    "artifact block you MAY add 2–5 sentences of analysis. Cite sources "
    "from the 'sources' field. No forward-looking statements."
)

INLINE_MARKDOWN = (
    "MUST: Your reply MUST start with ui.raw copied VERBATIM into your "
    "chat message body — character for character, including any heading, "
    "markdown table, ```mermaid code fence, emoji, ASCII bars, and the "
    "_Source:_ footer. Do NOT wrap ui.raw in a :::artifact fence. Do NOT "
    "rewrite it, summarize it, describe it in words, or convert tables "
    "into bullet lists. Do NOT replace the _Source:_ footer with your own "
    "sources sentence — ui.raw already contains the proper source "
    "attribution. The visualization is not a supplement to your answer "
    "— it IS your answer. AFTER pasting ui.raw verbatim, you MAY append "
    "2–5 sentences of analytical commentary that interprets the "
    "visualization or connects it to the user's question. Cite sources "
    "from the 'sources' field only if ui.raw's footer doesn't already "
    "cover them. No forward-looking statements, no BioNTech strategic "
    "recommendations."
)

SKIP = (
    "Answer as plain text based on data. Cite sources using NCT/PMID IDs "
    "from the 'sources' field. No forward-looking statements."
)


def for_artifact_type(artifact_type: str) -> str:
    """Return the matching render_hint for a given artifact MIME type."""
    if artifact_type == "application/vnd.react":
        return REACT
    if artifact_type == "text/html":
        return HTML
    if artifact_type == "application/vnd.mermaid":
        return MERMAID
    if artifact_type == "text/markdown":
        return INLINE_MARKDOWN
    raise ValueError(f"Unknown artifact type: {artifact_type!r}")


__all__ = [
    "REACT",
    "HTML",
    "MERMAID",
    "INLINE_MARKDOWN",
    "SKIP",
    "for_artifact_type",
]

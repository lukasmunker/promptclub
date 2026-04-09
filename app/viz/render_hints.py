"""The fixed render_hint strings the envelope uses.

These are the instructions the LLM reads to decide how to transform the
envelope's `ui` / `data` into either a ``:::artifact{…}:::`` block (rendered
in LibreChat's artifact side pane) or inline markdown in the chat bubble.
All strings are terse, self-contained, and end with a compliance reminder
("Cite sources", "No forward-looking statements").
"""

REACT = (
    "Emit a :::artifact{…}::: block of type application/vnd.react using "
    "ui.artifact metadata, ui.components as imports (paths are absolute — e.g. "
    "/components/ui/card), and ui.blueprint as the component tree. Bind values "
    "from the 'data' field; do not invent values. Cite sources from the "
    "'sources' field in your chat text. No forward-looking statements, no "
    "BioNTech strategic recommendations."
)

HTML = (
    "Emit a :::artifact{…}::: block of type text/html using ui.artifact "
    "metadata. Copy ui.raw as the body verbatim. Tailwind classes work via the "
    "preloaded CDN. Cite sources from the 'sources' field in your chat text. "
    "No forward-looking statements."
)

MERMAID = (
    "Emit a :::artifact{…}::: block of type application/vnd.mermaid using "
    "ui.artifact metadata. Copy ui.raw as the diagram source verbatim. Cite "
    "sources from the 'sources' field in your chat text. No forward-looking "
    "statements."
)

INLINE_MARKDOWN = (
    "Copy ui.raw verbatim into your chat message body as plain markdown — do "
    "NOT wrap it in a :::artifact fence. The content uses GFM tables, mermaid "
    "code fences (```mermaid), and/or inline markdown images, all of which "
    "render directly in the chat bubble. You may add one short sentence of "
    "prose before or after ui.raw, but do not modify ui.raw itself. Cite "
    "sources from the 'sources' field. No forward-looking statements, no "
    "BioNTech strategic recommendations."
)

SKIP = (
    "Answer as plain text based on data. Cite sources using NCT/PMID IDs from "
    "the 'sources' field. No forward-looking statements."
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

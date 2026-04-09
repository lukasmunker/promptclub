"""The four fixed render_hint strings the envelope uses.

These are the instructions the LLM reads to decide how to transform the
envelope's `ui` / `data` into a :::artifact{…}::: block. They are deliberately
terse, self-contained, and end with a compliance reminder.
"""

REACT = (
    "Emit a :::artifact{…}::: block of type application/vnd.react using "
    "ui.artifact metadata, ui.components as imports (paths are absolute — e.g. "
    "/components/ui/card), and ui.blueprint as the component tree. Bind values "
    "from the 'data' field; do not invent values. Cite sources from the "
    "'sources' field in your chat text. No forward-looking statements, no "
    "[Company] strategic recommendations."
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
    raise ValueError(f"Unknown artifact type: {artifact_type!r}")


__all__ = ["REACT", "HTML", "MERMAID", "SKIP", "for_artifact_type"]

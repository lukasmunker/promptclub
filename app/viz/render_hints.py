"""The fixed render_hint strings the envelope uses.

These are the instructions the LLM reads to decide how to transform the
envelope's `ui` / `data` into a ``:::artifact{…}:::`` block that LibreChat
mounts in the Artifact side pane.

Every hint starts with a hard MUST directive so even models with a tendency
to paraphrase will forward the visualization verbatim. All hints end with
a compliance reminder ("Cite sources", "No forward-looking statements").
"""

HTML = (
    "MUST: Your reply MUST include a :::artifact{…}::: block of type "
    "text/html using ui.artifact metadata for identifier/title, with ui.raw "
    "copied VERBATIM as the body. Do NOT paraphrase, rewrite, or summarize "
    "ui.raw. Tailwind utility classes work via the preloaded CDN. After the "
    "artifact block you MAY add 2–5 sentences of analysis, but the artifact "
    "itself is non-optional — do not write a prose-only answer that omits "
    "the visualization. Cite sources from the 'sources' field in your chat "
    "text. No forward-looking statements, no [Company] strategic "
    "recommendations."
)

MERMAID = (
    "MUST: Your reply MUST include a :::artifact{…}::: block of type "
    "application/vnd.mermaid using ui.artifact metadata for identifier/title, "
    "with ui.raw copied VERBATIM as the diagram source. Do NOT wrap ui.raw "
    "in a ```mermaid fence — the artifact directive already declares the "
    "type. Do NOT paraphrase ui.raw. After the artifact block you MAY add "
    "2–5 sentences of analysis. Cite sources from the 'sources' field. "
    "No forward-looking statements."
)

SKIP = (
    "Answer as plain text based on data. Cite sources using NCT/PMID IDs "
    "from the 'sources' field. No forward-looking statements."
)


def for_artifact_type(artifact_type: str) -> str:
    """Return the matching render_hint for a given artifact MIME type."""
    if artifact_type == "text/html":
        return HTML
    if artifact_type == "application/vnd.mermaid":
        return MERMAID
    raise ValueError(f"Unknown artifact type: {artifact_type!r}")


__all__ = [
    "HTML",
    "MERMAID",
    "SKIP",
    "for_artifact_type",
]

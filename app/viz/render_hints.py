"""The fixed render_hint strings the envelope uses.

These are the instructions the LLM reads to decide how to transform the
envelope's `ui` / `data` into a ``:::artifact{…}:::`` block that LibreChat
mounts in the Artifact side pane.

LibreChat's artifact directive uses short type names (``html``, ``mermaid``,
``react``, ``python``, etc.), NOT MIME types. We ship ``html`` and
``mermaid`` — the full MIME form (``text/html`` / ``application/vnd.mermaid``)
is silently ignored by LibreChat's remark-directive parser, which is why
the artifacts never rendered when we tried that earlier.

Every hint starts with a hard MUST directive so even models with a tendency
to paraphrase will forward the visualization verbatim. All hints end with
a compliance reminder ("Cite sources", "No forward-looking statements").
"""

HTML = (
    "MUST: Your reply MUST include a :::artifact{…}::: block of type "
    "html using ui.artifact metadata for identifier/title, with ui.raw "
    "copied VERBATIM as the body. Do NOT paraphrase, rewrite, or summarize "
    "ui.raw. Tailwind utility classes work via the preloaded CDN. After the "
    "artifact block you MAY add 2–5 sentences of analysis, but the artifact "
    "itself is non-optional — do not write a prose-only answer that omits "
    "the visualization. Cite sources from the 'sources' field in your chat "
    "text. No forward-looking statements, no BioNTech strategic "
    "recommendations."
)

MERMAID = (
    "MUST: Your reply MUST include a :::artifact{…}::: block of type "
    "mermaid using ui.artifact metadata for identifier/title, with ui.raw "
    "copied VERBATIM as the diagram source. Do NOT wrap ui.raw in a "
    "```mermaid fence — the artifact directive already declares the type. "
    "Do NOT paraphrase ui.raw. After the artifact block you MAY add 2–5 "
    "sentences of analysis. Cite sources from the 'sources' field. "
    "No forward-looking statements."
)

MARKDOWN = (
    "MUST: Your reply MUST include the Markdown snippet in ui.raw copied "
    "VERBATIM, embedded directly inline in your chat message body. This is "
    "the inline-in-chat visualization path — do NOT wrap ui.raw in a "
    "``:::artifact{…}::: block, do NOT convert it to HTML, and do NOT "
    "paraphrase it. The snippet is intentionally compact so it renders "
    "inline without opening the artifact side pane. After the snippet you "
    "MAY add 2–5 sentences of analytical commentary. When you cite a "
    "source in your commentary, use inline numbered markers like [1], [2] "
    "that map to the References list in the tool result. Cite sources "
    "from the 'sources' field. No forward-looking statements."
)

SKIP = (
    "Answer as plain text based on data. Cite sources using NCT/PMID IDs "
    "from the 'sources' field. No forward-looking statements."
)


def for_artifact_type(artifact_type: str) -> str:
    """Return the matching render_hint for a given artifact type."""
    if artifact_type == "html":
        return HTML
    if artifact_type == "mermaid":
        return MERMAID
    if artifact_type == "markdown":
        return MARKDOWN
    raise ValueError(f"Unknown artifact type: {artifact_type!r}")


__all__ = [
    "HTML",
    "MERMAID",
    "MARKDOWN",
    "SKIP",
    "for_artifact_type",
]

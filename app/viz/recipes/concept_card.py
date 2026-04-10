"""Markdown recipe: definition / concept card.

Used by the fallback dispatcher when the user query is a "what is X" /
"define X" pattern and the response is essentially a single concept
explanation. Renders as a compact **inline** Markdown snippet — not a
side-pane HTML artifact — because a 1-3 sentence definition doesn't
warrant opening LibreChat's artifact side pane.

Input shape:

    {
        "term": "Required — the canonical term",
        "definition": "1-2 sentences",
        "context": "Optional 2-4 sentence extended explanation",
        "category": "Optional category tag (rendered as a small italic badge)",
    }
"""

from __future__ import annotations

from typing import Any

from app.viz.contract import ArtifactMeta, Source, UiPayload
from app.viz.utils.identifiers import make_identifier

__all__ = ["build"]


def build(
    data: dict[str, Any],
    sources: list[Source] | None = None,
) -> UiPayload:
    term = str(data.get("term") or "Concept")
    definition = data.get("definition")
    context = data.get("context")
    category = data.get("category")

    lines: list[str] = []
    header = f"### {_safe_markdown(term)}"
    if category:
        header += f"  _({_safe_markdown(str(category))})_"
    lines.append(header)

    if definition:
        lines.append("")
        lines.append(f"> {_safe_markdown(str(definition))}")

    if context:
        lines.append("")
        lines.append(_safe_markdown(str(context)))

    raw = "\n".join(lines)

    return UiPayload(
        recipe="concept_card",
        artifact=ArtifactMeta(
            identifier=make_identifier("concept_card", term),
            type="markdown",
            title=term,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )


def _safe_markdown(value: str) -> str:
    """Neutralize raw HTML in user inputs so the inline-markdown path is
    still XSS-safe.

    Markdown renderers (GFM / remark) pass through raw HTML by default,
    so an unescaped ``<script>`` tag in a user-provided term would render
    as a real script block. Escaping ``<`` / ``>`` / ``&`` gives us the
    same safety guarantee the HTML recipes get from ``escape_html`` —
    the tokens render literally and cannot execute as markup.

    Returns the input stripped of trailing whitespace; callers decide
    layout / punctuation around the escaped value.
    """
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .strip()
    )

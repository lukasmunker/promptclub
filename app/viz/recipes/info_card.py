"""Markdown recipe: universal catch-all info card.

This recipe is the visualization coverage guarantor. It accepts ANY
``data`` shape (including empty dicts) and produces a valid UiPayload
with a compact Markdown body. When no specialized recipe matches, the
fallback dispatcher in ``app.viz.fallback`` routes here.

Renders as a compact **inline** Markdown snippet — not a side-pane HTML
artifact — because the catch-all is almost always just a title + a few
bullets, and opening LibreChat's artifact side pane for a short bullet
list is pure friction.

Input shape (all optional):

    {
        "title": "Card title (defaults to 'Result')",
        "subtitle": "Optional subtitle",
        "bullets": ["fact 1", "fact 2"],         # rendered as a bullet list
        "no_results_hint": "Hint shown when bullets is empty",
        "knowledge_annotations": [...],            # WS2 glossary entries
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
    title = str(data.get("title") or "Result")
    subtitle = data.get("subtitle")
    bullets = data.get("bullets") or []
    hint = data.get("no_results_hint")

    lines: list[str] = [f"### {_safe_markdown(title)}"]

    if subtitle:
        lines.append("")
        lines.append(f"_{_safe_markdown(str(subtitle))}_")

    bullet_items = [b for b in bullets if b] if isinstance(bullets, list) else []
    if bullet_items:
        lines.append("")
        for b in bullet_items:
            lines.append(f"- {_safe_markdown(str(b))}")
    elif hint:
        lines.append("")
        lines.append(f"_{_safe_markdown(str(hint))}_")
    else:
        lines.append("")
        lines.append("_No additional details available._")

    glossary_md = _render_glossary(data.get("knowledge_annotations") or [])
    if glossary_md:
        lines.append("")
        lines.append(glossary_md)

    raw = "\n".join(lines)

    return UiPayload(
        recipe="info_card",
        artifact=ArtifactMeta(
            identifier=make_identifier("info_card", title),
            type="markdown",
            title=title,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )


def _render_glossary(annotations: list[dict[str, Any]]) -> str:
    """Render a deduplicated glossary block from knowledge annotations.

    Only one entry per unique ``lexicon_id`` is shown — the first
    occurrence wins. Returns an empty string if no annotations produce
    a usable term + definition.
    """
    if not annotations:
        return ""

    seen: set[str] = set()
    items: list[str] = []
    for ann in annotations:
        lid = ann.get("lexicon_id")
        if not lid or lid in seen:
            continue
        seen.add(lid)
        term = _safe_markdown(str(ann.get("matched_term", "")))
        definition = _safe_markdown(str(ann.get("short_definition", "")))
        if not term or not definition:
            continue
        items.append(f"- **{term}** — {definition}")

    if not items:
        return ""

    return "**Glossary**\n\n" + "\n".join(items)


def _safe_markdown(value: str) -> str:
    """Neutralize raw HTML in user inputs so the inline-markdown path is
    still XSS-safe. Escaping ``<`` / ``>`` / ``&`` gives us the same
    guarantee the HTML recipes get from ``escape_html`` — tokens render
    literally and cannot execute as markup."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .strip()
    )

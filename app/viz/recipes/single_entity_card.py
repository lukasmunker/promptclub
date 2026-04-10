"""Markdown recipe: single-entity detail card.

Used by the fallback dispatcher when the response represents one
identifiable entity (one trial, one drug, one disease, one target).
Renders as a compact **inline** Markdown snippet — not a side-pane HTML
artifact — because a small key/value facts list doesn't warrant opening
LibreChat's artifact side pane.

Input shape:

    {
        "kind": "trial" | "drug" | "disease" | "target",
        "title": "Required — the entity name or ID",
        "subtitle": "Optional one-line description",
        "facts": [("Key", "Value"), ...],   # ordered key/value pairs
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
    kind = str(data.get("kind") or "entity")
    title = str(data.get("title") or "Entity")
    subtitle = data.get("subtitle")
    facts = data.get("facts") or []

    lines: list[str] = []
    lines.append(f"_{_safe_markdown(kind)}_")
    lines.append(f"### {_safe_markdown(title)}")
    if subtitle:
        lines.append("")
        lines.append(f"{_safe_markdown(str(subtitle))}")

    rows: list[tuple[str, str]] = []
    if isinstance(facts, list):
        for entry in facts:
            if not entry:
                continue
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                key = entry[0]
                value = entry[1]
            elif isinstance(entry, dict):
                # Support {"key": ..., "value": ...} fact shape too.
                key = entry.get("key") or entry.get("name")
                value = entry.get("value")
            else:
                continue
            if not key:
                continue
            rows.append((_safe_markdown(str(key)), _safe_markdown(str(value))))

    if rows:
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("| --- | --- |")
        for key, value in rows:
            lines.append(f"| {key} | {value} |")

    raw = "\n".join(lines)

    return UiPayload(
        recipe="single_entity_card",
        artifact=ArtifactMeta(
            identifier=make_identifier("single_entity_card", title),
            type="markdown",
            title=title,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )


def _safe_markdown(value: str) -> str:
    """Neutralize raw HTML in user inputs so the inline-markdown path is
    still XSS-safe. Also collapses pipes to avoid breaking GFM tables."""
    escaped = (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .strip()
    )
    # ``|`` is the GFM table column delimiter — escape to keep rows intact.
    return escaped.replace("|", "\\|")

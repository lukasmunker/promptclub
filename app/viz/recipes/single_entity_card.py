"""HTML recipe: single-entity detail card.

Used by the fallback dispatcher when the response represents one
identifiable entity (one trial, one drug, one disease, one target).
Renders a title, subtitle, and a key/value facts table.

Input shape:

    {
        "kind": "trial" | "drug" | "disease" | "target" (used for icon hint),
        "title": "Required — the entity name or ID",
        "subtitle": "Optional one-line description",
        "facts": [("Key", "Value"), ...],   # ordered key/value pairs
    }
"""

from __future__ import annotations

from typing import Any

from app.viz.contract import ArtifactMeta, Source, UiPayload
from app.viz.utils.html import assert_safe_html, escape_html
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

    subtitle_html = ""
    if subtitle:
        subtitle_html = (
            f'<p class="text-sm text-gray-500 mt-1">{escape_html(str(subtitle))}</p>'
        )

    facts_html = ""
    if facts:
        rows = "\n        ".join(
            f"""<div class="flex justify-between border-b border-gray-100 py-1.5">
          <span class="text-xs uppercase tracking-wide text-gray-500">{escape_html(str(k))}</span>
          <span class="text-sm font-medium text-gray-900 text-right">{escape_html(str(v))}</span>
        </div>"""
            for k, v in facts if k
        )
        facts_html = (
            f'<dl class="mt-3 space-y-0">\n        {rows}\n      </dl>'
        )

    raw = f"""<div class="p-4 font-sans rounded-lg border border-gray-200 bg-white">
  <header class="border-b border-gray-100 pb-2 mb-2">
    <p class="text-xs uppercase tracking-wide text-gray-400">{escape_html(kind)}</p>
    <h2 class="text-base font-semibold text-gray-900">{escape_html(title)}</h2>
    {subtitle_html}
  </header>
  <section>
    {facts_html}
  </section>
</div>"""

    assert_safe_html(raw)

    return UiPayload(
        recipe="single_entity_card",
        artifact=ArtifactMeta(
            identifier=make_identifier("single_entity_card", title),
            type="html",
            title=title,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )

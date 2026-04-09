"""HTML recipe: universal catch-all info card.

This recipe is the visualization coverage guarantor. It accepts ANY
``data`` shape (including empty dicts) and produces a valid UiPayload
with a Tailwind-styled card. When no specialized recipe matches, the
fallback dispatcher in app.viz.fallback routes here.

Input shape (all optional):

    {
        "title": "Card title (defaults to 'Result')",
        "subtitle": "Optional subtitle",
        "bullets": ["fact 1", "fact 2"],         # rendered as a bullet list
        "no_results_hint": "Hint shown when bullets is empty",
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
    title = str(data.get("title") or "Result")
    subtitle = data.get("subtitle")
    bullets = data.get("bullets") or []
    hint = data.get("no_results_hint")

    body_parts: list[str] = []
    if subtitle:
        body_parts.append(
            f'<p class="text-sm text-gray-500">{escape_html(str(subtitle))}</p>'
        )

    if bullets:
        items = "\n      ".join(
            f"<li>{escape_html(str(b))}</li>" for b in bullets if b
        )
        body_parts.append(
            f'<ul class="mt-3 list-disc list-inside text-sm text-gray-800 space-y-1">\n      {items}\n    </ul>'
        )
    elif hint:
        body_parts.append(
            f'<p class="mt-3 text-sm italic text-gray-500">{escape_html(str(hint))}</p>'
        )
    else:
        body_parts.append(
            '<p class="mt-3 text-sm italic text-gray-500">No additional details available.</p>'
        )

    body = "\n    ".join(body_parts)

    glossary_html = _render_glossary(data.get("knowledge_annotations") or [])

    raw = f"""<div class="p-4 font-sans rounded-lg border border-gray-200 bg-white">
  <header class="border-b border-gray-100 pb-2 mb-2">
    <h2 class="text-base font-semibold text-gray-900">{escape_html(title)}</h2>
  </header>
  <section>
    {body}
    {glossary_html}
  </section>
</div>"""

    assert_safe_html(raw)

    return UiPayload(
        recipe="info_card",
        artifact=ArtifactMeta(
            identifier=make_identifier("info_card", title),
            type="html",
            title=title,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )


def _render_glossary(annotations: list[dict[str, Any]]) -> str:
    """Render a deduplicated glossary block from knowledge annotations.

    Only one entry per unique lexicon_id is shown — the first occurrence
    wins. Returns empty string if no annotations.
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
        term = escape_html(str(ann.get("matched_term", "")))
        definition = escape_html(str(ann.get("short_definition", "")))
        items.append(
            f'<li class="text-xs text-gray-700"><span class="font-semibold">{term}</span> — {definition}</li>'
        )

    if not items:
        return ""

    return f"""<div class="mt-4 pt-3 border-t border-gray-100">
      <p class="text-xs uppercase tracking-wide text-gray-400 mb-2">Glossary</p>
      <ul class="space-y-1">
        {"".join(items)}
      </ul>
    </div>"""

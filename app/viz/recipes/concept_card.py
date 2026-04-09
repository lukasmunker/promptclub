"""HTML recipe: definition / concept card.

Used by the fallback dispatcher when the user query is a "what is X" /
"define X" pattern and the response is essentially a single concept
explanation. Renders the term as a heading with a definition and
optional extended context underneath.

Input shape:

    {
        "term": "Required — the canonical term",
        "definition": "1-2 sentences",
        "context": "Optional 2-4 sentence extended explanation",
        "category": "Optional category tag (rendered as small badge)",
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
    term = str(data.get("term") or "Concept")
    definition = data.get("definition")
    context = data.get("context")
    category = data.get("category")

    badge_html = ""
    if category:
        badge_html = (
            f'<span class="ml-2 inline-block rounded bg-blue-50 text-blue-700 '
            f'border border-blue-200 px-2 py-0.5 text-xs uppercase tracking-wide">'
            f"{escape_html(str(category))}</span>"
        )

    definition_html = ""
    if definition:
        definition_html = (
            f'<p class="text-sm text-gray-800 mt-2">{escape_html(str(definition))}</p>'
        )

    context_html = ""
    if context:
        context_html = (
            f'<p class="text-sm text-gray-600 mt-3 leading-relaxed">'
            f"{escape_html(str(context))}</p>"
        )

    raw = f"""<div class="p-4 font-sans rounded-lg border border-gray-200 bg-white">
  <header class="border-b border-gray-100 pb-2 mb-2">
    <h2 class="text-base font-semibold text-gray-900 inline">{escape_html(term)}</h2>{badge_html}
  </header>
  <section>
    {definition_html}
    {context_html}
  </section>
</div>"""

    assert_safe_html(raw)

    return UiPayload(
        recipe="concept_card",
        artifact=ArtifactMeta(
            identifier=make_identifier("concept_card", term),
            type="html",
            title=term,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )

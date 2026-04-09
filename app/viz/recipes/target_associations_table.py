"""HTML recipe: target-disease associations from Open Targets.

Renders as a ``text/html`` artifact — a scored table showing which protein
targets are associated with a given disease, with the association score
visualized as a small horizontal CSS bar.

Works on the normalized shape produced by
``app.viz.adapters._normalize_target_associations``:

    {
        "disease_id": "EFO_0000756",
        "disease_name": "melanoma",
        "associations": [
            {
                "target_symbol": "BRAF",
                "target_name": "B-Raf proto-oncogene",
                "target_id": "ENSG00000157764",
                "score": 0.92
            }
        ]
    }
"""

from __future__ import annotations

from typing import Any

from app.viz.contract import ArtifactMeta, UiPayload
from app.viz.theme import (
    BADGE_MUTED,
    BADGE_TARGET,
    BAR_FILL_PRIMARY,
    BAR_TRACK,
    CARD_STYLE_BLOCK,
    CARD_WRAPPER,
    HEADER_BORDER,
    LINK_SUBTLE,
)
from app.viz.utils.html import assert_safe_html, escape_html
from app.viz.utils.identifiers import make_identifier

__all__ = ["build", "MAX_ROWS"]

MAX_ROWS = 20


def build(
    data: dict[str, Any],
    sources: list[Any] | None = None,
) -> UiPayload:
    disease_name = data.get("disease_name") or "Disease"
    disease_id = data.get("disease_id") or "unknown"
    title = f"Target Associations — {disease_name}"

    associations = data.get("associations") or []
    # Sort by score descending, then take top N
    associations_sorted = sorted(
        associations,
        key=lambda a: a.get("score") or 0,
        reverse=True,
    )[:MAX_ROWS]

    rows_html = "\n".join(_render_row(a) for a in associations_sorted)

    # Open Targets disease page link
    opentargets_url = (
        f"https://platform.opentargets.org/disease/{escape_html(disease_id)}"
    )

    raw = f"""{CARD_STYLE_BLOCK}
<div class="{CARD_WRAPPER}">
  <header class="mb-3 flex items-baseline justify-between {HEADER_BORDER} pb-2">
    <div>
      <h2 class="text-base font-semibold">{escape_html(title)}</h2>
      <p class="text-xs text-gray-500">Source: Open Targets · Disease ID <span class="font-mono">{escape_html(disease_id)}</span></p>
    </div>
    <a href="{opentargets_url}" target="_blank" rel="noopener"
       class="{LINK_SUBTLE}">View on Open Targets →</a>
  </header>
  <table class="w-full text-sm">
    <thead>
      <tr class="text-left text-xs uppercase text-gray-500 border-b border-gray-200">
        <th class="py-2 pr-3">Target</th>
        <th class="py-2 pr-3">Name</th>
        <th class="py-2 pr-3 w-40">Association Score</th>
      </tr>
    </thead>
    <tbody>
{rows_html}
    </tbody>
  </table>
</div>"""

    assert_safe_html(raw)

    return UiPayload(
        recipe="target_associations_table",
        artifact=ArtifactMeta(
            identifier=make_identifier("target_associations_table", disease_id),
            type="html",
            title=title,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )


def _render_row(assoc: dict[str, Any]) -> str:
    symbol = assoc.get("target_symbol") or "?"
    name = assoc.get("target_name") or ""
    target_id = assoc.get("target_id") or ""
    score = assoc.get("score")

    target_badge: str
    if target_id:
        target_url = (
            f"https://platform.opentargets.org/target/{escape_html(target_id)}"
        )
        target_badge = (
            f'<a href="{target_url}" target="_blank" rel="noopener" '
            f'class="{BADGE_TARGET}">{escape_html(symbol)}</a>'
        )
    else:
        target_badge = f'<span class="{BADGE_MUTED}">{escape_html(symbol)}</span>'

    # Render score as a horizontal bar + number. Clamp to [0, 1] and
    # convert to a 0-100 percent width for the fill.
    if isinstance(score, (int, float)):
        clamped = max(0.0, min(1.0, float(score)))
        pct = round(clamped * 100)
        score_cell = (
            f'<div class="flex items-center gap-2">'
            f'<div class="flex-1 h-2 rounded-full {BAR_TRACK} overflow-hidden">'
            f'<div class="h-full {BAR_FILL_PRIMARY}" style="width: {pct}%"></div>'
            f"</div>"
            f'<span class="font-mono text-xs text-gray-700 tabular-nums w-10 text-right">'
            f"{clamped:.2f}</span></div>"
        )
    else:
        score_cell = '<span class="text-xs text-gray-400">—</span>'

    return f"""      <tr class="border-b border-gray-100">
        <td class="py-2 pr-3 align-top">{target_badge}</td>
        <td class="py-2 pr-3 align-top text-gray-700">{escape_html(name)}</td>
        <td class="py-2 pr-3 align-top">{score_cell}</td>
      </tr>"""

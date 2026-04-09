"""HTML recipe: indication landscape dashboard.

Renders as a ``text/html`` artifact with four panels:

  1. Stat tiles — total trials, unique phases, unique sponsors, enrollment
  2. Phase distribution — SVG donut (via app.viz.utils.html.svg_donut)
  3. Status breakdown — SVG donut
  4. Top sponsors — HTML table with CSS bar + numeric trial count

Formerly a React + recharts blueprint. Rewritten to plain HTML + Tailwind +
inline SVG so it renders without Sandpack. Panels without usable data are
omitted gracefully.

Input shape comes from ``get_indication_landscape`` / ``analyze_indication_landscape``:

    {
        "indication": "NSCLC",
        "phase_distribution": [{"phase": "Phase 1", "count": 42}, ...],
        "status_breakdown": [{"status": "Recruiting", "count": 95}, ...],
        "top_sponsors": [{"name": "Merck", "trials": 34}, ...],
        "enrollment_over_time": [{"month": "2025-01", "enrolled": 120}, ...]  # optional
    }
"""

from __future__ import annotations

from typing import Any

from app.viz.contract import ArtifactMeta, UiPayload
from app.viz.utils.html import assert_safe_html, escape_html, svg_donut
from app.viz.utils.identifiers import make_identifier

__all__ = ["build", "MAX_SPONSORS_IN_BAR"]

MAX_SPONSORS_IN_BAR = 20


def build(
    data: dict[str, Any],
    sources: list[Any] | None = None,
) -> UiPayload:
    indication = data.get("indication") or "Indication"
    title = data.get("title") or f"{indication} Landscape"

    phase_dist = data.get("phase_distribution") or []
    status_breakdown = data.get("status_breakdown") or []
    top_sponsors = _cap_sponsors(data.get("top_sponsors") or [])

    panels: list[str] = []

    tiles_html = _render_stat_tiles(phase_dist, status_breakdown, top_sponsors)
    if tiles_html:
        panels.append(tiles_html)

    phase_donut_html = _render_phase_donut(phase_dist)
    status_donut_html = _render_status_donut(status_breakdown)
    if phase_donut_html or status_donut_html:
        panels.append(_render_donut_row(phase_donut_html, status_donut_html))

    sponsors_html = _render_sponsors_table(top_sponsors)
    if sponsors_html:
        panels.append(sponsors_html)

    body_html = (
        "\n".join(panels)
        if panels
        else (
            '<section><p class="text-sm text-gray-500 italic">'
            f"No landscape data available for {escape_html(indication)}.</p></section>"
        )
    )

    raw = f"""<div class="p-4 font-sans text-gray-900 space-y-4">
  <header class="border-b border-gray-200 pb-2">
    <h2 class="text-base font-semibold">{escape_html(title)}</h2>
    <p class="text-xs text-gray-500">Source: ClinicalTrials.gov</p>
  </header>
  {body_html}
</div>"""

    assert_safe_html(raw)

    return UiPayload(
        recipe="indication_dashboard",
        artifact=ArtifactMeta(
            identifier=make_identifier("indication_dashboard", indication),
            type="text/html",
            title=title,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )


# --- Stat tiles ------------------------------------------------------------


def _render_stat_tiles(
    phase_dist: list[dict[str, Any]],
    status_breakdown: list[dict[str, Any]],
    top_sponsors: list[dict[str, Any]],
) -> str:
    total_trials = sum(
        int(row.get("count", 0))
        for row in phase_dist
        if isinstance(row, dict) and isinstance(row.get("count"), (int, float))
    )
    distinct_phases = sum(
        1
        for row in phase_dist
        if isinstance(row, dict)
        and isinstance(row.get("count"), (int, float))
        and row.get("count") > 0
    )
    recruiting = 0
    for row in status_breakdown:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").lower()
        count = row.get("count", 0)
        if "recruit" in status and isinstance(count, (int, float)):
            recruiting += int(count)
    sponsor_count = len(top_sponsors)

    # Don't render the panel if all stats are zero — decision layer should
    # have caught it, but defense in depth.
    if not (total_trials or distinct_phases or recruiting or sponsor_count):
        return ""

    tiles = [
        ("Total Trials", total_trials, "blue"),
        ("Phases", distinct_phases, "blue"),
        ("Recruiting", recruiting, "emerald"),
        ("Sponsors", sponsor_count, "purple"),
    ]
    rendered = "\n    ".join(_tile(label, value, color) for label, value, color in tiles)
    return f"""<section>
    <h3 class="sr-only">Landscape Overview</h3>
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
    {rendered}
    </div>
  </section>"""


def _tile(label: str, value: int, color: str) -> str:
    color_classes = {
        "blue": "bg-blue-50 text-blue-700 border-blue-200",
        "emerald": "bg-emerald-50 text-emerald-700 border-emerald-200",
        "amber": "bg-amber-50 text-amber-700 border-amber-200",
        "purple": "bg-purple-50 text-purple-700 border-purple-200",
    }.get(color, "bg-gray-50 text-gray-700 border-gray-200")
    display = f"{value:,}".replace(",", ".") if isinstance(value, int) else "—"
    return f"""<div class="rounded-lg border {color_classes} p-3 text-center">
      <div class="text-2xl font-semibold tabular-nums">{escape_html(display)}</div>
      <div class="text-xs uppercase tracking-wide opacity-80 mt-1">{escape_html(label)}</div>
    </div>"""


# --- Donut pies ------------------------------------------------------------


def _render_phase_donut(phase_dist: list[dict[str, Any]]) -> str:
    segments = [
        (str(row.get("phase", "?")), float(row.get("count", 0)))
        for row in phase_dist
        if isinstance(row, dict) and isinstance(row.get("count"), (int, float))
    ]
    donut = svg_donut(segments)
    if not donut:
        return ""
    return f"""<div class="rounded-lg border border-gray-200 p-3">
      <h3 class="text-sm font-semibold text-gray-900 mb-2">Phase Distribution</h3>
      {donut}
    </div>"""


def _render_status_donut(status_breakdown: list[dict[str, Any]]) -> str:
    segments = [
        (str(row.get("status", "?")), float(row.get("count", 0)))
        for row in status_breakdown
        if isinstance(row, dict) and isinstance(row.get("count"), (int, float))
    ]
    donut = svg_donut(segments)
    if not donut:
        return ""
    return f"""<div class="rounded-lg border border-gray-200 p-3">
      <h3 class="text-sm font-semibold text-gray-900 mb-2">Status Breakdown</h3>
      {donut}
    </div>"""


def _render_donut_row(phase_html: str, status_html: str) -> str:
    panels = [p for p in (phase_html, status_html) if p]
    if not panels:
        return ""
    inner = "\n    ".join(panels)
    return f"""<section class="grid grid-cols-1 sm:grid-cols-2 gap-3">
    {inner}
  </section>"""


# --- Top sponsors table ----------------------------------------------------


def _render_sponsors_table(top_sponsors: list[dict[str, Any]]) -> str:
    if not top_sponsors:
        return ""
    max_count = max(
        (int(s.get("trials", 0)) for s in top_sponsors if isinstance(s, dict)),
        default=0,
    )
    if max_count == 0:
        return ""

    rows: list[str] = []
    for idx, sponsor in enumerate(top_sponsors, start=1):
        if not isinstance(sponsor, dict):
            continue
        name = escape_html(sponsor.get("name") or "—")
        count = int(sponsor.get("trials", 0))
        pct = round((count / max_count) * 100) if max_count else 0
        bar_cell = (
            f'<div class="flex items-center gap-2">'
            f'<div class="flex-1 h-2 rounded-full bg-gray-100 overflow-hidden">'
            f'<div class="h-full bg-blue-500" style="width: {pct}%"></div>'
            f"</div>"
            f'<span class="font-mono text-xs text-gray-700 tabular-nums w-10 text-right">'
            f"{count}</span></div>"
        )
        rows.append(
            f"      <tr class=\"border-b border-gray-100\">\n"
            f'        <td class="py-2 pr-3 align-top text-gray-500 tabular-nums">{idx}</td>\n'
            f'        <td class="py-2 pr-3 align-top font-medium">{name}</td>\n'
            f'        <td class="py-2 pr-3 align-top">{bar_cell}</td>\n'
            f"      </tr>"
        )
    rows_html = "\n".join(rows)

    return f"""<section>
    <h3 class="text-sm font-semibold text-gray-900 mb-2">Top Sponsors</h3>
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left text-xs uppercase text-gray-500 border-b border-gray-200">
          <th class="py-2 pr-3 w-8">#</th>
          <th class="py-2 pr-3">Sponsor</th>
          <th class="py-2 pr-3">Trials</th>
        </tr>
      </thead>
      <tbody>
{rows_html}
      </tbody>
    </table>
  </section>"""


# --- Helpers ---------------------------------------------------------------


def _cap_sponsors(
    sponsors: list[dict[str, Any]], cap: int = MAX_SPONSORS_IN_BAR
) -> list[dict[str, Any]]:
    """Keep the top ``cap`` sponsors; bucket the rest as 'Other'."""
    if len(sponsors) <= cap:
        return list(sponsors)
    top = list(sponsors[:cap])
    rest = sponsors[cap:]
    other_trials = sum(
        int(s.get("trials", 0)) for s in rest if isinstance(s, dict)
    )
    if other_trials > 0:
        top.append({"name": "Other", "trials": other_trials})
    return top

"""HTML recipe: whitespace / gap analysis for a disease indication.

Renders the output of the ``analyze_whitespace`` MCP tool as a self-contained
``text/html`` artifact:

  - Top: a row of stat tiles for trial counts by phase + recruiting status
  - Bottom: a list of identified whitespace signals as warning-styled cards

Input shape (from app.viz.adapters._handle_analyze_whitespace):

    {
        "condition": "non-small cell lung cancer",
        "trial_counts_by_phase": {"phase_1": 42, "phase_2": 78, "phase_3": 35},
        "trial_counts_by_status": {"recruiting": 95, "completed": 38},
        "pubmed_publications_3yr": 1200,
        "fda_label_records": 8,
        "identified_whitespace": [
            "Few Phase 3 trials — late-stage evidence lacking",
            "Limited recent publications relative to trial volume"
        ]
    }
"""

from __future__ import annotations

from typing import Any

from app.viz.contract import ArtifactMeta, UiPayload
from app.viz.utils.html import assert_safe_html, escape_html
from app.viz.utils.identifiers import make_identifier

__all__ = ["build"]


def build(
    data: dict[str, Any],
    sources: list[Any] | None = None,
) -> UiPayload:
    condition = data.get("condition") or "indication"
    title = f"Whitespace Analysis — {condition}"

    phase_counts = data.get("trial_counts_by_phase") or {}
    status_counts = data.get("trial_counts_by_status") or {}
    pubs_3yr = data.get("pubmed_publications_3yr")
    fda_count = data.get("fda_label_records")
    signals = data.get("identified_whitespace") or []

    stat_tiles = _render_stat_tiles(phase_counts, status_counts, pubs_3yr, fda_count)
    signals_html = _render_signals(signals)

    raw = f"""<div class="p-4 font-sans text-gray-900 space-y-4">
  <header class="border-b border-gray-200 pb-2">
    <h2 class="text-base font-semibold">{escape_html(title)}</h2>
    <p class="text-xs text-gray-500">Source: ClinicalTrials.gov · PubMed · openFDA</p>
  </header>
  {stat_tiles}
  {signals_html}
</div>"""

    assert_safe_html(raw)

    return UiPayload(
        recipe="whitespace_card",
        artifact=ArtifactMeta(
            identifier=make_identifier("whitespace_card", condition),
            type="html",
            title=title,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )


# --- Stat tiles -------------------------------------------------------------


def _render_stat_tiles(
    phase_counts: dict[str, Any],
    status_counts: dict[str, Any],
    pubs_3yr: Any,
    fda_count: Any,
) -> str:
    """Top row: 6 stat tiles. Phases 1/2/3, recruiting, publications, FDA labels."""
    tiles = [
        ("Phase 1", phase_counts.get("phase_1"), "blue"),
        ("Phase 2", phase_counts.get("phase_2"), "blue"),
        ("Phase 3", phase_counts.get("phase_3"), "blue"),
        ("Recruiting", status_counts.get("recruiting"), "emerald"),
        ("Publications (3y)", pubs_3yr, "amber"),
        ("FDA labels", fda_count, "purple"),
    ]
    rendered = "\n    ".join(_tile(label, value, color) for label, value, color in tiles)
    return f"""<section>
    <h3 class="sr-only">Activity Overview</h3>
    <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
    {rendered}
    </div>
  </section>"""


def _tile(label: str, value: Any, color: str) -> str:
    color_classes = {
        "blue": "bg-blue-50 text-blue-700 border-blue-200",
        "emerald": "bg-emerald-50 text-emerald-700 border-emerald-200",
        "amber": "bg-amber-50 text-amber-700 border-amber-200",
        "purple": "bg-purple-50 text-purple-700 border-purple-200",
    }.get(color, "bg-gray-50 text-gray-700 border-gray-200")

    display_value: str
    if value is None:
        display_value = "—"
    elif isinstance(value, int):
        display_value = f"{value:,}".replace(",", ".")
    elif isinstance(value, float):
        display_value = f"{value:.0f}"
    else:
        display_value = str(value)

    return f"""<div class="rounded-lg border {color_classes} p-3 text-center">
      <div class="text-2xl font-semibold tabular-nums">{escape_html(display_value)}</div>
      <div class="text-xs uppercase tracking-wide opacity-80 mt-1">{escape_html(label)}</div>
    </div>"""


# --- Identified-whitespace signals -----------------------------------------


def _render_signals(signals: list[Any]) -> str:
    if not signals:
        return """<section>
    <p class="text-sm text-gray-500 italic">
      No specific whitespace signals identified for this indication.
    </p>
  </section>"""

    items = "\n      ".join(
        _signal_card(str(signal)) for signal in signals if signal
    )
    return f"""<section>
    <h3 class="text-sm font-semibold text-gray-900 mb-2">Identified Whitespace Signals</h3>
    <ul class="space-y-2">
      {items}
    </ul>
  </section>"""


def _signal_card(signal: str) -> str:
    return f"""<li class="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="mt-0.5 h-4 w-4 flex-shrink-0">
          <path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"></path>
        </svg>
        <span>{escape_html(signal)}</span>
      </li>"""

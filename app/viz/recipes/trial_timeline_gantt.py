"""Mermaid recipe: trial timelines as a gantt chart.

Renders as an ``application/vnd.mermaid`` artifact — LibreChat has a dedicated
``Mermaid.tsx`` renderer with zoom/pan.

Produces a ``gantt`` diagram with one section per sponsor and one task row
per trial. Labels are aggressively sanitized because Mermaid's parser chokes
on colons, quotes, and unmatched parens in free-form labels.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.viz.contract import ArtifactMeta, UiPayload
from app.viz.utils.identifiers import make_identifier
from app.viz.utils.mermaid import is_valid_iso_date, safe_label

__all__ = ["build", "MAX_TRIALS"]

MAX_TRIALS = 15


def build(
    data: dict[str, Any],
    sources: list[Any] | None = None,
) -> UiPayload:
    trials_all: list[dict[str, Any]] = data.get("trials") or []
    # Only trials with valid ISO start + primary completion dates can be rendered
    trials = [
        t
        for t in trials_all
        if is_valid_iso_date(t.get("start_date"))
        and is_valid_iso_date(t.get("primary_completion_date"))
    ][:MAX_TRIALS]

    title = data.get("title") or "Trial Timeline Comparison"
    query = data.get("query") or title

    raw = _render_gantt(title, trials)

    return UiPayload(
        recipe="trial_timeline_gantt",
        artifact=ArtifactMeta(
            identifier=make_identifier("trial_timeline_gantt", query),
            type="application/vnd.mermaid",
            title=title,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )


def _render_gantt(title: str, trials: list[dict[str, Any]]) -> str:
    lines: list[str] = [
        "gantt",
        "    dateFormat  YYYY-MM-DD",
        f"    title       {safe_label(title, max_length=80)}",
        "    axisFormat  %Y-%m",
    ]

    # Group by sponsor → one section per sponsor.
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in trials:
        sponsor = safe_label(t.get("sponsor") or "(unknown)")
        groups[sponsor].append(t)

    for sponsor, items in groups.items():
        lines.append(f"    section {sponsor}")
        for t in items:
            label = safe_label(
                t.get("acronym") or t.get("title") or t.get("nct_id") or "trial"
            )
            nct = t.get("nct_id") or "trial"
            # Mermaid task syntax: Label :status, taskId, start, end
            # We use "active" uniformly — no speculation about which is "done".
            lines.append(
                f"    {label} :active, {nct}, "
                f"{t['start_date']}, {t['primary_completion_date']}"
            )

    if not trials:
        # Empty-state: render a gantt with a placeholder section so the artifact
        # still parses. The decision layer should have caught this, but defense in depth.
        lines.append("    section No data")
        lines.append("    (no datable trials) :active, nodata, 2026-01-01, 2026-01-02")

    return "\n".join(lines)

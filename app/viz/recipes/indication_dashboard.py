"""Inline Markdown recipe: indication landscape dashboard.

Formerly rendered as a React + recharts artifact (BarChart + PieChart +
LineChart + shadcn Card grid), but LibreChat's Sandpack 2.19.8 crashes on
recharts-based artifacts with "Attempted to assign to readonly property".
We migrated to inline markdown with Mermaid pies + Markdown tables instead.

Sections (rendered only when the corresponding data is present):
  1. Phase Distribution — mermaid pie chart
  2. Status Breakdown — mermaid pie chart
  3. Top Sponsors — markdown table with ASCII bars
  4. Enrollment Pace — markdown table (no chart, since mermaid xychart-beta
     is unreliable in LibreChat 2.19.8 sandpack)

The recipe name is kept as ``indication_dashboard`` for backward
compatibility with decision.py, the envelope contract, and existing callers.
"""

from __future__ import annotations

from typing import Any

from app.viz.contract import ArtifactMeta, UiPayload
from app.viz.utils.citations import format_source_footer
from app.viz.utils.identifiers import make_identifier

__all__ = ["build", "MAX_SPONSORS_IN_BAR"]

MAX_SPONSORS_IN_BAR = 20
BAR_WIDTH = 10  # ASCII bar width in block characters


def build(
    data: dict[str, Any],
    sources: list[Any] | None = None,
) -> UiPayload:
    indication = data.get("indication") or "Indication"
    title = data.get("title") or f"{indication} Landscape"

    phase_dist = data.get("phase_distribution") or []
    status_breakdown = data.get("status_breakdown") or []
    top_sponsors = _cap_sponsors(data.get("top_sponsors") or [])
    enrollment_series = data.get("enrollment_over_time") or []

    sections: list[str] = []

    phase_md = _render_phase_pie(phase_dist, indication)
    if phase_md:
        sections.append(phase_md)

    status_md = _render_status_pie(status_breakdown, indication)
    if status_md:
        sections.append(status_md)

    sponsors_md = _render_sponsors_table(top_sponsors)
    if sponsors_md:
        sections.append(sponsors_md)

    enrollment_md = _render_enrollment_table(enrollment_series)
    if enrollment_md:
        sections.append(enrollment_md)

    if not sections:
        sections.append(
            f"_No landscape data available for {indication}._"
        )

    body_md = "\n\n".join(sections)
    source_footer = format_source_footer(sources)

    raw = f"## {_md_escape(title)}\n\n{body_md}\n{source_footer}"

    return UiPayload(
        recipe="indication_dashboard",
        artifact=ArtifactMeta(
            identifier=make_identifier("indication_dashboard", indication),
            type="text/markdown",
            title=title,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )


# --- Phase distribution pie ------------------------------------------------


def _render_phase_pie(
    phase_dist: list[dict[str, Any]], indication: str
) -> str:
    """Mermaid pie chart. Skipped when fewer than 2 phases have non-zero data."""
    non_zero = [
        (str(row.get("phase", "?")), int(row.get("count", 0)))
        for row in phase_dist
        if isinstance(row, dict)
        and isinstance(row.get("count"), (int, float))
        and row.get("count") > 0
    ]
    if len(non_zero) < 2:
        return ""

    title = _safe_mermaid_label(f"Phase Distribution — {indication}", 80)
    lines = ["### Phase Distribution", "", "```mermaid", f"pie title {title}"]
    for label, count in non_zero:
        safe = _safe_mermaid_label(label, 40)
        lines.append(f'    "{safe}" : {count}')
    lines.append("```")
    return "\n".join(lines)


# --- Status breakdown pie --------------------------------------------------


def _render_status_pie(
    status_breakdown: list[dict[str, Any]], indication: str
) -> str:
    """Mermaid pie chart for status distribution. Skipped when fewer than 2
    distinct statuses have non-zero counts."""
    non_zero = [
        (str(row.get("status", "?")), int(row.get("count", 0)))
        for row in status_breakdown
        if isinstance(row, dict)
        and isinstance(row.get("count"), (int, float))
        and row.get("count") > 0
    ]
    if len(non_zero) < 2:
        return ""

    title = _safe_mermaid_label(f"Status Breakdown — {indication}", 80)
    lines = ["### Status Breakdown", "", "```mermaid", f"pie title {title}"]
    for label, count in non_zero:
        safe = _safe_mermaid_label(label, 40)
        lines.append(f'    "{safe}" : {count}')
    lines.append("```")
    return "\n".join(lines)


# --- Top sponsors table ----------------------------------------------------


def _render_sponsors_table(top_sponsors: list[dict[str, Any]]) -> str:
    if not top_sponsors:
        return ""

    # Scale bars against the leader's count so the #1 sponsor gets a full bar
    max_count = max(
        (int(s.get("trials", 0)) for s in top_sponsors if isinstance(s, dict)),
        default=0,
    )
    if max_count == 0:
        return ""

    header = (
        "### Top Sponsors\n\n"
        "| Rank | Sponsor | Trials | Share |\n"
        "| ---:| --- | ---:| --- |\n"
    )
    rows: list[str] = []
    for idx, sponsor in enumerate(top_sponsors, start=1):
        if not isinstance(sponsor, dict):
            continue
        name = _md_escape_cell(sponsor.get("name") or "—")
        count = int(sponsor.get("trials", 0))
        filled = round((count / max_count) * BAR_WIDTH) if max_count else 0
        bar = "█" * filled + "░" * (BAR_WIDTH - filled)
        rows.append(f"| {idx} | {name} | {count} | `{bar}` |")
    return header + "\n".join(rows)


# --- Enrollment over time table --------------------------------------------


def _render_enrollment_table(
    series: list[dict[str, Any]],
) -> str:
    """Markdown table + optional trend arrows for enrollment-over-time data.

    No chart — mermaid xychart-beta would be the natural fit but it's beta
    in mermaid 11.x and crashed LibreChat's sandpack earlier. A table is
    reliable and still visually informative with trend arrows.
    """
    if not series:
        return ""

    rows_data = [
        (str(row.get("month", "?")), int(row.get("enrolled", 0)))
        for row in series
        if isinstance(row, dict)
        and isinstance(row.get("enrolled"), (int, float))
    ]
    if len(rows_data) < 2:
        return ""

    header = (
        "### Enrollment Pace\n\n"
        "| Period | Enrolled | Δ vs previous |\n"
        "| --- | ---:| --- |\n"
    )

    rendered_rows: list[str] = []
    prev: int | None = None
    for month, enrolled in rows_data:
        if prev is None:
            delta_cell = "—"
        else:
            diff = enrolled - prev
            if diff > 0:
                delta_cell = f"📈 +{diff:,}".replace(",", ".")
            elif diff < 0:
                delta_cell = f"📉 {diff:,}".replace(",", ".")
            else:
                delta_cell = "➡️ 0"
        rendered_rows.append(
            f"| {_md_escape_cell(month)} | {enrolled:,} | {delta_cell} |".replace(
                ",", "."
            )
        )
        prev = enrolled
    return header + "\n".join(rendered_rows)


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


def _safe_mermaid_label(text: object, max_length: int = 80) -> str:
    if text is None:
        return "(untitled)"
    s = str(text).replace('"', "").replace("\n", " ").replace("\r", " ").strip()
    if len(s) > max_length:
        s = s[: max_length - 1].rstrip() + "…"
    return s or "(untitled)"


def _md_escape(text: object) -> str:
    if text is None:
        return ""
    return str(text).replace("\\", "\\\\").replace("_", "\\_").replace("*", "\\*")


def _md_escape_cell(text: object) -> str:
    if text is None:
        return ""
    s = str(text).replace("\n", " ").replace("\r", " ").strip()
    return s.replace("|", "\\|")

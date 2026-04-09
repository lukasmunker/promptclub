"""HTML recipe: trials grouped by sponsor (or phase) in a responsive card grid.

Used as the alternative to ``trial_timeline_gantt`` when either:
- the user explicitly requests a cards view via ``prefer_visualization="cards"``
- the comparison exceeds ``MAX_TRIALS_IN_GANTT`` and a gantt would be illegible
- start/primary_completion dates are missing so a gantt can't be drawn
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.viz.contract import ArtifactMeta, UiPayload
from app.viz.theme import BADGE_MUTED, BADGE_NCT, PILL_PHASE
from app.viz.utils.html import assert_safe_html, escape_html
from app.viz.utils.identifiers import make_identifier

__all__ = ["build"]


def build(
    data: dict[str, Any],
    sources: list[Any] | None = None,
) -> UiPayload:
    trials: list[dict[str, Any]] = data.get("trials") or []
    group_key = data.get("group_by") or "sponsor"
    title = data.get("title") or "Sponsor Pipeline"
    query = data.get("query") or title

    groups = _group_trials(trials, group_key)

    section_html = "\n".join(
        _render_section(name, items) for name, items in groups.items()
    )

    raw = (
        f'<div class="space-y-6 p-4 font-sans text-gray-900">\n'
        f"{section_html}\n"
        f"</div>"
    )

    assert_safe_html(raw)

    return UiPayload(
        recipe="sponsor_pipeline_cards",
        artifact=ArtifactMeta(
            identifier=make_identifier("sponsor_pipeline_cards", query),
            type="html",
            title=title,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )


# --- Grouping ---------------------------------------------------------------


def _group_trials(
    trials: list[dict[str, Any]], group_key: str
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in trials:
        name = t.get(group_key) or "(unknown)"
        groups[str(name)].append(t)
    # Sort sections by trial count, descending, then by name
    return dict(
        sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    )


# --- Section + card templates ----------------------------------------------


def _render_section(name: str, items: list[dict[str, Any]]) -> str:
    header = (
        f'<div class="flex items-baseline justify-between border-b border-gray-200 pb-2">\n'
        f'  <h2 class="text-base font-semibold text-gray-900">{escape_html(name)}</h2>\n'
        f'  <span class="text-xs text-gray-500">{len(items)} trials</span>\n'
        f'</div>'
    )
    cards = "\n".join(_render_card(t) for t in items)
    return (
        f'<section>\n{header}\n'
        f'<div class="mt-3 grid sm:grid-cols-2 lg:grid-cols-3 gap-3">\n'
        f"{cards}\n"
        f"</div>\n</section>"
    )


def _render_card(trial: dict[str, Any]) -> str:
    nct = trial.get("nct_id") or "(no id)"
    nct_badge = (
        f'<a href="https://clinicaltrials.gov/study/{escape_html(nct)}" '
        f'target="_blank" rel="noopener" '
        f'class="{BADGE_NCT}">{escape_html(nct)}</a>'
        if trial.get("nct_id")
        else f'<span class="{BADGE_MUTED}">(no id)</span>'
    )

    phase = trial.get("phase")
    phase_pill = (
        f'<span class="{PILL_PHASE}">{escape_html(phase)}</span>'
        if phase
        else ""
    )

    title = trial.get("acronym") or trial.get("title") or "(untitled)"
    status = trial.get("status")
    start = trial.get("start_date")
    end = trial.get("primary_completion_date")

    dates_line = ""
    if start and end:
        dates_line = f"{escape_html(start)} → {escape_html(end)}"
    elif start:
        dates_line = f"start {escape_html(start)}"

    meta_parts = []
    if status:
        meta_parts.append(escape_html(status))
    if dates_line:
        meta_parts.append(dates_line)
    meta_line = " · ".join(meta_parts)

    return f"""<article class="rounded-lg border border-gray-200 bg-white p-3">
  <div class="flex items-start justify-between gap-2">
    {nct_badge}
    {phase_pill}
  </div>
  <h3 class="mt-2 font-medium text-gray-900 leading-snug">{escape_html(title)}</h3>
  <p class="mt-1 text-xs text-gray-500">{meta_line}</p>
</article>"""

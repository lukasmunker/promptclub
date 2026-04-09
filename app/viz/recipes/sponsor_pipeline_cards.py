"""Inline Markdown recipe: trials grouped by sponsor, each as its own table.

Used as the alternative to ``trial_timeline_gantt`` when either:
- the user explicitly requests a cards/table view via ``prefer_visualization="cards"``
- the comparison exceeds ``MAX_TRIALS_IN_GANTT`` and a gantt would be illegible
- start/primary_completion dates are missing so a gantt can't be drawn

Produces a ``text/markdown`` envelope with one ``### Sponsor`` section per
sponsor, each containing a GFM table of that sponsor's trials. Renders
directly in the chat bubble.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.viz.contract import ArtifactMeta, UiPayload
from app.viz.utils.citations import format_source_footer
from app.viz.utils.emoji import format_phase, format_status
from app.viz.utils.identifiers import make_identifier

__all__ = ["build", "BAR_WIDTH"]

BAR_WIDTH = 10  # 0.0 → 1.0 scaled to 10 Unicode block characters


def build(
    data: dict[str, Any],
    sources: list[Any] | None = None,
) -> UiPayload:
    trials: list[dict[str, Any]] = data.get("trials") or []
    group_key = data.get("group_by") or "sponsor"
    title = data.get("title") or "Sponsor Pipeline"
    query = data.get("query") or title

    groups = _group_trials(trials, group_key)

    # Pre-section overview: ranked sponsor-count table with ASCII bars.
    # This gives a quick visual sense of *which* sponsor dominates before
    # the user scrolls through the per-sponsor details below.
    overview_md = _render_sponsor_ranking(groups)

    sections_md = "\n\n".join(
        _render_section(name, items) for name, items in groups.items()
    )

    source_footer = format_source_footer(sources)
    raw = (
        f"## {_md_escape(title)}\n\n"
        f"{overview_md}"
        f"{sections_md}\n"
        f"{source_footer}"
    )

    return UiPayload(
        recipe="sponsor_pipeline_cards",
        artifact=ArtifactMeta(
            identifier=make_identifier("sponsor_pipeline_cards", query),
            type="text/markdown",
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
    return dict(sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])))


# --- Section rendering ------------------------------------------------------


def _render_section(name: str, items: list[dict[str, Any]]) -> str:
    """A ### header + a GFM table of the sponsor's trials."""
    header = f"### {_md_escape(name)} ({len(items)} trial{'s' if len(items) != 1 else ''})\n"
    table_header = (
        "| NCT | Trial | Phase | Status | Start → Primary completion |\n"
        "| --- | --- | --- | --- | --- |\n"
    )
    rows = "\n".join(_row(t) for t in items)
    return header + "\n" + table_header + rows + "\n"


def _row(trial: dict[str, Any]) -> str:
    nct = trial.get("nct_id") or ""
    nct_cell = (
        f"[`{_md_escape_cell(nct)}`](https://clinicaltrials.gov/study/{_md_escape_url(nct)})"
        if nct
        else "—"
    )

    title = trial.get("acronym") or trial.get("title") or "(untitled)"
    title_cell = _md_escape_cell(_truncate(title, 60)) or "—"

    phase_raw = trial.get("phase")
    phase_cell = _md_escape_cell(format_phase(phase_raw)) if phase_raw else "—"
    status_raw = trial.get("status")
    status_cell = _md_escape_cell(format_status(status_raw)) if status_raw else "—"

    start = trial.get("start_date")
    end = trial.get("primary_completion_date")
    if start and end:
        dates_cell = f"{_md_escape_cell(start)} → {_md_escape_cell(end)}"
    elif start:
        dates_cell = f"start {_md_escape_cell(start)}"
    else:
        dates_cell = "—"

    return f"| {nct_cell} | {title_cell} | {phase_cell} | {status_cell} | {dates_cell} |"


# --- Sponsor ranking overview (ASCII bars) ---------------------------------


def _render_sponsor_ranking(
    groups: dict[str, list[dict[str, Any]]],
) -> str:
    """GFM table of sponsors ranked by trial count, with a visual bar column.

    Returns an empty string when there's only one sponsor (the per-section
    layout below already makes the point — no need for a 1-row ranking
    table).
    """
    if len(groups) < 2:
        return ""

    max_count = max((len(items) for items in groups.values()), default=0)
    if max_count == 0:
        return ""

    header = (
        "### Sponsor Ranking\n\n"
        "| Rank | Sponsor | Trials | Share |\n"
        "| ---:| --- | ---:| --- |\n"
    )
    rows: list[str] = []
    for idx, (name, items) in enumerate(groups.items(), start=1):
        count = len(items)
        # Scale each sponsor's count against the leader (not against the
        # total) so the leader has a full bar and the bottom sponsor still
        # shows a visible sliver.
        ratio = count / max_count if max_count else 0
        filled = round(ratio * BAR_WIDTH)
        bar = "█" * filled + "░" * (BAR_WIDTH - filled)
        rows.append(
            f"| {idx} | {_md_escape_cell(name)} | {count} | `{bar}` |"
        )
    return header + "\n".join(rows) + "\n\n"


# --- Escaping helpers ------------------------------------------------------


def _md_escape(text: object) -> str:
    if text is None:
        return ""
    s = str(text)
    return s.replace("\\", "\\\\").replace("_", "\\_").replace("*", "\\*")


def _md_escape_cell(text: object) -> str:
    if text is None:
        return ""
    s = str(text).replace("\n", " ").replace("\r", " ").strip()
    return s.replace("|", "\\|")


def _md_escape_url(url: object) -> str:
    if url is None:
        return ""
    return str(url).replace(")", "%29").replace("(", "%28").replace(" ", "%20")


def _truncate(text: str | None, max_len: int) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"

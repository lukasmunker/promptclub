"""Inline Markdown recipe: a table of clinical trials or publications.

Renders as a ``text/markdown`` envelope — the LLM copies ``ui.raw`` directly
into its chat message body (no artifact fence). LibreChat's GFM pipeline
renders the table inline in the chat bubble.

Caps at 25 rows and appends a "… N more" note linking to the full
ClinicalTrials.gov search URL when there are more results.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.viz.contract import ArtifactMeta, UiPayload
from app.viz.utils.citations import format_source_footer
from app.viz.utils.emoji import format_phase, format_status
from app.viz.utils.identifiers import make_identifier

__all__ = ["build", "MAX_ROWS"]

MAX_ROWS = 25


def build(
    data: dict[str, Any],
    sources: list[Any] | None = None,
) -> UiPayload:
    """Build a Markdown table envelope for search_clinical_trials / search_publications."""
    results: list[dict[str, Any]] = data.get("results") or []
    total = data.get("total", len(results))
    query = data.get("query") or data.get("title") or "search"
    title = data.get("title") or _default_title(data)

    shown = results[:MAX_ROWS]
    more = max(total - len(shown), 0)

    # Decide whether this is a trial list (NCT badges) or publications (PMID)
    has_nct = any(hit.get("nct_id") for hit in shown)
    has_pmid = any(hit.get("pmid") for hit in shown)

    # Optional pre-table overview chart: mermaid pie of status breakdown.
    # Only render when this is a trial result set AND there are ≥2 distinct
    # non-empty statuses — otherwise a pie with one slice is pointless.
    overview_md = ""
    if has_nct or not has_pmid:
        overview_md = _render_status_pie(shown, title)
        table_md = _render_trial_table(shown)
    else:
        table_md = _render_publication_table(shown)

    overflow_md = ""
    if more > 0:
        search_url = data.get("search_url")
        if search_url:
            overflow_md = (
                f"\n_… and **{more} more** — "
                f"[view the full list on ClinicalTrials.gov]({_md_escape_url(search_url)})._\n"
            )
        else:
            overflow_md = f"\n_… and **{more} more** not shown._\n"

    source_footer = format_source_footer(sources)
    raw = (
        f"## {_md_escape(title)}\n\n"
        f"{overview_md}"
        f"{table_md}"
        f"{overflow_md}"
        f"{source_footer}"
    )

    return UiPayload(
        recipe="trial_search_results",
        artifact=ArtifactMeta(
            identifier=make_identifier("trial_search_results", query),
            type="text/markdown",
            title=title,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )


# --- Trial table ------------------------------------------------------------


def _render_trial_table(hits: list[dict[str, Any]]) -> str:
    """GFM table with one row per trial.

    Columns: NCT (linked), Phase, Status, Sponsor, n, Primary completion.
    """
    header = (
        "| NCT | Phase | Status | Sponsor | n | Primary completion |\n"
        "| --- | --- | --- | --- | ---:| --- |\n"
    )
    rows = "\n".join(_trial_row(h) for h in hits)
    return header + rows + "\n"


def _trial_row(hit: dict[str, Any]) -> str:
    nct = hit.get("nct_id") or ""
    nct_cell = (
        f"[`{_md_escape_cell(nct)}`](https://clinicaltrials.gov/study/{_md_escape_url(nct)})"
        if nct
        else "—"
    )
    # Decorate phase and status with a leading emoji for at-a-glance scanning
    phase_raw = hit.get("phase")
    phase_cell = (
        _md_escape_cell(format_phase(phase_raw)) if phase_raw else "—"
    )
    status_raw = hit.get("status")
    status_cell = (
        _md_escape_cell(format_status(status_raw)) if status_raw else "—"
    )
    sponsor = _md_escape_cell(_truncate(hit.get("sponsor"), 40)) or "—"
    enrollment = (
        str(hit.get("enrollment")) if hit.get("enrollment") is not None else "—"
    )
    completion = _md_escape_cell(hit.get("primary_completion_date")) or "—"
    return f"| {nct_cell} | {phase_cell} | {status_cell} | {sponsor} | {enrollment} | {completion} |"


# --- Publication table ------------------------------------------------------


def _render_publication_table(hits: list[dict[str, Any]]) -> str:
    """GFM table with one row per publication.

    Columns: PMID (linked), Title, Journal · Year.
    """
    header = (
        "| PMID | Title | Journal · Year |\n"
        "| --- | --- | --- |\n"
    )
    rows = "\n".join(_publication_row(h) for h in hits)
    return header + rows + "\n"


def _publication_row(hit: dict[str, Any]) -> str:
    pmid = hit.get("pmid") or ""
    pmid_cell = (
        f"[`{_md_escape_cell(pmid)}`](https://pubmed.ncbi.nlm.nih.gov/{_md_escape_url(pmid)}/)"
        if pmid
        else "—"
    )
    title = _md_escape_cell(_truncate(hit.get("title"), 100)) or "—"
    # The adapter writes "Journal · Pub date" into the `sponsor` slot for PubMed hits
    meta = hit.get("sponsor") or ""
    meta_cell = _md_escape_cell(meta) or "—"
    return f"| {pmid_cell} | {title} | {meta_cell} |"


# --- Helpers ----------------------------------------------------------------


def _default_title(data: dict[str, Any]) -> str:
    q = data.get("query") or {}
    if isinstance(q, dict):
        indication = q.get("indication")
        phase = q.get("phase")
        parts = []
        if phase:
            parts.append(f"Phase {phase}")
        if indication:
            parts.append(str(indication).title())
        parts.append("Trials")
        return " ".join(parts)
    return "Search Results"


def _truncate(text: str | None, max_len: int) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _md_escape(text: object) -> str:
    """Escape characters that would break markdown layout at block level."""
    if text is None:
        return ""
    s = str(text)
    return s.replace("\\", "\\\\").replace("_", "\\_").replace("*", "\\*")


def _md_escape_cell(text: object) -> str:
    """Escape for use inside a GFM table cell. Pipes break the column
    layout and newlines break row parsing."""
    if text is None:
        return ""
    s = str(text).replace("\n", " ").replace("\r", " ").strip()
    return s.replace("|", "\\|")


def _md_escape_url(url: object) -> str:
    """Escape a URL for use inside a markdown link target."""
    if url is None:
        return ""
    return str(url).replace(")", "%29").replace("(", "%28").replace(" ", "%20")


# --- Status pie chart (pre-table overview) ---------------------------------

# Minimum distinct non-empty statuses before we emit a pie chart.
# One status → pie has a single slice which is pointless.
_MIN_STATUSES_FOR_PIE = 2


def _render_status_pie(hits: list[dict[str, Any]], title: str) -> str:
    """Build an optional mermaid pie chart above the trial table showing the
    status breakdown.

    Only emits the chart when there are ≥2 distinct non-empty statuses across
    the shown hits. Otherwise returns an empty string (the caller handles the
    concatenation).

    The chart is wrapped in a ``` ```mermaid ``` fence so LibreChat's chat
    markdown pipeline renders it inline via its Mermaid component.
    """
    counts: Counter[str] = Counter()
    for hit in hits:
        status = hit.get("status")
        if not status:
            continue
        counts[str(status).strip()] += 1

    if len(counts) < _MIN_STATUSES_FOR_PIE:
        return ""

    # Mermaid pie syntax: labels go in quotes, values are plain numbers.
    # Labels can't contain unescaped quotes — strip them.
    pie_title = _safe_mermaid_label(f"Status breakdown — {title}", max_length=80)
    lines = ["```mermaid", f"pie title {pie_title}"]
    # Sort by count descending so the biggest slice is first
    for status, count in counts.most_common():
        safe_status = _safe_mermaid_label(status, max_length=40)
        lines.append(f'    "{safe_status}" : {count}')
    lines.append("```")
    lines.append("")  # blank line after the fence
    return "\n".join(lines) + "\n"


def _safe_mermaid_label(text: object, max_length: int = 80) -> str:
    """Strip characters that break mermaid pie label parsing."""
    if text is None:
        return "(untitled)"
    s = str(text).replace('"', "").replace("\n", " ").replace("\r", " ").strip()
    if len(s) > max_length:
        s = s[: max_length - 1].rstrip() + "…"
    return s or "(untitled)"

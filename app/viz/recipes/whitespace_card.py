"""Inline Markdown recipe: whitespace / gap analysis for a disease indication.

Renders the output of the ``analyze_whitespace`` MCP tool as a ``text/markdown``
envelope. The LLM copies ``ui.raw`` directly into its chat message so the
activity-overview table and whitespace signals appear inline in the chat
bubble — no artifact pane needed.

Input shape (from ``app.viz.adapters._handle_analyze_whitespace``)::

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
from app.viz.utils.identifiers import make_identifier

__all__ = ["build"]


def build(data: dict[str, Any]) -> UiPayload:
    condition = data.get("condition") or "indication"
    title = f"Whitespace Analysis — {condition}"

    phase_counts = data.get("trial_counts_by_phase") or {}
    status_counts = data.get("trial_counts_by_status") or {}
    pubs_3yr = data.get("pubmed_publications_3yr")
    fda_count = data.get("fda_label_records")
    signals = data.get("identified_whitespace") or []

    overview_md = _render_overview_table(phase_counts, status_counts, pubs_3yr, fda_count)
    signals_md = _render_signals(signals)

    raw = (
        f"## {_md_escape(title)}\n\n"
        f"_Source: ClinicalTrials.gov · PubMed · openFDA_\n\n"
        f"### Activity Overview\n\n"
        f"{overview_md}\n"
        f"### Identified Whitespace Signals\n\n"
        f"{signals_md}\n"
    )

    return UiPayload(
        recipe="whitespace_card",
        artifact=ArtifactMeta(
            identifier=make_identifier("whitespace_card", condition),
            type="text/markdown",
            title=title,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )


# --- Overview table --------------------------------------------------------


def _render_overview_table(
    phase_counts: dict[str, Any],
    status_counts: dict[str, Any],
    pubs_3yr: Any,
    fda_count: Any,
) -> str:
    """GFM table with one row per metric. Missing values render as '—'."""
    rows = [
        ("Phase 1 trials", phase_counts.get("phase_1")),
        ("Phase 2 trials", phase_counts.get("phase_2")),
        ("Phase 3 trials", phase_counts.get("phase_3")),
        ("Recruiting", status_counts.get("recruiting")),
        ("Completed", status_counts.get("completed")),
        ("Publications (3y)", pubs_3yr),
        ("FDA label records", fda_count),
    ]
    header = "| Metric | Count |\n| --- | ---:|\n"
    body = "\n".join(
        f"| {_md_escape_cell(label)} | {_format_count(value)} |" for label, value in rows
    )
    return header + body + "\n"


def _format_count(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, int):
        # Thousands separator with German style (period) to match the domain context
        return f"{value:,}".replace(",", ".")
    if isinstance(value, float):
        return f"{value:.0f}"
    return _md_escape_cell(value)


# --- Signals list ----------------------------------------------------------


def _render_signals(signals: list[Any]) -> str:
    """Bulleted list of gap signals, each prefixed with ⚠️. If empty, we
    explicitly note that there were no signals so the section still makes
    sense rather than looking broken."""
    if not signals:
        return "_No specific whitespace signals identified for this indication._\n"

    items = "\n".join(
        f"- ⚠️ {_md_escape_inline(str(signal))}" for signal in signals if signal
    )
    return items + "\n"


# --- Escaping helpers ------------------------------------------------------


def _md_escape(text: object) -> str:
    """Escape block-level markdown metacharacters (used in headings)."""
    if text is None:
        return ""
    s = str(text)
    return s.replace("\\", "\\\\").replace("_", "\\_").replace("*", "\\*")


def _md_escape_inline(text: object) -> str:
    """Escape for inline bullet / sentence context. Preserves em-dashes and
    normal punctuation; just neutralizes markdown emphasis markers."""
    if text is None:
        return ""
    s = str(text)
    return s.replace("\\", "\\\\").replace("*", "\\*")


def _md_escape_cell(text: object) -> str:
    """Escape for GFM table cells (pipes and newlines are structural)."""
    if text is None:
        return ""
    s = str(text).replace("\n", " ").replace("\r", " ").strip()
    return s.replace("|", "\\|")

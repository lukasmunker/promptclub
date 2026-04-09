"""Inline Markdown recipe: single-trial deep dive with section headers.

Formerly rendered as a React + shadcn Tabs artifact, but LibreChat's Sandpack
runtime (2.19.8) crashes with "Attempted to assign to readonly property" on
React-Tabs-based artifacts. We migrated to inline markdown with ``###``
section headers instead — no Sandpack, no crash, renders directly in the chat
bubble like the other 5 inline recipes.

The recipe name is kept as ``trial_detail_tabs`` for backward compatibility
with decision.py, adapters.py, and the envelope contract, even though the
output now uses section headers rather than literal tabs.

Sections (only rendered when the corresponding data is present):
  1. Overview — trial title, status, sponsor, phase, enrollment, dates
  2. Design & Endpoints — primary / secondary outcome measures
  3. Eligibility — inclusion / exclusion criteria, age, gender
  4. Arms & Interventions — study arms and their interventions
  5. Sites — study locations table
  6. Publications — linked PubMed papers
"""

from __future__ import annotations

from typing import Any

from app.viz.contract import ArtifactMeta, UiPayload
from app.viz.utils.citations import format_source_footer
from app.viz.utils.emoji import format_phase, format_status
from app.viz.utils.identifiers import make_identifier

__all__ = ["build"]


def build(
    data: dict[str, Any],
    sources: list[Any] | None = None,
) -> UiPayload:
    nct_id = data.get("nct_id") or "trial"
    title_text = data.get("title") or nct_id

    # --- Header ------------------------------------------------------------
    header_md = _render_header(title_text, nct_id, data)

    # --- Optional sections (only rendered when data present) --------------
    sections: list[str] = []

    overview_md = _render_overview(data)
    if overview_md:
        sections.append(overview_md)

    design_md = _render_design(data)
    if design_md:
        sections.append(design_md)

    eligibility_md = _render_eligibility(data)
    if eligibility_md:
        sections.append(eligibility_md)

    arms_md = _render_arms(data)
    if arms_md:
        sections.append(arms_md)

    sites_md = _render_sites(data)
    if sites_md:
        sections.append(sites_md)

    publications_md = _render_publications(data)
    if publications_md:
        sections.append(publications_md)

    # If ALL optional sections are empty, emit a small placeholder so the
    # reader knows the trial record was sparse rather than that the recipe
    # glitched.
    body_md = "\n\n".join(sections) if sections else (
        "_No detailed design, eligibility, arms, sites, or publication "
        "data available for this trial._"
    )

    source_footer = format_source_footer(sources)

    raw = f"{header_md}\n\n{body_md}\n{source_footer}"

    return UiPayload(
        recipe="trial_detail_tabs",
        artifact=ArtifactMeta(
            identifier=make_identifier("trial_detail_tabs", nct_id),
            type="text/markdown",
            title=f"Trial {nct_id}",
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )


# --- Header -----------------------------------------------------------------


def _render_header(title: str, nct_id: str, data: dict[str, Any]) -> str:
    """Top-of-card heading + a single-line metadata strip with badges."""
    nct_link = (
        f"[`{_md_escape_cell(nct_id)}`](https://clinicaltrials.gov/study/"
        f"{_md_escape_url(nct_id)})"
    )
    badges: list[str] = []

    phase = data.get("phase")
    if phase:
        badges.append(format_phase(phase))

    status = data.get("status")
    if status:
        badges.append(format_status(status))

    sponsor = data.get("sponsor")
    if sponsor:
        badges.append(f"**{_md_escape_cell(sponsor)}**")

    enrollment = data.get("enrollment")
    if enrollment is not None:
        badges.append(f"n={enrollment}")

    start = data.get("start_date")
    end = data.get("primary_completion_date")
    if start and end:
        badges.append(f"{_md_escape_cell(start)} → {_md_escape_cell(end)}")
    elif start:
        badges.append(f"start {_md_escape_cell(start)}")

    badge_line = " · ".join(badges) if badges else ""

    return (
        f"## {_md_escape(title)}\n\n"
        f"{nct_link}{'  ·  ' + badge_line if badge_line else ''}"
    )


# --- Sections ---------------------------------------------------------------


def _render_overview(data: dict[str, Any]) -> str:
    summary = data.get("brief_summary") or data.get("description")
    if not summary:
        return ""
    return f"### Overview\n\n{_md_escape_paragraph(summary)}"


def _render_design(data: dict[str, Any]) -> str:
    primary = data.get("primary_outcome_measures") or []
    secondary = data.get("secondary_outcome_measures") or []

    if not primary and not secondary:
        return ""

    parts: list[str] = ["### Design & Endpoints"]

    if primary:
        parts.append("**Primary outcome measures:**")
        for o in primary:
            measure = _md_escape_inline(o.get("measure", ""))
            time_frame = _md_escape_inline(o.get("time_frame", ""))
            if time_frame:
                parts.append(f"- {measure} _({time_frame})_")
            else:
                parts.append(f"- {measure}")

    if secondary:
        parts.append("")
        parts.append("**Secondary outcome measures:**")
        for o in secondary:
            measure = _md_escape_inline(o.get("measure", ""))
            time_frame = _md_escape_inline(o.get("time_frame", ""))
            if time_frame:
                parts.append(f"- {measure} _({time_frame})_")
            else:
                parts.append(f"- {measure}")

    return "\n".join(parts)


def _render_eligibility(data: dict[str, Any]) -> str:
    elig = data.get("eligibility") or {}
    criteria = elig.get("criteria") or ""
    gender = elig.get("gender") or ""
    min_age = elig.get("minimum_age") or ""
    max_age = elig.get("maximum_age") or ""

    if not criteria and not gender and not min_age and not max_age:
        return ""

    parts: list[str] = ["### Eligibility"]

    meta_bits: list[str] = []
    if gender:
        meta_bits.append(f"**Gender:** {_md_escape_inline(gender)}")
    if min_age:
        meta_bits.append(f"**Min age:** {_md_escape_inline(min_age)}")
    if max_age:
        meta_bits.append(f"**Max age:** {_md_escape_inline(max_age)}")
    if meta_bits:
        parts.append(" · ".join(meta_bits))
        parts.append("")

    if criteria:
        # Criteria text is usually a multi-line string with "Inclusion:" and
        # "Exclusion:" sections. We wrap it in a fenced plain-text block so
        # line breaks are preserved and it's clearly demarcated from the
        # surrounding prose.
        parts.append("```")
        parts.append(str(criteria))
        parts.append("```")

    return "\n".join(parts)


def _render_arms(data: dict[str, Any]) -> str:
    arms = data.get("arms") or []
    if not arms:
        return ""

    header = (
        "### Arms & Interventions\n\n"
        "| Arm | Type | Interventions |\n"
        "| --- | --- | --- |\n"
    )
    rows: list[str] = []
    for arm in arms:
        label = _md_escape_cell(arm.get("label") or "—")
        arm_type = _md_escape_cell(arm.get("type") or "—")
        interventions = arm.get("interventions") or []
        if isinstance(interventions, list):
            interventions_cell = ", ".join(
                _md_escape_cell(i) for i in interventions if i
            ) or "—"
        else:
            interventions_cell = _md_escape_cell(interventions) or "—"
        rows.append(f"| {label} | {arm_type} | {interventions_cell} |")
    return header + "\n".join(rows)


def _render_sites(data: dict[str, Any]) -> str:
    sites = data.get("sites") or data.get("locations") or []
    if not sites:
        return ""

    # Promptclub's TrialRecord.locations is list[str] — handle both shapes
    if sites and isinstance(sites[0], str):
        header = "### Sites\n\n"
        body = "\n".join(f"- {_md_escape_inline(s)}" for s in sites)
        return header + body

    header = (
        "### Sites\n\n"
        "| Facility | City | Country | Status |\n"
        "| --- | --- | --- | --- |\n"
    )
    rows: list[str] = []
    for site in sites:
        if not isinstance(site, dict):
            continue
        facility = _md_escape_cell(site.get("facility") or "—")
        city = _md_escape_cell(site.get("city") or "—")
        country = _md_escape_cell(site.get("country") or "—")
        status = _md_escape_cell(site.get("status") or "—")
        rows.append(f"| {facility} | {city} | {country} | {status} |")
    return header + "\n".join(rows) if rows else ""


def _render_publications(data: dict[str, Any]) -> str:
    pubs = data.get("linked_publications") or data.get("publications") or []
    if not pubs:
        return ""

    header = (
        "### Linked Publications\n\n"
        "| PMID | Title | Journal · Year |\n"
        "| --- | --- | --- |\n"
    )
    rows: list[str] = []
    for pub in pubs:
        if not isinstance(pub, dict):
            continue
        pmid = pub.get("pmid") or ""
        pmid_cell = (
            f"[`{_md_escape_cell(pmid)}`](https://pubmed.ncbi.nlm.nih.gov/"
            f"{_md_escape_url(pmid)}/)"
            if pmid
            else "—"
        )
        title = _md_escape_cell(_truncate(pub.get("title"), 80)) or "—"
        journal = pub.get("journal") or ""
        year = pub.get("year") or ""
        meta = " · ".join(p for p in [journal, str(year) if year else ""] if p) or "—"
        rows.append(f"| {pmid_cell} | {title} | {_md_escape_cell(meta)} |")
    return header + "\n".join(rows) if rows else ""


# --- Escaping helpers ------------------------------------------------------


def _md_escape(text: object) -> str:
    if text is None:
        return ""
    s = str(text)
    return s.replace("\\", "\\\\").replace("_", "\\_").replace("*", "\\*")


def _md_escape_paragraph(text: object) -> str:
    """Escape for paragraph body — preserves newlines, neutralizes emphasis."""
    if text is None:
        return ""
    return str(text).replace("\\", "\\\\").replace("*", "\\*")


def _md_escape_inline(text: object) -> str:
    if text is None:
        return ""
    return str(text).replace("\\", "\\\\").replace("*", "\\*").strip()


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

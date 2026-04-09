"""HTML recipe: single-trial deep dive with stacked sections.

Renders as a ``text/html`` artifact. Formerly a React + shadcn Tabs blueprint,
but LibreChat's Sandpack 2.19.8 runtime crashes on React-based artifacts
(see commit history). The rewrite uses plain HTML + Tailwind with a
`<header>` + flat `<section>` stack — no JS dependency, renders in any HTML
artifact sandbox.

Sections (only rendered when the corresponding data is present):
  1. Overview — brief summary text
  2. Design & Endpoints — primary / secondary outcome measures
  3. Eligibility — inclusion / exclusion criteria, age, gender
  4. Arms & Interventions — table of arms
  5. Sites — table of study locations
  6. Publications — linked PubMed papers
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
    nct_id = data.get("nct_id") or "trial"
    title_text = data.get("title") or nct_id

    header_html = _render_header(title_text, nct_id, data)

    sections: list[str] = []
    for section_html in (
        _render_overview(data),
        _render_design(data),
        _render_eligibility(data),
        _render_arms(data),
        _render_sites(data),
        _render_publications(data),
    ):
        if section_html:
            sections.append(section_html)

    body_html = (
        "\n".join(sections)
        if sections
        else (
            '<section><p class="text-sm text-gray-500 italic">'
            "No detailed design, eligibility, arms, sites, or publication data "
            "available for this trial.</p></section>"
        )
    )

    raw = (
        '<div class="p-4 font-sans text-gray-900 space-y-4">\n'
        f"  {header_html}\n"
        f"  {body_html}\n"
        "</div>"
    )

    assert_safe_html(raw)

    return UiPayload(
        recipe="trial_detail_tabs",
        artifact=ArtifactMeta(
            identifier=make_identifier("trial_detail_tabs", nct_id),
            type="text/html",
            title=f"Trial {nct_id}",
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )


# --- Header -----------------------------------------------------------------


def _render_header(title: str, nct_id: str, data: dict[str, Any]) -> str:
    """Top-of-card heading + a single-line metadata strip."""
    nct_url = f"https://clinicaltrials.gov/study/{escape_html(nct_id)}"
    nct_badge = (
        f'<a href="{nct_url}" target="_blank" rel="noopener" '
        f'class="font-mono text-xs px-2 py-0.5 rounded bg-blue-50 text-blue-700 '
        f'border border-blue-200 hover:bg-blue-100">{escape_html(nct_id)}</a>'
    )

    pills: list[str] = []

    phase = data.get("phase")
    if phase:
        pills.append(
            f'<span class="inline-flex items-center text-xs px-2 py-0.5 rounded '
            f'bg-amber-50 text-amber-700 border border-amber-200">'
            f"{escape_html(phase)}</span>"
        )
    status = data.get("status")
    if status:
        pills.append(
            f'<span class="inline-flex items-center text-xs px-2 py-0.5 rounded '
            f'bg-emerald-50 text-emerald-700 border border-emerald-200">'
            f"{escape_html(status)}</span>"
        )

    meta_bits: list[str] = []
    sponsor = data.get("sponsor")
    if sponsor:
        meta_bits.append(escape_html(sponsor))
    enrollment = data.get("enrollment")
    if enrollment is not None:
        meta_bits.append(f"n={escape_html(enrollment)}")
    start = data.get("start_date")
    end = data.get("primary_completion_date")
    if start and end:
        meta_bits.append(f"{escape_html(start)} → {escape_html(end)}")
    elif start:
        meta_bits.append(f"start {escape_html(start)}")
    meta_line = " · ".join(meta_bits)

    pills_html = "".join(f"\n      {p}" for p in pills)

    return f"""<header class="border-b border-gray-200 pb-3">
    <h2 class="text-base font-semibold leading-snug">{escape_html(title)}</h2>
    <div class="mt-2 flex flex-wrap items-center gap-2">
      {nct_badge}{pills_html}
    </div>
    <p class="mt-1 text-xs text-gray-500">{meta_line}</p>
  </header>"""


# --- Sections ---------------------------------------------------------------


def _render_overview(data: dict[str, Any]) -> str:
    summary = data.get("brief_summary") or data.get("description")
    if not summary:
        return ""
    return (
        '<section>\n'
        '    <h3 class="text-sm font-semibold text-gray-900 mb-2">Overview</h3>\n'
        f'    <p class="text-sm text-gray-700 whitespace-pre-wrap">{escape_html(summary)}</p>\n'
        "  </section>"
    )


def _render_design(data: dict[str, Any]) -> str:
    primary = data.get("primary_outcome_measures") or []
    secondary = data.get("secondary_outcome_measures") or []

    if not primary and not secondary:
        return ""

    parts: list[str] = [
        '<section>',
        '    <h3 class="text-sm font-semibold text-gray-900 mb-2">Design &amp; Endpoints</h3>',
    ]

    if primary:
        parts.append('    <p class="text-xs uppercase tracking-wide text-gray-500 mt-2">Primary</p>')
        parts.append('    <ul class="mt-1 space-y-1 text-sm text-gray-700 list-disc list-inside">')
        for o in primary:
            measure = escape_html(o.get("measure", ""))
            time_frame = escape_html(o.get("time_frame", ""))
            if time_frame:
                parts.append(f'      <li>{measure} <span class="text-xs text-gray-500">({time_frame})</span></li>')
            else:
                parts.append(f'      <li>{measure}</li>')
        parts.append("    </ul>")

    if secondary:
        parts.append('    <p class="text-xs uppercase tracking-wide text-gray-500 mt-3">Secondary</p>')
        parts.append('    <ul class="mt-1 space-y-1 text-sm text-gray-700 list-disc list-inside">')
        for o in secondary:
            measure = escape_html(o.get("measure", ""))
            time_frame = escape_html(o.get("time_frame", ""))
            if time_frame:
                parts.append(f'      <li>{measure} <span class="text-xs text-gray-500">({time_frame})</span></li>')
            else:
                parts.append(f'      <li>{measure}</li>')
        parts.append("    </ul>")

    parts.append("  </section>")
    return "\n".join(parts)


def _render_eligibility(data: dict[str, Any]) -> str:
    elig = data.get("eligibility") or {}
    criteria = elig.get("criteria") or ""
    gender = elig.get("gender") or ""
    min_age = elig.get("minimum_age") or ""
    max_age = elig.get("maximum_age") or ""

    if not criteria and not gender and not min_age and not max_age:
        return ""

    meta_bits: list[str] = []
    if gender:
        meta_bits.append(f"<strong>Gender:</strong> {escape_html(gender)}")
    if min_age:
        meta_bits.append(f"<strong>Min age:</strong> {escape_html(min_age)}")
    if max_age:
        meta_bits.append(f"<strong>Max age:</strong> {escape_html(max_age)}")
    meta_html = (
        f'    <p class="text-xs text-gray-600">{" · ".join(meta_bits)}</p>'
        if meta_bits
        else ""
    )

    criteria_html = ""
    if criteria:
        criteria_html = (
            '    <pre class="mt-2 rounded-md bg-gray-50 border border-gray-200 p-3 '
            'text-xs text-gray-700 whitespace-pre-wrap font-sans overflow-x-auto">'
            f"{escape_html(criteria)}</pre>"
        )

    return (
        '<section>\n'
        '    <h3 class="text-sm font-semibold text-gray-900 mb-2">Eligibility</h3>\n'
        + (meta_html + "\n" if meta_html else "")
        + criteria_html
        + "\n  </section>"
    )


def _render_arms(data: dict[str, Any]) -> str:
    arms = data.get("arms") or []
    if not arms:
        return ""

    rows: list[str] = []
    for arm in arms:
        label = escape_html(arm.get("label") or "—")
        arm_type = escape_html(arm.get("type") or "—")
        interventions = arm.get("interventions") or []
        if isinstance(interventions, list):
            interventions_cell = escape_html(
                ", ".join(str(i) for i in interventions if i) or "—"
            )
        else:
            interventions_cell = escape_html(interventions or "—")
        rows.append(
            f"      <tr class=\"border-b border-gray-100\">\n"
            f'        <td class="py-2 pr-3 align-top font-medium">{label}</td>\n'
            f'        <td class="py-2 pr-3 align-top text-gray-600">{arm_type}</td>\n'
            f'        <td class="py-2 pr-3 align-top text-gray-700">{interventions_cell}</td>\n'
            f"      </tr>"
        )

    rows_html = "\n".join(rows)

    return f"""<section>
    <h3 class="text-sm font-semibold text-gray-900 mb-2">Arms &amp; Interventions</h3>
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left text-xs uppercase text-gray-500 border-b border-gray-200">
          <th class="py-2 pr-3">Arm</th>
          <th class="py-2 pr-3">Type</th>
          <th class="py-2 pr-3">Interventions</th>
        </tr>
      </thead>
      <tbody>
{rows_html}
      </tbody>
    </table>
  </section>"""


def _render_sites(data: dict[str, Any]) -> str:
    sites = data.get("sites") or data.get("locations") or []
    if not sites:
        return ""

    # promptclub TrialRecord.locations may be list[str]; detail adapter converts
    # to list[dict]. Handle both shapes.
    if sites and isinstance(sites[0], str):
        items = "\n".join(
            f'      <li class="text-sm text-gray-700">{escape_html(s)}</li>'
            for s in sites
        )
        return (
            '<section>\n'
            '    <h3 class="text-sm font-semibold text-gray-900 mb-2">Sites</h3>\n'
            '    <ul class="space-y-1 list-disc list-inside">\n'
            f"{items}\n"
            "    </ul>\n"
            "  </section>"
        )

    rows: list[str] = []
    for site in sites:
        if not isinstance(site, dict):
            continue
        facility = escape_html(site.get("facility") or "—")
        city = escape_html(site.get("city") or "—")
        country = escape_html(site.get("country") or "—")
        status = escape_html(site.get("status") or "—")
        rows.append(
            f"      <tr class=\"border-b border-gray-100\">\n"
            f'        <td class="py-2 pr-3 align-top">{facility}</td>\n'
            f'        <td class="py-2 pr-3 align-top text-gray-600">{city}</td>\n'
            f'        <td class="py-2 pr-3 align-top text-gray-600">{country}</td>\n'
            f'        <td class="py-2 pr-3 align-top text-gray-600">{status}</td>\n'
            f"      </tr>"
        )
    if not rows:
        return ""
    rows_html = "\n".join(rows)

    return f"""<section>
    <h3 class="text-sm font-semibold text-gray-900 mb-2">Sites</h3>
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left text-xs uppercase text-gray-500 border-b border-gray-200">
          <th class="py-2 pr-3">Facility</th>
          <th class="py-2 pr-3">City</th>
          <th class="py-2 pr-3">Country</th>
          <th class="py-2 pr-3">Status</th>
        </tr>
      </thead>
      <tbody>
{rows_html}
      </tbody>
    </table>
  </section>"""


def _render_publications(data: dict[str, Any]) -> str:
    pubs = data.get("linked_publications") or data.get("publications") or []
    if not pubs:
        return ""

    rows: list[str] = []
    for pub in pubs:
        if not isinstance(pub, dict):
            continue
        pmid = pub.get("pmid") or ""
        if pmid:
            pmid_cell = (
                f'<a href="https://pubmed.ncbi.nlm.nih.gov/{escape_html(pmid)}/" '
                f'target="_blank" rel="noopener" '
                f'class="font-mono text-xs px-2 py-0.5 rounded bg-emerald-50 '
                f'text-emerald-700 border border-emerald-200 hover:bg-emerald-100">'
                f"{escape_html(pmid)}</a>"
            )
        else:
            pmid_cell = '<span class="text-xs text-gray-400">—</span>'

        title = escape_html(_truncate(pub.get("title"), 80)) or "—"
        journal = pub.get("journal") or ""
        year = pub.get("year") or ""
        meta = escape_html(
            " · ".join(p for p in [journal, str(year) if year else ""] if p) or "—"
        )
        rows.append(
            f"      <tr class=\"border-b border-gray-100\">\n"
            f'        <td class="py-2 pr-3 align-top">{pmid_cell}</td>\n'
            f'        <td class="py-2 pr-3 align-top text-gray-700">{title}</td>\n'
            f'        <td class="py-2 pr-3 align-top text-gray-500 text-xs">{meta}</td>\n'
            f"      </tr>"
        )
    if not rows:
        return ""
    rows_html = "\n".join(rows)

    return f"""<section>
    <h3 class="text-sm font-semibold text-gray-900 mb-2">Linked Publications</h3>
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left text-xs uppercase text-gray-500 border-b border-gray-200">
          <th class="py-2 pr-3">PMID</th>
          <th class="py-2 pr-3">Title</th>
          <th class="py-2 pr-3">Journal · Year</th>
        </tr>
      </thead>
      <tbody>
{rows_html}
      </tbody>
    </table>
  </section>"""


# --- Helpers ---------------------------------------------------------------


def _truncate(text: str | None, max_len: int) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"

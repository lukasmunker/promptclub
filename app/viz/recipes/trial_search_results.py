"""HTML recipe: a card list of clinical trials or publications.

Renders as a ``text/html`` artifact — LibreChat mounts it in its HTML artifact
sandbox with the Tailwind Play CDN preloaded, so utility classes work out of
the box.

Caps at 25 cards and appends a "N more" footer linking to the full
ClinicalTrials.gov search URL when there are more results.
"""

from __future__ import annotations

from typing import Any

from app.viz.contract import ArtifactMeta, UiPayload
from app.viz.theme import (
    BADGE_MUTED,
    BADGE_NCT,
    BADGE_PMID,
    CARD_STYLE_BLOCK,
    CARD_WRAPPER,
    PILL_PHASE,
)
from app.viz.utils.html import assert_safe_html, escape_html
from app.viz.utils.identifiers import make_identifier

__all__ = ["build", "MAX_CARDS"]

MAX_CARDS = 25


def build(
    data: dict[str, Any],
    sources: list[Any] | None = None,
) -> UiPayload:
    """Build the HTML card list for a search_clinical_trials / search_publications result."""
    results: list[dict[str, Any]] = data.get("results") or []
    total = data.get("total", len(results))
    query = data.get("query") or data.get("title") or "search"
    title = data.get("title") or _default_title(data)

    shown = results[:MAX_CARDS]
    more = max(total - len(shown), 0)

    cards_html = "\n".join(_render_card(hit) for hit in shown)
    footer_html = _render_more_footer(more, data.get("search_url")) if more > 0 else ""

    raw = (
        f"{CARD_STYLE_BLOCK}\n"
        f'<div class="{CARD_WRAPPER}">\n'
        f'<div class="grid gap-3">\n'
        f"{cards_html}\n"
        f"{footer_html}"
        f"</div>\n"
        f"</div>"
    )

    assert_safe_html(raw)

    return UiPayload(
        recipe="trial_search_results",
        artifact=ArtifactMeta(
            identifier=make_identifier("trial_search_results", query),
            type="html",
            title=title,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )


# --- Card templates ---------------------------------------------------------


def _render_card(hit: dict[str, Any]) -> str:
    """One card per trial or publication.

    Recognized fields (all optional except `title` or `nct_id`/`pmid`):
        - nct_id (ClinicalTrials.gov) OR pmid (PubMed)
        - title, phase, status, sponsor, enrollment,
          primary_completion_date, snippet / abstract, source_url
    """
    badge_html = _id_badge(hit)

    phase = hit.get("phase")
    phase_pill = (
        f'<span class="{PILL_PHASE}">{escape_html(phase)}</span>'
        if phase
        else ""
    )

    title = hit.get("title") or "(untitled)"
    sponsor = hit.get("sponsor")
    status = hit.get("status")
    enrollment = hit.get("enrollment")
    primary_completion = hit.get("primary_completion_date")

    meta_parts: list[str] = []
    if sponsor:
        meta_parts.append(escape_html(sponsor))
    if status:
        meta_parts.append(escape_html(status))
    if enrollment is not None:
        meta_parts.append(f"n={escape_html(enrollment)}")
    if primary_completion:
        meta_parts.append(f"completion {escape_html(primary_completion)}")
    meta_line = " · ".join(meta_parts)

    snippet = hit.get("snippet") or hit.get("abstract")
    snippet_html = (
        f'<p class="mt-2 text-sm text-gray-600 line-clamp-3">'
        f"{escape_html(_truncate(snippet, 260))}</p>"
        if snippet
        else ""
    )

    return f"""<article class="rounded-lg border border-gray-200 bg-white p-4 hover:shadow-sm transition-shadow">
  <div class="flex items-start justify-between gap-3">
    {badge_html}
    {phase_pill}
  </div>
  <h3 class="mt-2 font-semibold text-gray-900 leading-snug">{escape_html(title)}</h3>
  <p class="mt-1 text-xs text-gray-500">{meta_line}</p>
  {snippet_html}
</article>"""


def _id_badge(hit: dict[str, Any]) -> str:
    nct = hit.get("nct_id")
    pmid = hit.get("pmid")
    if nct:
        href = f"https://clinicaltrials.gov/study/{escape_html(nct)}"
        return (
            f'<a href="{href}" target="_blank" rel="noopener" '
            f'class="{BADGE_NCT}">{escape_html(nct)}</a>'
        )
    if pmid:
        href = f"https://pubmed.ncbi.nlm.nih.gov/{escape_html(pmid)}/"
        return (
            f'<a href="{href}" target="_blank" rel="noopener" '
            f'class="{BADGE_PMID}">PMID {escape_html(pmid)}</a>'
        )
    return f'<span class="{BADGE_MUTED}">(no id)</span>'


def _render_more_footer(more: int, search_url: str | None) -> str:
    label = f"… and {more} more"
    if search_url:
        return (
            f'<a href="{escape_html(search_url)}" target="_blank" rel="noopener" '
            f'class="block rounded-lg border border-dashed border-gray-300 bg-gray-50 '
            f'p-4 text-center text-sm text-gray-600 hover:bg-gray-100 hover:text-gray-900">'
            f"{escape_html(label)} →</a>"
        )
    return (
        f'<div class="rounded-lg border border-dashed border-gray-300 bg-gray-50 '
        f'p-4 text-center text-sm text-gray-600">{escape_html(label)}</div>'
    )


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

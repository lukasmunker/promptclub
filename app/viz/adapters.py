"""Adapter layer: promptclub model shapes → yallah_viz recipe shapes.

promptclub returns plain Pydantic ``model_dump()`` dicts whose field names
don't exactly match what the yallah_viz recipes expect. Rather than rewrite
the recipes, we normalize here.

This module also converts promptclub's ``Citation`` objects into the
``Source`` entries that yallah_viz envelopes use, filling in the missing
``retrieved_at`` timestamp and mapping the free-form ``source`` string to
the ``SourceKind`` literal.

Usage (from ``app/main.py``)::

    from app.viz.adapters import build_response_from_promptclub

    @mcp.tool()
    async def search_trials(disease_query: str, prefer_visualization: str = "auto"):
        result = await orchestrator.search_trials_with_publications(...)
        return build_response_from_promptclub(
            tool_name="search_trials",
            promptclub_data=result.model_dump(),
            prefer_visualization=prefer_visualization,
        )
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.viz.build import build_response
from app.viz.contract import PreferVisualization

__all__ = ["build_response_from_promptclub", "normalize_citations_to_sources"]


# Map promptclub's free-form `source` strings (as they appear in Citation.source
# and Record.source) to the yallah_viz SourceKind literal.
_SOURCE_KIND_MAP = {
    "clinicaltrials.gov": "clinicaltrials.gov",
    "clinicaltrialsv2": "clinicaltrials.gov",
    "pubmed": "pubmed",
    "openfda": "openfda",
    "open targets": "opentargets",
    "opentargets": "opentargets",
    "vertex google search": "web",
    "google": "web",
    "web": "web",
}


def _normalize_source_kind(source: str | None) -> str:
    if not source:
        return "web"
    key = source.strip().lower()
    return _SOURCE_KIND_MAP.get(key, "web")


def normalize_citations_to_sources(
    citations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Turn promptclub Citation dicts into yallah_viz Source dicts.

    Input shape (from Citation.model_dump()):
        {source: str, id: str | None, url: str | None, title: str | None}

    Output shape (Source):
        {kind: SourceKind, id: str, url: str, retrieved_at: ISO8601}

    Citations without a URL are dropped (they can't be cited usefully).
    """
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        url = citation.get("url")
        if not url:
            continue
        kind = _normalize_source_kind(citation.get("source"))
        identifier = citation.get("id") or citation.get("title") or url
        key = (kind, str(identifier))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "kind": kind,
                "id": str(identifier),
                "url": url,
                "retrieved_at": now,
            }
        )
    return out


# --- Per-tool normalizers ---------------------------------------------------


def _flatten_phase(phase_field: Any) -> str | None:
    """TrialRecord.phase is list[str]; recipes expect a single string."""
    if isinstance(phase_field, list):
        if not phase_field:
            return None
        return "/".join(p for p in phase_field if p)
    if isinstance(phase_field, str) and phase_field:
        return phase_field
    return None


def _normalize_trial_hit(trial: dict[str, Any]) -> dict[str, Any]:
    """Normalize a promptclub TrialRecord dict into the shape expected by
    trial_search_results / sponsor_pipeline_cards."""
    snippet = None
    endpoints = trial.get("primary_endpoints") or []
    if endpoints and isinstance(endpoints, list):
        snippet = "; ".join(str(e) for e in endpoints[:2])
    elif trial.get("official_title") and trial.get("official_title") != trial.get("title"):
        snippet = trial.get("official_title")

    return {
        "nct_id": trial.get("nct_id"),
        "title": trial.get("title"),
        "phase": _flatten_phase(trial.get("phase")),
        "status": trial.get("status"),
        "sponsor": trial.get("sponsor"),
        "enrollment": trial.get("enrollment"),
        "primary_completion_date": trial.get("completion_date"),
        "start_date": trial.get("start_date"),
        "snippet": snippet,
    }


def _normalize_publication_hit(pub: dict[str, Any]) -> dict[str, Any]:
    """Normalize a PublicationRecord dict into a search-results hit shape."""
    # Repurpose `sponsor`/`status` fields for journal + pub date so the
    # existing HTML card template lights them up.
    meta_bits: list[str] = []
    if pub.get("journal"):
        meta_bits.append(str(pub["journal"]))
    if pub.get("pub_date"):
        meta_bits.append(str(pub["pub_date"]))

    return {
        "pmid": pub.get("pmid"),
        "title": pub.get("title"),
        "snippet": pub.get("abstract"),
        "sponsor": " · ".join(meta_bits) if meta_bits else None,
    }


def _normalize_web_hit(row: dict[str, Any]) -> dict[str, Any]:
    """WebContextRecord → search-results hit.

    WebContextRecord only has {source, answer, citations} — repurpose `answer`
    as the snippet and the first citation as title/url.
    """
    cites = row.get("citations") or []
    first_cite = cites[0] if cites else {}
    return {
        "title": (first_cite.get("title") if isinstance(first_cite, dict) else None)
        or "Web context",
        "snippet": row.get("answer"),
        "sponsor": (first_cite.get("source") if isinstance(first_cite, dict) else None)
        or "Vertex Google Search",
    }


def _normalize_trial_detail(detail: dict[str, Any]) -> dict[str, Any]:
    """Normalize a TrialRecord dict into the shape expected by trial_detail_tabs.

    promptclub doesn't have structured `arms`, `sites`, `linked_publications`,
    `primary_outcome_measures` fields — it has free-form strings / lists. We
    convert them into the structured shapes the recipe expects, filling in the
    available data. Missing data leads to tabs being omitted (the recipe
    handles this).
    """
    locations = detail.get("locations") or []
    sites: list[dict[str, Any]] = []
    if isinstance(locations, list):
        for loc in locations[:50]:
            if not loc:
                continue
            sites.append({"facility": str(loc), "city": "", "country": "", "status": ""})

    interventions = detail.get("interventions") or []
    arms: list[dict[str, Any]] = []
    if isinstance(interventions, list) and interventions:
        arms.append(
            {
                "label": "Study Interventions",
                "type": detail.get("study_type") or "",
                "description": "",
                "interventions": [str(i) for i in interventions],
            }
        )

    primary_endpoints = detail.get("primary_endpoints") or []
    primary_outcomes: list[dict[str, Any]] = []
    if isinstance(primary_endpoints, list):
        for ep in primary_endpoints:
            if not ep:
                continue
            primary_outcomes.append({"measure": str(ep), "time_frame": ""})

    # Merge inclusion + exclusion criteria into the structured eligibility shape
    inc = detail.get("inclusion_criteria") or ""
    exc = detail.get("exclusion_criteria") or ""
    criteria_parts: list[str] = []
    if inc:
        criteria_parts.append(f"Inclusion Criteria:\n{inc}")
    if exc:
        criteria_parts.append(f"Exclusion Criteria:\n{exc}")
    eligibility = (
        {
            "criteria": "\n\n".join(criteria_parts),
            "gender": "",
            "minimum_age": "",
            "maximum_age": "",
        }
        if criteria_parts
        else None
    )

    return {
        "nct_id": detail.get("nct_id"),
        "title": detail.get("title"),
        "phase": _flatten_phase(detail.get("phase")),
        "status": detail.get("status"),
        "sponsor": detail.get("sponsor"),
        "enrollment": detail.get("enrollment"),
        "start_date": detail.get("start_date"),
        "primary_completion_date": detail.get("completion_date"),
        "brief_summary": detail.get("official_title"),
        "primary_outcome_measures": primary_outcomes,
        "secondary_outcome_measures": [],
        "eligibility": eligibility,
        "arms": arms,
        "sites": sites,
        "linked_publications": [],
    }


def _normalize_target_associations(
    rows: list[dict[str, Any]], disease_id: str | None
) -> dict[str, Any]:
    """Normalize a list of TargetAssociationRecord dicts into the shape the
    target_associations_table recipe expects."""
    return {
        "disease_id": disease_id,
        "disease_name": rows[0].get("disease_name") if rows else None,
        "associations": [
            {
                "target_symbol": r.get("target_symbol"),
                "target_name": r.get("target_name"),
                "target_id": r.get("target_id"),
                "score": r.get("score"),
            }
            for r in rows
            if r.get("target_symbol") or r.get("target_name")
        ],
    }


# --- Top-level dispatcher ---------------------------------------------------


def build_response_from_promptclub(
    tool_name: str,
    promptclub_data: dict[str, Any],
    prefer_visualization: PreferVisualization = "auto",
    *,
    query: str | None = None,
    disease_id: str | None = None,
) -> dict[str, Any]:
    """Convert a promptclub tool result into a yallah_viz envelope.

    This is the single entrypoint each wired tool calls. It:

    1. Normalizes ``promptclub_data`` into the shape yallah_viz recipes expect.
    2. Extracts ``citations`` from the data (and from any nested records) into
       the ``Source[]`` array the envelope needs.
    3. Delegates to ``build_response()`` which picks the recipe and validates.

    Args:
        tool_name: The MCP tool's name (drives recipe selection).
        promptclub_data: The raw dict returned by the orchestrator / adapter.
        prefer_visualization: LLM override.
        query: Optional query string for search tools (used in titles/identifiers).
        disease_id: Optional EFO ID for get_target_context.

    Returns:
        A dict ready to be ``json.dumps``'d and returned by the MCP tool.
    """
    if tool_name == "search_trials":
        return _handle_search_trials(promptclub_data, prefer_visualization, query)

    if tool_name == "get_trial_details":
        return _handle_get_trial_details(promptclub_data, prefer_visualization)

    if tool_name == "search_publications":
        return _handle_search_publications(promptclub_data, prefer_visualization, query)

    if tool_name == "web_context_search":
        return _handle_web_context(promptclub_data, prefer_visualization, query)

    if tool_name == "get_target_context":
        return _handle_get_target_context(
            promptclub_data, prefer_visualization, disease_id
        )

    if tool_name == "build_trial_comparison":
        return _handle_build_trial_comparison(
            promptclub_data, prefer_visualization, query
        )

    if tool_name == "analyze_whitespace":
        return _handle_analyze_whitespace(promptclub_data, prefer_visualization)

    # Unknown tools (resolve_disease, get_regulatory_context, test_data_sources,
    # analyze_indication_landscape, get_sponsor_overview, anything future) get
    # a plain-text envelope: no ui block, render_hint asks the LLM to answer
    # from data, and we forward whatever citations exist.
    citations = _extract_all_citations(promptclub_data)
    return build_response(
        tool_name=tool_name,  # unknown → decision.py returns skip
        data=promptclub_data,
        sources=normalize_citations_to_sources(citations),
        prefer_visualization=prefer_visualization,
    )


# --- Per-tool handlers ------------------------------------------------------


def _handle_search_trials(
    data: dict[str, Any],
    prefer: PreferVisualization,
    query: str | None,
) -> dict[str, Any]:
    trials_raw = data.get("trials") or []
    normalized_results = [_normalize_trial_hit(t) for t in trials_raw]

    recipe_data = {
        "query": query or "oncology trials",
        "title": data.get("summary") or "Clinical Trials",
        "results": normalized_results,
        "total": len(normalized_results),
    }

    citations = _extract_all_citations(data)
    return build_response(
        tool_name="search_clinical_trials",  # yallah_viz recipe key
        data=recipe_data,
        sources=normalize_citations_to_sources(citations),
        prefer_visualization=prefer,
    )


def _handle_get_trial_details(
    data: dict[str, Any],
    prefer: PreferVisualization,
) -> dict[str, Any]:
    # promptclub returns {"found": bool, "trial": {...}} or {"found": False, "nct_id": ...}
    if not data.get("found") or not data.get("trial"):
        return build_response(
            tool_name="get_trial_details",
            data=data,
            sources=[],
            prefer_visualization="never",  # force text answer
        )

    trial = data["trial"]
    normalized = _normalize_trial_detail(trial)
    citations = trial.get("citations") or []
    return build_response(
        tool_name="get_trial_details",
        data=normalized,
        sources=normalize_citations_to_sources(citations),
        prefer_visualization=prefer,
    )


def _handle_search_publications(
    data: dict[str, Any],
    prefer: PreferVisualization,
    query: str | None,
) -> dict[str, Any]:
    pubs_raw = data.get("results") or []
    normalized_results = [_normalize_publication_hit(p) for p in pubs_raw]

    recipe_data = {
        "query": query or "publications",
        "title": "Publications",
        "results": normalized_results,
        "total": len(normalized_results),
    }

    citations = _extract_all_citations(data)
    return build_response(
        tool_name="search_publications",
        data=recipe_data,
        sources=normalize_citations_to_sources(citations),
        prefer_visualization=prefer,
    )


def _handle_web_context(
    data: dict[str, Any],
    prefer: PreferVisualization,
    query: str | None,
) -> dict[str, Any]:
    rows_raw = data.get("results") or []
    normalized_results = [_normalize_web_hit(r) for r in rows_raw]

    recipe_data = {
        "query": query or "web context",
        "title": "Web Context Results",
        "results": normalized_results,
        "total": len(normalized_results),
    }

    citations = _extract_all_citations(data)
    return build_response(
        tool_name="search_clinical_trials",  # reuse trial_search_results recipe
        data=recipe_data,
        sources=normalize_citations_to_sources(citations),
        prefer_visualization=prefer,
    )


def _handle_get_target_context(
    data: dict[str, Any],
    prefer: PreferVisualization,
    disease_id: str | None,
) -> dict[str, Any]:
    rows_raw = data.get("results") or []
    recipe_data = _normalize_target_associations(rows_raw, disease_id)

    citations = _extract_all_citations(data)
    return build_response(
        tool_name="get_target_context",
        data=recipe_data,
        sources=normalize_citations_to_sources(citations),
        prefer_visualization=prefer,
    )


def _handle_build_trial_comparison(
    data: dict[str, Any],
    prefer: PreferVisualization,
    query: str | None,
) -> dict[str, Any]:
    """build_trial_comparison returns ``{count, trials, errors}``. Each trial
    is a TrialRecord dict with ``start_date`` + ``completion_date`` fields,
    which the trial_timeline_gantt recipe needs as ``start_date`` +
    ``primary_completion_date`` (Mermaid gantt uses primary completion as the
    end-of-bar marker for clarity)."""
    trials_raw = data.get("trials") or []
    normalized_trials: list[dict[str, Any]] = []
    for t in trials_raw:
        normalized_trials.append(
            {
                "nct_id": t.get("nct_id"),
                "title": t.get("title"),
                "acronym": t.get("title"),  # promptclub has no separate acronym field
                "sponsor": t.get("sponsor") or "(unknown)",
                "phase": _flatten_phase(t.get("phase")),
                "status": t.get("status"),
                "enrollment": t.get("enrollment"),
                "start_date": t.get("start_date"),
                "primary_completion_date": t.get("completion_date"),
            }
        )

    recipe_data = {
        "title": "Trial Comparison",
        "query": query or "trial-comparison",
        "trials": normalized_trials,
    }

    citations = _extract_all_citations(data)
    return build_response(
        tool_name="build_trial_comparison",
        data=recipe_data,
        sources=normalize_citations_to_sources(citations),
        prefer_visualization=prefer,
    )


def _handle_analyze_whitespace(
    data: dict[str, Any],
    prefer: PreferVisualization,
) -> dict[str, Any]:
    """analyze_whitespace returns ``{condition, trial_counts_by_phase,
    trial_counts_by_status, pubmed_publications_3yr, fda_label_records,
    identified_whitespace}``. The shape is exactly what whitespace_card
    expects, so we forward it (with a no-op normalization for safety)."""
    recipe_data = {
        "condition": data.get("condition"),
        "trial_counts_by_phase": data.get("trial_counts_by_phase") or {},
        "trial_counts_by_status": data.get("trial_counts_by_status") or {},
        "pubmed_publications_3yr": data.get("pubmed_publications_3yr"),
        "fda_label_records": data.get("fda_label_records"),
        "identified_whitespace": data.get("identified_whitespace") or [],
    }

    citations = _extract_all_citations(data)
    return build_response(
        tool_name="analyze_whitespace",
        data=recipe_data,
        sources=normalize_citations_to_sources(citations),
        prefer_visualization=prefer,
    )


# --- Citation extraction ----------------------------------------------------


def _extract_all_citations(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull every Citation dict out of a (potentially nested) promptclub response.

    Walks top-level, ``trials``, ``publications``, ``results``, ``targets``,
    ``regulatory``, ``web_context`` lists. Each element's ``citations`` field
    is harvested.
    """
    bag: list[dict[str, Any]] = []

    top_citations = data.get("citations")
    if isinstance(top_citations, list):
        bag.extend(c for c in top_citations if isinstance(c, dict))

    for key in ("trials", "publications", "results", "targets", "regulatory", "web_context"):
        items = data.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            cites = item.get("citations")
            if isinstance(cites, list):
                bag.extend(c for c in cites if isinstance(c, dict))

    return bag

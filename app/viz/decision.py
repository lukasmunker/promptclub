"""Decision logic — should the MCP response get a visualization?

Pure function, no I/O, no side effects. Given a tool name and its raw data
dict, return a ``Decision`` telling the dispatcher which recipe to use (or to
skip visualization entirely and fall back to a text answer).

See the plan's "should we visualize?" table for the exact heuristics.
"""

from __future__ import annotations

from typing import Any

from app.viz.contract import Decision, PreferVisualization
from app.viz.utils.mermaid import is_valid_iso_date

__all__ = ["should_visualize", "MAX_TRIALS_IN_GANTT"]

# Cardinality threshold: beyond this many trials a Mermaid gantt becomes
# illegible, so we auto-fall back to the HTML sponsor_pipeline_cards recipe.
MAX_TRIALS_IN_GANTT = 15


def should_visualize(
    tool_name: str,
    data: dict[str, Any],
    prefer_visualization: PreferVisualization = "auto",
) -> Decision:
    """Decide whether and how to visualize a tool response.

    Args:
        tool_name: The MCP tool that produced the data. Known values:
            ``search_clinical_trials``, ``search_publications``,
            ``get_trial_details``, ``get_indication_landscape``,
            ``compare_trials``. Unknown tool names always skip visualization.
        data: The tool's raw result dict (tool-specific shape).
        prefer_visualization: LLM-set override. ``"auto"`` follows heuristics,
            ``"always"`` forces a recipe (best effort), ``"never"`` forces
            skip, ``"cards"`` forces the HTML card alternative for graph data.

    Returns:
        A ``Decision`` — either ``Decision.use(recipe_name)`` or
        ``Decision.skip(reason)``.
    """
    if prefer_visualization == "never":
        return Decision.skip("user requested text-only answer")

    if tool_name in ("search_clinical_trials", "search_publications"):
        return _decide_search(data, prefer_visualization)

    if tool_name == "get_trial_details":
        return _decide_trial_details(data, prefer_visualization)

    if tool_name == "get_indication_landscape":
        return _decide_indication_landscape(data, prefer_visualization)

    if tool_name == "compare_trials":
        return _decide_compare_trials(data, prefer_visualization)

    if tool_name == "get_target_context":
        return _decide_target_context(data, prefer_visualization)

    if tool_name == "build_trial_comparison":
        return _decide_compare_trials(data, prefer_visualization)

    if tool_name == "analyze_whitespace":
        return _decide_whitespace(data, prefer_visualization)

    # analyze_indication_landscape and get_sponsor_overview return flat
    # aggregate counts that don't fit the existing recipes — text-only for
    # now. They can graduate to a recipe in a follow-up.
    if tool_name in ("analyze_indication_landscape", "get_sponsor_overview"):
        if prefer_visualization == "always":
            return Decision.skip(
                "no recipe registered for this tool — text answer is the only path"
            )
        return Decision.skip("flat aggregate counts render best as plain text")

    # Unknown tool — safer to let the LLM answer as text.
    return Decision.skip(f"no visualization registered for tool '{tool_name}'")


def _decide_whitespace(
    data: dict[str, Any], prefer: PreferVisualization
) -> Decision:
    """analyze_whitespace returns counts by phase + identified gap signals.
    Worth visualizing whenever there's any phase / status data OR identified
    whitespace signals."""
    if prefer == "always":
        return Decision.use("whitespace_card", "forced by prefer_visualization")

    phase = data.get("trial_counts_by_phase") or {}
    status = data.get("trial_counts_by_status") or {}
    signals = data.get("identified_whitespace") or []

    has_any_count = any(v for v in phase.values()) or any(v for v in status.values())
    has_any_signal = bool(signals)

    if not has_any_count and not has_any_signal:
        return Decision.skip("no phase counts and no whitespace signals")

    return Decision.use(
        "whitespace_card",
        f"phases={len(phase)} signals={len(signals)}",
    )


def _decide_target_context(
    data: dict[str, Any], prefer: PreferVisualization
) -> Decision:
    """Target-disease associations from Open Targets. Worth visualizing
    whenever we have at least 2 targets to rank."""
    associations = data.get("associations") or []
    if prefer == "always":
        return Decision.use(
            "target_associations_table", "forced by prefer_visualization"
        )
    if len(associations) < 2:
        return Decision.skip("need at least 2 targets for a meaningful table")
    return Decision.use(
        "target_associations_table", f"{len(associations)} associations"
    )


# --- Per-tool helpers -------------------------------------------------------


def _decide_search(
    data: dict[str, Any], prefer: PreferVisualization
) -> Decision:
    results = data.get("results") or []
    if prefer == "always":
        return Decision.use("trial_search_results", "forced by prefer_visualization")
    if len(results) == 0:
        return Decision.skip("no results matched the query")
    if len(results) == 1 and _is_trivial_hit(results[0]):
        return Decision.skip("single trivial hit, text answer is sufficient")
    if len(results) >= 2:
        return Decision.use(
            "trial_search_results",
            f"{len(results)} hits warrant a card list",
        )
    return Decision.skip("only one hit with partial data")


def _decide_trial_details(
    data: dict[str, Any], prefer: PreferVisualization
) -> Decision:
    if prefer == "always":
        return Decision.use("trial_detail_tabs", "forced by prefer_visualization")
    facets = _count_facets(data)
    if facets == 0:
        return Decision.skip("sparse trial record, text answer is sufficient")
    return Decision.use(
        "trial_detail_tabs", f"trial has {facets} rich facets"
    )


def _decide_indication_landscape(
    data: dict[str, Any], prefer: PreferVisualization
) -> Decision:
    if prefer == "always":
        return Decision.use("indication_dashboard", "forced by prefer_visualization")

    phase_dist = data.get("phase_distribution") or []
    sponsors = data.get("top_sponsors") or []
    status_breakdown = data.get("status_breakdown") or []

    # Trivial aggregates → no chart is more useful than an empty chart.
    if not phase_dist and not sponsors and not status_breakdown:
        return Decision.skip("no aggregate data available")

    if len(phase_dist) <= 1 and len(sponsors) <= 1:
        return Decision.skip(
            "single-dimension aggregate, text answer is clearer than a chart"
        )

    return Decision.use(
        "indication_dashboard",
        f"phases={len(phase_dist)} sponsors={len(sponsors)}",
    )


def _decide_compare_trials(
    data: dict[str, Any], prefer: PreferVisualization
) -> Decision:
    trials = data.get("trials") or []
    num = len(trials)

    if prefer == "cards":
        if num == 0:
            return Decision.skip("no trials to compare")
        return Decision.use(
            "sponsor_pipeline_cards", "user requested cards view"
        )

    if prefer == "always":
        recipe = (
            "sponsor_pipeline_cards"
            if num > MAX_TRIALS_IN_GANTT
            else "trial_timeline_gantt"
        )
        return Decision.use(recipe, "forced by prefer_visualization")

    if num < 2:
        return Decision.skip("nothing to compare with fewer than 2 trials")

    # Need at least start and primary completion dates for a gantt to make
    # sense — and they must be valid ISO dates because the gantt recipe
    # filters with the same strict check. A truthy-only check here would let
    # year-only or year-month dates through, the recipe would drop them, and
    # we'd end up with a 1-trial "comparison" gantt (or an empty placeholder).
    datable = [
        t
        for t in trials
        if is_valid_iso_date(t.get("start_date"))
        and is_valid_iso_date(t.get("primary_completion_date"))
    ]
    if len(datable) < 2:
        # Fall back to cards if not enough trials have ISO dates
        return Decision.use(
            "sponsor_pipeline_cards",
            f"only {len(datable)} trial(s) with valid ISO dates, using cards",
        )

    if num > MAX_TRIALS_IN_GANTT:
        return Decision.use(
            "sponsor_pipeline_cards",
            f"{num} trials exceed gantt cap ({MAX_TRIALS_IN_GANTT})",
        )

    return Decision.use("trial_timeline_gantt", f"comparing {num} trials")


# --- Shape helpers ----------------------------------------------------------


def _is_trivial_hit(hit: dict[str, Any]) -> bool:
    """A hit is trivial if it's essentially just an ID + title, nothing else."""
    rich_fields = ("sponsor", "phase", "status", "enrollment", "snippet", "abstract")
    return not any(hit.get(f) for f in rich_fields)


def _count_facets(detail: dict[str, Any]) -> int:
    """Count how many 'rich' facets a trial detail response has. Zero facets
    means the record is too sparse to justify a tabbed detail view."""
    facets = 0
    if detail.get("arms"):
        facets += 1
    if detail.get("endpoints") or detail.get("primary_outcome_measures"):
        facets += 1
    if detail.get("eligibility"):
        facets += 1
    if detail.get("sites") or detail.get("locations"):
        facets += 1
    if detail.get("publications") or detail.get("linked_publications"):
        facets += 1
    if detail.get("interventions"):
        facets += 1
    return facets

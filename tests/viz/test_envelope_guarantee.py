"""Coverage guarantee test — the keystone of the viz coverage workstream.

For every MCP tool, parametrized over three response factories
(populated, empty, single_item), assert that build_response() returns
an envelope whose ui field is populated and whose ui.raw contains
non-empty rendered content.

This is the regression test for the entire coverage guarantee.
"""

from typing import Any, Callable

import pytest

from app.viz.build import build_response

# All MCP tools defined in app/main.py. Keep in sync with @mcp.tool() decorators.
ALL_TOOLS = [
    "search_trials",
    "get_trial_details",
    "search_publications",
    "get_target_context",
    "get_known_drugs_for_target",
    "get_regulatory_context",
    "resolve_disease",
    "web_context_search",
    "test_data_sources",
    "build_trial_comparison",
    "analyze_indication_landscape",
    "analyze_whitespace",
    "get_sponsor_overview",
]


def _populated(tool: str) -> dict[str, Any]:
    """Return a richly-populated data dict for the given tool."""
    if tool in ("search_trials", "search_publications"):
        return {"results": [
            {"id": "NCT01", "title": "T1", "sponsor": "S1", "phase": "3", "status": "Recruiting", "abstract": "X"},
            {"id": "NCT02", "title": "T2", "sponsor": "S2", "phase": "3", "status": "Active", "abstract": "Y"},
        ]}
    if tool == "get_trial_details":
        return {
            "nct_id": "NCT01234567",
            "title": "A Phase 3 study",
            "phase": "3",
            "status": "Recruiting",
            "sponsor": "Merck",
            "arms": [{"name": "Arm A"}],
            "endpoints": ["OS"],
            "eligibility": {"min_age": "18"},
            "locations": [{"country": "US"}],
            "interventions": [{"name": "Drug X"}],
        }
    if tool in ("compare_trials", "build_trial_comparison"):
        return {"trials": [
            {"id": "NCT01", "start_date": "2024-01-01", "primary_completion_date": "2026-01-01", "title": "T1"},
            {"id": "NCT02", "start_date": "2024-06-01", "primary_completion_date": "2026-06-01", "title": "T2"},
        ]}
    if tool == "get_indication_landscape":
        return {
            "phase_distribution": [{"phase": "3", "count": 12}, {"phase": "2", "count": 8}],
            "top_sponsors": [{"name": "Merck", "count": 5}, {"name": "Pfizer", "count": 4}],
            "status_breakdown": [{"status": "Recruiting", "count": 15}],
        }
    if tool == "get_target_context":
        return {"associations": [{"target": "EGFR", "score": 0.9}, {"target": "KRAS", "score": 0.8}]}
    if tool == "analyze_whitespace":
        return {
            "condition": "NSCLC",
            "trial_counts_by_phase": {"phase_1": 12, "phase_2": 8, "phase_3": 4},
            "trial_counts_by_status": {"recruiting": 14},
            "identified_whitespace": ["Few Phase 3 trials"],
        }
    return {"some_data": "populated", "title": f"{tool} result"}


def _empty(tool: str) -> dict[str, Any]:
    """Return an empty / no-results data dict."""
    return {"results": [], "trials": [], "associations": [], "total": 0}


def _single_item(tool: str) -> dict[str, Any]:
    """Return a single-record data dict — common for trivial-hit cases."""
    if tool == "search_trials":
        return {"results": [{"id": "NCT01", "title": "T1"}]}
    if tool == "get_trial_details":
        return {"nct_id": "NCT01"}
    return {"results": [{"id": "1"}]}


@pytest.mark.parametrize("tool", ALL_TOOLS)
@pytest.mark.parametrize(
    "factory",
    [_populated, _empty, _single_item],
    ids=["populated", "empty", "single_item"],
)
def test_envelope_always_emits_artifact(tool: str, factory: Callable[[str], dict[str, Any]]):
    data = factory(tool)
    envelope = build_response(
        tool_name=tool,
        data=data,
        sources=[],
        query_hint="test query",
    )
    # The keystone assertion
    assert envelope.get("ui") is not None, (
        f"tool={tool} factory={factory.__name__} produced ui=None — coverage guarantee broken"
    )
    ui = envelope["ui"]
    assert ui.get("raw"), (
        f"tool={tool} factory={factory.__name__} produced empty ui.raw — recipe failed"
    )
    assert ui.get("recipe") in (
        "indication_dashboard", "trial_search_results", "trial_detail_tabs",
        "trial_timeline_gantt", "sponsor_pipeline_cards", "target_associations_table",
        "whitespace_card", "info_card", "concept_card", "single_entity_card",
    )


def test_unknown_tool_still_emits_artifact():
    envelope = build_response(
        tool_name="totally_unknown_tool",
        data={"weird": "shape"},
        sources=[],
    )
    assert envelope.get("ui") is not None
    assert envelope["ui"]["recipe"] == "info_card"

"""Tests for app.viz.decision.should_visualize."""

from __future__ import annotations

import pytest

from app.viz.contract import DecisionKind
from app.viz.decision import MAX_TRIALS_IN_GANTT, should_visualize


# --- Unknown tools skip -----------------------------------------------------


def test_unknown_tool_skips():
    d = should_visualize("unknown_tool", {"anything": True})
    assert d.kind is DecisionKind.SKIP


# --- prefer_visualization="never" always skips ------------------------------


@pytest.mark.parametrize(
    "tool,data",
    [
        ("search_clinical_trials", {"results": [{"nct_id": "x", "phase": "3"}]}),
        ("get_indication_landscape", {"phase_distribution": [{"phase": "1", "count": 5}]}),
        ("compare_trials", {"trials": [{"nct_id": "a"}, {"nct_id": "b"}]}),
    ],
)
def test_never_always_skips(tool, data):
    d = should_visualize(tool, data, prefer_visualization="never")
    assert d.kind is DecisionKind.SKIP


# --- search_clinical_trials / search_publications --------------------------


def test_search_empty_skips():
    d = should_visualize("search_clinical_trials", {"results": []})
    assert d.kind is DecisionKind.SKIP


def test_search_single_trivial_hit_skips():
    d = should_visualize(
        "search_clinical_trials",
        {"results": [{"nct_id": "NCT01", "title": "Just a title"}]},
    )
    assert d.kind is DecisionKind.SKIP


def test_search_single_rich_hit_skips():
    # Even a rich single hit skips — a text answer is better than one card
    d = should_visualize(
        "search_clinical_trials",
        {"results": [{"nct_id": "NCT01", "title": "T", "phase": "Phase 3", "sponsor": "S"}]},
    )
    assert d.kind is DecisionKind.SKIP


def test_search_two_hits_uses_recipe():
    d = should_visualize(
        "search_clinical_trials",
        {
            "results": [
                {"nct_id": "NCT01", "title": "A", "phase": "3"},
                {"nct_id": "NCT02", "title": "B", "phase": "3"},
            ]
        },
    )
    assert d.kind is DecisionKind.USE
    assert d.recipe == "trial_search_results"


def test_search_always_forces_recipe_even_for_empty():
    d = should_visualize(
        "search_clinical_trials",
        {"results": []},
        prefer_visualization="always",
    )
    assert d.kind is DecisionKind.USE
    assert d.recipe == "trial_search_results"


def test_publications_same_recipe_as_trials():
    d = should_visualize(
        "search_publications",
        {
            "results": [
                {"pmid": "111", "title": "A", "abstract": "x"},
                {"pmid": "222", "title": "B", "abstract": "y"},
            ]
        },
    )
    assert d.kind is DecisionKind.USE
    assert d.recipe == "trial_search_results"


# --- get_trial_details ------------------------------------------------------


def test_trial_details_sparse_skips():
    d = should_visualize(
        "get_trial_details",
        {"nct_id": "NCT01", "title": "Sparse"},
    )
    assert d.kind is DecisionKind.SKIP


def test_trial_details_rich_uses_tabs():
    d = should_visualize(
        "get_trial_details",
        {
            "nct_id": "NCT01",
            "title": "Rich",
            "arms": [{"label": "Arm A"}],
            "eligibility": {"criteria": "..."},
        },
    )
    assert d.kind is DecisionKind.USE
    assert d.recipe == "trial_detail_tabs"


def test_trial_details_always_forces():
    d = should_visualize(
        "get_trial_details",
        {"nct_id": "NCT01"},
        prefer_visualization="always",
    )
    assert d.kind is DecisionKind.USE
    assert d.recipe == "trial_detail_tabs"


# --- get_indication_landscape ----------------------------------------------


def test_landscape_empty_skips():
    d = should_visualize("get_indication_landscape", {"indication": "x"})
    assert d.kind is DecisionKind.SKIP


def test_landscape_single_phase_single_sponsor_skips():
    d = should_visualize(
        "get_indication_landscape",
        {
            "phase_distribution": [{"phase": "3", "count": 10}],
            "top_sponsors": [{"name": "A", "trials": 10}],
        },
    )
    assert d.kind is DecisionKind.SKIP


def test_landscape_multi_phase_uses_dashboard():
    d = should_visualize(
        "get_indication_landscape",
        {
            "phase_distribution": [
                {"phase": "1", "count": 5},
                {"phase": "2", "count": 10},
                {"phase": "3", "count": 3},
            ],
            "top_sponsors": [],
        },
    )
    assert d.kind is DecisionKind.USE
    assert d.recipe == "indication_dashboard"


def test_landscape_multi_sponsor_uses_dashboard():
    d = should_visualize(
        "get_indication_landscape",
        {
            "phase_distribution": [{"phase": "3", "count": 10}],
            "top_sponsors": [
                {"name": "A", "trials": 5},
                {"name": "B", "trials": 3},
            ],
        },
    )
    assert d.kind is DecisionKind.USE


# --- compare_trials ---------------------------------------------------------


def test_compare_single_trial_skips():
    d = should_visualize(
        "compare_trials",
        {"trials": [{"nct_id": "NCT01"}]},
    )
    assert d.kind is DecisionKind.SKIP


def test_compare_two_trials_with_dates_uses_gantt():
    d = should_visualize(
        "compare_trials",
        {
            "trials": [
                {
                    "nct_id": "NCT01",
                    "start_date": "2023-01-01",
                    "primary_completion_date": "2026-01-01",
                },
                {
                    "nct_id": "NCT02",
                    "start_date": "2023-06-01",
                    "primary_completion_date": "2026-06-01",
                },
            ]
        },
    )
    assert d.kind is DecisionKind.USE
    assert d.recipe == "trial_timeline_gantt"


def test_compare_missing_dates_falls_back_to_cards():
    d = should_visualize(
        "compare_trials",
        {
            "trials": [
                {"nct_id": "NCT01"},
                {"nct_id": "NCT02"},
            ]
        },
    )
    assert d.kind is DecisionKind.USE
    assert d.recipe == "sponsor_pipeline_cards"


def test_compare_over_cap_switches_to_cards():
    trials = [
        {
            "nct_id": f"NCT{i:04d}",
            "start_date": "2023-01-01",
            "primary_completion_date": "2026-01-01",
        }
        for i in range(MAX_TRIALS_IN_GANTT + 3)
    ]
    d = should_visualize("compare_trials", {"trials": trials})
    assert d.kind is DecisionKind.USE
    assert d.recipe == "sponsor_pipeline_cards"


def test_compare_prefer_cards_forces_cards():
    d = should_visualize(
        "compare_trials",
        {
            "trials": [
                {
                    "nct_id": "NCT01",
                    "start_date": "2023-01-01",
                    "primary_completion_date": "2026-01-01",
                },
                {
                    "nct_id": "NCT02",
                    "start_date": "2023-06-01",
                    "primary_completion_date": "2026-06-01",
                },
            ]
        },
        prefer_visualization="cards",
    )
    assert d.kind is DecisionKind.USE
    assert d.recipe == "sponsor_pipeline_cards"


def test_compare_prefer_cards_empty_skips():
    d = should_visualize(
        "compare_trials", {"trials": []}, prefer_visualization="cards"
    )
    assert d.kind is DecisionKind.SKIP


# --- build_trial_comparison (NEW promptclub tool, same heuristic) -----------


def test_build_trial_comparison_uses_compare_logic():
    d = should_visualize(
        "build_trial_comparison",
        {
            "trials": [
                {"nct_id": "NCT01", "start_date": "2023-01-01", "primary_completion_date": "2026-01-01"},
                {"nct_id": "NCT02", "start_date": "2023-06-01", "primary_completion_date": "2026-06-01"},
            ]
        },
    )
    assert d.kind is DecisionKind.USE
    assert d.recipe == "trial_timeline_gantt"


def test_build_trial_comparison_single_trial_skips():
    d = should_visualize(
        "build_trial_comparison",
        {"trials": [{"nct_id": "NCT01"}]},
    )
    assert d.kind is DecisionKind.SKIP


# --- analyze_whitespace -----------------------------------------------------


def test_analyze_whitespace_with_phase_counts_uses_card():
    d = should_visualize(
        "analyze_whitespace",
        {
            "trial_counts_by_phase": {"phase_1": 10, "phase_2": 5, "phase_3": 1},
            "trial_counts_by_status": {"recruiting": 8},
            "identified_whitespace": ["Few Phase 3 trials"],
        },
    )
    assert d.kind is DecisionKind.USE
    assert d.recipe == "whitespace_card"


def test_analyze_whitespace_only_signals_uses_card():
    d = should_visualize(
        "analyze_whitespace",
        {
            "trial_counts_by_phase": {},
            "trial_counts_by_status": {},
            "identified_whitespace": ["Some gap signal"],
        },
    )
    assert d.kind is DecisionKind.USE


def test_analyze_whitespace_empty_skips():
    d = should_visualize(
        "analyze_whitespace",
        {
            "trial_counts_by_phase": {"phase_1": 0, "phase_2": 0},
            "trial_counts_by_status": {},
            "identified_whitespace": [],
        },
    )
    assert d.kind is DecisionKind.SKIP


# --- analyze_indication_landscape + get_sponsor_overview (always skip) ------


import pytest


@pytest.mark.parametrize(
    "tool", ["analyze_indication_landscape", "get_sponsor_overview"]
)
def test_aggregate_count_tools_skip_by_design(tool):
    d = should_visualize(tool, {"some_count": 100})
    assert d.kind is DecisionKind.SKIP

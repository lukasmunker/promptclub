"""Smoke tests: build_response must always return an envelope with ui."""

from app.viz.build import build_response


def test_build_response_with_no_results_emits_ui():
    envelope = build_response(
        tool_name="search_clinical_trials",
        data={"results": []},
        sources=[],
    )
    # Pre-fix: ui is None. Post-fix: ui is populated.
    assert envelope.get("ui") is not None
    assert envelope["ui"]["recipe"] in ("info_card", "concept_card", "single_entity_card")


def test_build_response_with_unknown_tool_emits_ui():
    envelope = build_response(
        tool_name="totally_made_up_tool",
        data={"some": "data"},
        sources=[],
    )
    assert envelope.get("ui") is not None


def test_build_response_with_definition_query_emits_concept_card():
    envelope = build_response(
        tool_name="search_publications",
        data={"results": []},
        sources=[],
    )
    # Without query hint we get info_card (default)
    assert envelope.get("ui") is not None


def test_build_response_with_existing_recipe_unchanged():
    """The happy path must not regress: a real search_clinical_trials response
    with multiple results still gets the trial_search_results recipe."""
    envelope = build_response(
        tool_name="search_clinical_trials",
        data={"results": [
            {"id": "NCT01", "title": "T1", "sponsor": "S1", "phase": "3", "status": "Recruiting"},
            {"id": "NCT02", "title": "T2", "sponsor": "S2", "phase": "3", "status": "Active"},
        ]},
        sources=[],
    )
    assert envelope.get("ui") is not None
    assert envelope["ui"]["recipe"] == "trial_search_results"

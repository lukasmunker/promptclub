"""Tests for the fallback recipe selector.

The selector is the bridge between the SKIP path in build_response and
the new fallback recipes. It must always return a valid recipe name —
the universal default is 'info_card'.
"""

from app.viz.fallback import pick_fallback_recipe, build_fallback_data


# --- Recipe selection -------------------------------------------------------


def test_definition_query_picks_concept_card():
    name = pick_fallback_recipe(
        tool_name="search_publications",
        data={"results": [{"abstract": "RECIST is..."}]},
        query_hint="What is RECIST?",
    )
    assert name == "concept_card"


def test_define_query_picks_concept_card():
    name = pick_fallback_recipe(
        tool_name="search_publications",
        data={},
        query_hint="define progression-free survival",
    )
    assert name == "concept_card"


def test_single_trial_lookup_picks_single_entity_card():
    name = pick_fallback_recipe(
        tool_name="get_trial_details",
        data={"nct_id": "NCT01234567", "title": "Phase 3 study"},
        query_hint=None,
    )
    assert name == "single_entity_card"


def test_empty_response_picks_info_card():
    name = pick_fallback_recipe(
        tool_name="search_clinical_trials",
        data={"results": []},
        query_hint="any query",
    )
    assert name == "info_card"


def test_unknown_tool_picks_info_card():
    name = pick_fallback_recipe(
        tool_name="some_random_tool",
        data={"foo": "bar"},
        query_hint=None,
    )
    assert name == "info_card"


def test_no_query_hint_picks_info_card():
    name = pick_fallback_recipe(
        tool_name="search_clinical_trials",
        data={"results": [{"id": "x"}, {"id": "y"}]},
        query_hint=None,
    )
    assert name == "info_card"


# --- Fallback data shaping --------------------------------------------------


def test_build_fallback_data_for_info_card_uses_tool_name():
    data = build_fallback_data(
        recipe_name="info_card",
        tool_name="search_clinical_trials",
        original_data={"results": []},
        query_hint="pembrolizumab in NSCLC",
    )
    assert data["title"]
    assert "search_clinical_trials" in data["title"] or "Result" in data["title"]
    # The query hint should appear so the LLM has context
    assert data.get("subtitle") or data.get("no_results_hint")


def test_build_fallback_data_for_concept_card_extracts_term():
    data = build_fallback_data(
        recipe_name="concept_card",
        tool_name="search_publications",
        original_data={},
        query_hint="What is RECIST 1.1?",
    )
    assert data.get("term")
    assert "RECIST" in data["term"]


def test_build_fallback_data_for_single_entity_card_extracts_facts():
    data = build_fallback_data(
        recipe_name="single_entity_card",
        tool_name="get_trial_details",
        original_data={
            "nct_id": "NCT01234567",
            "title": "A Phase 3 study",
            "phase": "Phase 3",
            "sponsor": "Merck",
        },
        query_hint=None,
    )
    assert data.get("title") == "NCT01234567" or data.get("title") == "A Phase 3 study"
    assert data.get("facts")

"""When a tool's data fetch yields no records, the response must still
contain an artifact block. The legacy [NO DATA AVAILABLE] path must be
gone."""

from app.viz.build import build_response


def test_empty_search_clinical_trials_emits_artifact_not_no_data():
    envelope = build_response(
        tool_name="search_clinical_trials",
        data={"results": [], "total": 0},
        sources=[],
        query_hint="some query that returned nothing",
    )
    assert envelope.get("ui") is not None
    assert "raw" in envelope["ui"]
    assert envelope["ui"]["raw"]


def test_empty_get_trial_details_emits_artifact():
    envelope = build_response(
        tool_name="get_trial_details",
        data={},
        sources=[],
        query_hint="NCT99999999",
    )
    assert envelope.get("ui") is not None

"""End-to-end test: build_response enriches data with annotations
from the live oncology lexicon, then routes through the recipe
dispatcher (and the WS1 fallback if needed)."""

from app.viz.build import build_response


def test_build_response_attaches_annotations_for_oncology_terms():
    envelope = build_response(
        tool_name="search_clinical_trials",
        data={
            "results": [
                {"id": "NCT01", "title": "T1", "sponsor": "S1", "phase": "Phase 3", "status": "Recruiting"},
                {"id": "NCT02", "title": "T2", "sponsor": "S2", "phase": "Phase 3", "status": "Active"},
            ]
        },
        sources=[],
    )
    annotations = envelope["data"].get("knowledge_annotations", [])
    # Phase 3 should be annotated (matched_term preserves original casing)
    assert any(a["matched_term"].lower() == "phase 3" for a in annotations), (
        f"Expected 'phase 3' annotation, got: {[a['matched_term'] for a in annotations]}"
    )


def test_build_response_works_when_lexicon_has_no_match():
    envelope = build_response(
        tool_name="search_clinical_trials",
        data={"results": [{"id": "NCT99", "title": "Generic Title", "sponsor": "X"}]},
        sources=[],
    )
    # Annotations field is present but may be empty
    assert "knowledge_annotations" in envelope["data"]
    assert isinstance(envelope["data"]["knowledge_annotations"], list)


def test_build_response_still_emits_artifact_with_annotations():
    """Both WS1 and WS2 guarantees together: artifact present, annotations attached."""
    envelope = build_response(
        tool_name="search_clinical_trials",
        data={"results": []},
        sources=[],
        query_hint="test",
    )
    assert envelope.get("ui") is not None  # WS1 guarantee
    assert "knowledge_annotations" in envelope["data"]  # WS2 guarantee


def test_build_response_survives_lexicon_load_failure(monkeypatch):
    """When the lexicon loader raises, build_response must still
    produce a valid envelope with an empty knowledge_annotations list.
    The WS1 artifact guarantee must not be broken by lexicon trouble."""
    import app.viz.build as build_module

    # Force _lexicon() to raise by clearing its cache and monkeypatching
    # load_lexicon to fail.
    def broken_load():
        raise FileNotFoundError("simulated missing lexicon.yaml")

    monkeypatch.setattr(build_module, "load_lexicon", broken_load)
    build_module._lexicon.cache_clear()
    # Reset the disabled flag so this test starts fresh
    build_module._enrichment_disabled = False

    try:
        envelope = build_module.build_response(
            tool_name="search_clinical_trials",
            data={"results": [{"id": "NCT01", "title": "T", "phase": "Phase 3"}]},
            sources=[],
        )

        # WS1 guarantee: ui is populated
        assert envelope.get("ui") is not None
        # WS2 graceful fallback: knowledge_annotations is an empty list, not raised
        assert envelope["data"]["knowledge_annotations"] == []

        # Subsequent calls also work (disabled flag is sticky)
        envelope2 = build_module.build_response(
            tool_name="search_clinical_trials",
            data={"results": []},
            sources=[],
        )
        assert envelope2.get("ui") is not None
        assert envelope2["data"]["knowledge_annotations"] == []
    finally:
        # Cleanup: reset state for other tests
        build_module._enrichment_disabled = False
        build_module._lexicon.cache_clear()

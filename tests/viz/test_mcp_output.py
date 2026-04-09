"""Tests for app.viz.mcp_output.envelope_to_llm_text().

This wrapper is what every ``@mcp.tool()`` in app.main now returns. It
converts an envelope dict into plain text that the LLM can paste directly
into its reply (no JSON transformation required).
"""

from __future__ import annotations

import pytest

from app.viz.mcp_output import envelope_to_llm_text


# --- Full visualization path -----------------------------------------------


def _html_envelope(raw: str = "<div>hello</div>") -> dict:
    """Minimal visualization envelope with a text/html artifact."""
    return {
        "render_hint": (
            "MUST: …cite sources… no forward-looking statements."
        ),
        "ui": {
            "recipe": "trial_search_results",
            "artifact": {
                "identifier": "trial-search-results-melanoma-2026-04-09",
                "type": "html",
                "title": "Phase 3 Melanoma Trials",
            },
            "raw": raw,
        },
        "data": {"total": 3},
        "sources": [
            {
                "kind": "clinicaltrials.gov",
                "id": "NCT01234567",
                "url": "https://clinicaltrials.gov/study/NCT01234567",
                "retrieved_at": "2026-04-09T12:00:00Z",
            },
            {
                "kind": "pubmed",
                "id": "12345678",
                "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
                "retrieved_at": "2026-04-09T12:00:00Z",
            },
        ],
    }


def test_html_envelope_starts_with_action_required_preamble():
    """The tool result must start with the in-band instruction so the LLM
    reads "paste this verbatim" before the artifact block itself."""
    env = _html_envelope()
    text = envelope_to_llm_text(env)
    assert text.startswith("ACTION REQUIRED")
    assert "copy the :::artifact" in text
    assert "VERBATIM" in text


def test_html_envelope_contains_artifact_block_after_preamble():
    env = _html_envelope()
    text = envelope_to_llm_text(env)
    assert ":::artifact{" in text
    assert 'identifier="trial-search-results-melanoma-2026-04-09"' in text
    assert 'type="html"' in text
    assert 'title="Phase 3 Melanoma Trials"' in text
    assert "<div>hello</div>" in text
    # Must still have a closing fence
    assert "\n:::\n" in text or ":::\n\nSources" in text


def test_preamble_precedes_artifact_block():
    """Preamble must come BEFORE the artifact block."""
    text = envelope_to_llm_text(_html_envelope())
    preamble_idx = text.index("ACTION REQUIRED")
    artifact_idx = text.index(":::artifact{")
    assert preamble_idx < artifact_idx


def test_html_envelope_includes_sources_footer():
    env = _html_envelope()
    text = envelope_to_llm_text(env)
    assert "Sources:" in text
    assert "[clinicaltrials.gov] NCT01234567" in text
    assert "[pubmed] 12345678" in text


def test_html_envelope_artifact_precedes_sources():
    """Artifact block must come BEFORE the sources footer so the LLM pastes
    it at the top of the reply and cites from the footer afterwards."""
    text = envelope_to_llm_text(_html_envelope())
    artifact_end = text.rindex(":::")  # last triple-colon = end of block
    sources_idx = text.index("Sources:")
    assert artifact_end < sources_idx


def test_html_envelope_escapes_quotes_in_title():
    env = _html_envelope()
    env["ui"]["artifact"]["title"] = 'A "quoted" title'
    text = envelope_to_llm_text(env)
    # Title must have the inner quotes escaped so the directive attribute parses
    assert 'title="A \\"quoted\\" title"' in text


def test_html_envelope_with_empty_sources():
    env = _html_envelope()
    env["sources"] = []
    text = envelope_to_llm_text(env)
    assert "(none returned by this tool)" in text


def test_html_envelope_caps_sources_footer_at_ten():
    env = _html_envelope()
    env["sources"] = [
        {
            "kind": "pubmed",
            "id": f"{i:08d}",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{i:08d}/",
            "retrieved_at": "2026-04-09T12:00:00Z",
        }
        for i in range(25)
    ]
    text = envelope_to_llm_text(env)
    # Ten shown, 15 summarized
    assert "[pubmed] 00000000" in text
    assert "[pubmed] 00000009" in text
    assert "[pubmed] 00000010" not in text
    assert "(+15 more)" in text


# --- Mermaid artifact path --------------------------------------------------


def test_mermaid_envelope_emits_artifact_block_without_code_fence():
    """Mermaid artifacts must NOT be wrapped in a ```mermaid fence inside the
    directive body — the type declaration in the opening tag already declares
    the content type."""
    env = {
        "render_hint": "MUST: …cite sources… no forward-looking statements.",
        "ui": {
            "recipe": "trial_timeline_gantt",
            "artifact": {
                "identifier": "gantt-xyz",
                "type": "mermaid",
                "title": "Trial Timeline",
            },
            "raw": "gantt\n    dateFormat  YYYY-MM-DD\n    title Trial Timeline",
        },
        "data": {},
        "sources": [],
    }
    text = envelope_to_llm_text(env)
    assert text.startswith("ACTION REQUIRED")
    assert ":::artifact{" in text
    assert 'type="mermaid"' in text
    assert "gantt\n    dateFormat" in text
    assert "```mermaid" not in text


# --- Text-only / SKIP path (now dead — raises ValueError) ------------------


def test_skip_envelope_raises_value_error():
    """The SKIP path (ui=None envelope) is now a caller bug — build_response
    guarantees ui is always populated. envelope_to_llm_text must raise."""
    env = {
        "render_hint": (
            "Answer as plain text based on data. Cite sources using NCT/PMID "
            "IDs from the 'sources' field. No forward-looking statements."
        ),
        "data": {"count": 3, "results": [{"name": "foo"}]},
        "sources": [
            {
                "kind": "opentargets",
                "id": "EFO_0000756",
                "url": "https://platform.opentargets.org/disease/EFO_0000756",
                "retrieved_at": "2026-04-09T12:00:00Z",
            }
        ],
    }
    with pytest.raises(ValueError, match="without a ui field"):
        envelope_to_llm_text(env)


def test_skip_envelope_with_no_ui_raises_value_error():
    """Any envelope missing ui raises ValueError — even with large data."""
    env = {
        "render_hint": "Answer as plain text. Cite sources. No forward-looking.",
        "data": {"huge": "x" * 10000},
        "sources": [],
    }
    with pytest.raises(ValueError, match="without a ui field"):
        envelope_to_llm_text(env)


# --- Legacy "no data" path (now dead — raises ValueError) ------------------


def test_no_data_envelope_raises_value_error():
    """The no_data shortcircuit is gone — envelope_to_llm_text raises."""
    env = {
        "no_data": True,
        "source": "ClinicalTrials.gov v2",
        "query": "disease='xyz' phase=3 sponsor=None status=None",
        "do_not_supplement": (
            "No records were found in ClinicalTrials.gov v2 for 'xyz'. "
            "Tell the user no data is available; do NOT answer from training knowledge."
        ),
    }
    with pytest.raises(ValueError, match="without a ui field"):
        envelope_to_llm_text(env)


def test_no_data_without_guardrail_raises_value_error():
    """The no_data shortcircuit is gone — any ui=None envelope raises."""
    env = {"no_data": True, "source": "pubmed", "query": "weird"}
    with pytest.raises(ValueError, match="without a ui field"):
        envelope_to_llm_text(env)


def test_mcp_output_never_emits_no_visualization_marker():
    """The [NO VISUALIZATION] and [NO DATA AVAILABLE] markers must not
    appear for any envelope produced by build_response."""
    from app.viz.build import build_response
    from app.viz.mcp_output import envelope_to_llm_text

    for empty_data in ({}, {"results": []}, {"trials": []}):
        envelope = build_response(
            tool_name="search_clinical_trials",
            data=empty_data,
            sources=[],
            query_hint="test",
        )
        text = envelope_to_llm_text(envelope)
        assert ":::artifact" in text
        assert "[NO VISUALIZATION]" not in text
        assert "[NO DATA AVAILABLE]" not in text


# --- Knowledge annotations glossary ----------------------------------------


def test_envelope_to_llm_text_includes_glossary_when_annotations_present():
    """When the envelope's data dict carries knowledge_annotations, the
    LLM-facing text MUST include a ## Glossary section with deduplicated
    entries. Without this, only info_card surfaces annotations; every
    other recipe silently drops them."""
    envelope = {
        "ui": {
            "recipe": "trial_search_results",
            "artifact": {
                "identifier": "test-id",
                "type": "html",
                "title": "Test",
            },
            "raw": "<div>test</div>",
        },
        "data": {
            "results": [],
            "knowledge_annotations": [
                {
                    "field_path": "results[0].phase",
                    "matched_term": "Phase 3",
                    "lexicon_id": "trial-phase-3",
                    "short_definition": "Late-stage clinical trial confirming efficacy.",
                    "clinical_context": "x",
                    "review_status": "llm-generated",
                },
                {
                    "field_path": "results[0].endpoint",
                    "matched_term": "Overall Survival",
                    "lexicon_id": "endpoint-os",
                    "short_definition": "Time from randomization to death from any cause.",
                    "clinical_context": "x",
                    "review_status": "llm-generated",
                },
            ],
        },
        "sources": [
            {
                "kind": "clinicaltrials.gov",
                "id": "NCT01234567",
                "url": "https://clinicaltrials.gov/study/NCT01234567",
                "retrieved_at": "2026-04-09T12:00:00Z",
            }
        ],
    }

    text = envelope_to_llm_text(envelope)
    assert "## Glossary" in text
    assert "**Phase 3**" in text
    assert "Late-stage clinical trial" in text
    assert "**Overall Survival**" in text
    # Glossary appears between the artifact block and the sources footer
    artifact_idx = text.index(":::artifact")
    glossary_idx = text.index("## Glossary")
    sources_idx = text.index("Sources:")
    assert artifact_idx < glossary_idx < sources_idx


def test_envelope_to_llm_text_omits_glossary_when_no_annotations():
    """Without annotations, the glossary section must not appear."""
    envelope = {
        "ui": {
            "recipe": "trial_search_results",
            "artifact": {
                "identifier": "test-id",
                "type": "html",
                "title": "Test",
            },
            "raw": "<div>test</div>",
        },
        "data": {"results": []},
        "sources": [],
    }

    text = envelope_to_llm_text(envelope)
    assert "## Glossary" not in text


def test_envelope_to_llm_text_glossary_dedupes_by_lexicon_id():
    """Repeated annotations for the same lexicon_id must collapse to a
    single glossary line (first occurrence wins)."""
    envelope = {
        "ui": {
            "recipe": "trial_search_results",
            "artifact": {
                "identifier": "t",
                "type": "html",
                "title": "T",
            },
            "raw": "<div/>",
        },
        "data": {
            "knowledge_annotations": [
                {
                    "field_path": "a",
                    "matched_term": "Phase 3",
                    "lexicon_id": "trial-phase-3",
                    "short_definition": "First def.",
                    "clinical_context": "x",
                    "review_status": "llm-generated",
                },
                {
                    "field_path": "b",
                    "matched_term": "Phase 3",
                    "lexicon_id": "trial-phase-3",
                    "short_definition": "Second def (should be dropped).",
                    "clinical_context": "x",
                    "review_status": "llm-generated",
                },
            ]
        },
        "sources": [],
    }
    text = envelope_to_llm_text(envelope)
    assert text.count("**Phase 3**") == 1
    assert "First def." in text
    assert "Second def" not in text


def test_envelope_to_llm_text_glossary_truncates_long_definitions():
    """Definitions longer than 200 chars must be truncated with an ellipsis."""
    long_def = "x" * 500
    envelope = {
        "ui": {
            "recipe": "trial_search_results",
            "artifact": {
                "identifier": "t",
                "type": "html",
                "title": "T",
            },
            "raw": "<div/>",
        },
        "data": {
            "knowledge_annotations": [
                {
                    "field_path": "a",
                    "matched_term": "Phase 3",
                    "lexicon_id": "trial-phase-3",
                    "short_definition": long_def,
                    "clinical_context": "x",
                    "review_status": "llm-generated",
                },
            ]
        },
        "sources": [],
    }
    text = envelope_to_llm_text(envelope)
    # The full 500-char definition must not appear
    assert long_def not in text
    # But the truncation marker must
    assert "…" in text

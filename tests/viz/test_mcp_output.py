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


def test_html_envelope_emits_artifact_block_verbatim():
    env = _html_envelope()
    text = envelope_to_llm_text(env)

    assert text.startswith(":::artifact{")
    assert 'identifier="trial-search-results-melanoma-2026-04-09"' in text
    assert 'type="html"' in text
    assert 'title="Phase 3 Melanoma Trials"' in text
    # Raw HTML body appears between the opening attrs and the closing :::
    assert "<div>hello</div>" in text
    # Block closes with standalone :::
    assert "\n:::\n" in text or text.rstrip().endswith(":::")


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
    assert text.startswith(":::artifact{")
    assert 'type="mermaid"' in text
    assert "gantt\n    dateFormat" in text
    assert "```mermaid" not in text


# --- Text-only / SKIP path -------------------------------------------------


def test_skip_envelope_emits_no_visualization_marker():
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
    text = envelope_to_llm_text(env)
    assert text.startswith("[NO VISUALIZATION")
    assert ":::artifact" not in text  # no fake artifact block
    assert '"count": 3' in text  # data JSON included
    assert "[opentargets] EFO_0000756" in text  # sources footer
    assert "No forward-looking statements" in text


def test_skip_envelope_truncates_huge_data_dump():
    env = {
        "render_hint": "Answer as plain text. Cite sources. No forward-looking.",
        "data": {"huge": "x" * 10000},
        "sources": [],
    }
    text = envelope_to_llm_text(env)
    assert text.startswith("[NO VISUALIZATION")
    assert "truncated" in text.lower()
    # Overall text must stay reasonable so it doesn't eat the LLM context
    assert len(text) < 5000


# --- Legacy "no data" path --------------------------------------------------


def test_no_data_envelope_emits_marker_and_guardrail():
    env = {
        "no_data": True,
        "source": "ClinicalTrials.gov v2",
        "query": "disease='xyz' phase=3 sponsor=None status=None",
        "do_not_supplement": (
            "No records were found in ClinicalTrials.gov v2 for 'xyz'. "
            "Tell the user no data is available; do NOT answer from training knowledge."
        ),
    }
    text = envelope_to_llm_text(env)
    assert text.startswith("[NO DATA AVAILABLE]")
    assert "ClinicalTrials.gov v2" in text
    assert "disease='xyz'" in text
    assert "do NOT answer from training knowledge" in text


def test_no_data_without_guardrail_still_produces_text():
    env = {"no_data": True, "source": "pubmed", "query": "weird"}
    text = envelope_to_llm_text(env)
    assert text.startswith("[NO DATA AVAILABLE]")
    assert "pubmed" in text
    assert "no data was found" in text.lower()

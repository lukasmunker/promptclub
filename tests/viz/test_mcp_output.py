"""Tests for app.viz.mcp_output.envelope_to_llm_text().

This wrapper is what every ``@mcp.tool()`` in app.main now returns. It
converts an envelope dict into plain text that the LLM can paste directly
into its reply (no JSON transformation required).
"""

from __future__ import annotations

import pytest

from app.citations import attach_citation_layer
from app.models import Citation
from app.viz.build import build_response
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
    assert "copy the artifact directive block" in text
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


# --- Markdown inline path --------------------------------------------------


def _markdown_envelope(raw: str = "### Concept\n\n> A short definition.") -> dict:
    """Minimal envelope with a ``markdown`` artifact — the inline path."""
    return {
        "render_hint": (
            "MUST: …cite sources inline [1]… no forward-looking statements."
        ),
        "ui": {
            "recipe": "concept_card",
            "artifact": {
                "identifier": "concept-card-recist",
                "type": "markdown",
                "title": "RECIST 1.1",
            },
            "raw": raw,
        },
        "data": {},
        "sources": [],
    }


def test_markdown_envelope_does_not_wrap_in_artifact_directive():
    """The inline-markdown path must NOT wrap ui.raw in a
    ``:::artifact{…}:::`` block — that would push the content into the
    side pane, which is exactly what this path is meant to avoid."""
    text = envelope_to_llm_text(_markdown_envelope())
    assert ":::artifact" not in text
    assert "type=\"markdown\"" not in text


def test_markdown_envelope_embeds_raw_inline():
    """The markdown body must appear verbatim inline in the LLM text."""
    raw = "### RECIST 1.1\n\n> Response Evaluation Criteria in Solid Tumors."
    text = envelope_to_llm_text(_markdown_envelope(raw=raw))
    assert raw in text


def test_markdown_envelope_preamble_instructs_inline_paste():
    """The preamble on the inline path must tell the LLM to paste the
    snippet inline, not wrap it in an artifact directive."""
    text = envelope_to_llm_text(_markdown_envelope())
    assert text.startswith("ACTION REQUIRED")
    # Must NOT say "copy the :::artifact block"
    assert "copy the :::artifact" not in text
    # Must mention inline embedding and numbered citation markers
    assert "inline" in text.lower()
    assert "[1]" in text


def test_markdown_envelope_includes_sources_footer():
    env = _markdown_envelope()
    env["sources"] = [
        {
            "kind": "pubmed",
            "id": "12345678",
            "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
            "retrieved_at": "2026-04-09T12:00:00Z",
        }
    ]
    text = envelope_to_llm_text(env)
    assert "Sources:" in text
    assert "[pubmed] 12345678" in text


# --- Numbered references path (citation_layer) ----------------------------


def _citation_layer_envelope(
    artifact_type: str = "html",
    references: list[dict] | None = None,
) -> dict:
    """Envelope with an attached citation_layer simulating the output of
    ``app.citations.attach_citation_layer``."""
    refs = references if references is not None else [
        {
            "index": 1,
            "marker": "[1]",
            "markdown_marker": "[[1]](https://pubmed.ncbi.nlm.nih.gov/12345678/)",
            "label": "Pembrolizumab in NSCLC",
            "source": "PubMed",
            "id": "12345678",
            "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
            "title": "Pembrolizumab in NSCLC",
        },
        {
            "index": 2,
            "marker": "[2]",
            "markdown_marker": "[[2]](https://clinicaltrials.gov/study/NCT01234567)",
            "label": "NCT01234567",
            "source": "ClinicalTrials.gov",
            "id": "NCT01234567",
            "url": "https://clinicaltrials.gov/study/NCT01234567",
            "title": "Phase 3 study",
        },
    ]
    return {
        "render_hint": "MUST: …cite sources… no forward-looking statements.",
        "ui": {
            "recipe": "trial_search_results" if artifact_type == "html" else "concept_card",
            "artifact": {
                "identifier": "test-id",
                "type": artifact_type,
                "title": "Test",
            },
            "raw": (
                "<div>hi</div>" if artifact_type == "html" else "### RECIST"
            ),
        },
        "data": {},
        "sources": [],
        "citation_layer": {"references": refs},
    }


def test_citation_layer_renders_numbered_references_block():
    """When the envelope carries a citation_layer, the LLM text must
    include a numbered ``## References`` section with clickable markdown
    links — that's how we get inline clickable citations."""
    text = envelope_to_llm_text(_citation_layer_envelope())
    assert "## References" in text
    # Numbered clickable entries
    assert "[1] [Pembrolizumab in NSCLC](https://pubmed.ncbi.nlm.nih.gov/12345678/)" in text
    assert "[2] [NCT01234567](https://clinicaltrials.gov/study/NCT01234567)" in text


def test_citation_layer_emits_link_reference_footer_for_auto_linking():
    """Each reference must also appear as a markdown link reference
    (``[n]: url``) so bare ``[n]`` tokens in the LLM's commentary
    auto-link without the LLM needing to emit full markdown links."""
    text = envelope_to_llm_text(_citation_layer_envelope())
    assert "[1]: https://pubmed.ncbi.nlm.nih.gov/12345678/" in text
    assert "[2]: https://clinicaltrials.gov/study/NCT01234567" in text


def test_citation_layer_references_appear_between_artifact_and_sources():
    """Order: artifact block → (optional glossary) → ## References →
    link-ref footer → Sources: footer. This keeps the inline refs visible
    to the LLM AFTER the artifact and BEFORE the one-line Sources bag."""
    text = envelope_to_llm_text(_citation_layer_envelope(artifact_type="html"))
    artifact_end = text.index(":::\n")  # first closing fence after artifact
    refs_idx = text.index("## References")
    sources_idx = text.index("Sources:")
    assert artifact_end < refs_idx < sources_idx


def test_citation_layer_skipped_when_references_empty():
    """No references → no ``## References`` section."""
    env = _citation_layer_envelope(references=[])
    # Without any references, attach_citation_layer wouldn't attach the
    # layer at all, but defend against a partial attach just in case.
    env["citation_layer"] = {"references": []}
    text = envelope_to_llm_text(env)
    assert "## References" not in text


def test_citation_layer_skipped_when_not_attached():
    """No citation_layer key → no ``## References`` section. This is the
    baseline behavior — only tools that pass citations through
    ``attach_citation_layer`` get the inline references block."""
    env = _citation_layer_envelope()
    del env["citation_layer"]
    text = envelope_to_llm_text(env)
    assert "## References" not in text


def test_citation_layer_drops_references_missing_url():
    """References without a URL can't be clickable — drop them silently."""
    env = _citation_layer_envelope(
        references=[
            {
                "index": 1,
                "label": "No URL reference",
                "source": "Source",
                "id": "xyz",
                "url": None,
            },
            {
                "index": 2,
                "label": "Has URL",
                "source": "PubMed",
                "id": "12345",
                "url": "https://pubmed.ncbi.nlm.nih.gov/12345/",
            },
        ]
    )
    text = envelope_to_llm_text(env)
    assert "No URL reference" not in text
    assert "[2] [Has URL](https://pubmed.ncbi.nlm.nih.gov/12345/)" in text


def test_citation_layer_works_with_inline_markdown_envelope():
    """The inline-markdown path must also render the references block
    so compact recipes benefit from clickable citations."""
    text = envelope_to_llm_text(_citation_layer_envelope(artifact_type="markdown"))
    assert "## References" in text
    assert "[1]:" in text


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
    appear for any envelope produced by build_response. Every envelope
    must also carry a non-empty body — either an artifact directive
    block (side-pane path) or an inline Markdown snippet (inline path)
    — and start with the ACTION REQUIRED preamble so the LLM knows what
    to do with it."""
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
        assert text.startswith("ACTION REQUIRED")
        # Either a side-pane artifact block OR an inline markdown body
        # must be present — never neither.
        has_artifact = ":::artifact{identifier=" in text
        has_inline_body = bool(envelope["ui"].get("raw")) and (
            envelope["ui"]["raw"].strip() in text
        )
        assert has_artifact or has_inline_body, (
            "envelope produced neither an artifact directive nor an inline "
            "markdown body — coverage guarantee broken"
        )
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


# --- End-to-end: Citation → attach_citation_layer → LLM text --------------


def test_end_to_end_citations_produce_inline_numbered_references():
    """Full pipeline smoke test: feed real ``Citation`` models through
    ``attach_citation_layer`` on an envelope returned by
    ``build_response`` and assert the LLM-facing text carries the inline
    numbered references block with clickable markdown links.

    This is the regression gate for the "clickable numbered references"
    problem — if any future refactor breaks the wiring between
    ``attach_citation_layer`` and ``envelope_to_llm_text``, this test
    fires before the LLM ever sees a references-less tool result.
    """
    envelope = build_response(
        tool_name="get_target_context",
        data={
            "disease_id": "EFO_0000756",
            "disease_name": "Melanoma",
            "associations": [
                {"target_symbol": "BRAF", "target_name": "BRAF", "score": 0.95},
                {"target_symbol": "NRAS", "target_name": "NRAS", "score": 0.80},
                {"target_symbol": "PTEN", "target_name": "PTEN", "score": 0.70},
            ],
        },
        sources=[
            {
                "kind": "opentargets",
                "id": "EFO_0000756",
                "url": "https://platform.opentargets.org/disease/EFO_0000756",
                "retrieved_at": "2026-04-09T12:00:00Z",
            }
        ],
    )
    citations = [
        Citation(
            source="Open Targets",
            id="EFO_0000756",
            url="https://platform.opentargets.org/disease/EFO_0000756",
            title="Melanoma target-disease associations",
        ),
        Citation(
            source="PubMed",
            id="12345678",
            url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
            title="BRAF in melanoma",
        ),
    ]
    enriched = attach_citation_layer(envelope, citations)
    text = envelope_to_llm_text(enriched)

    # The enriched envelope must carry the citation_layer
    assert "citation_layer" in enriched
    assert len(enriched["citation_layer"]["references"]) == 2

    # The rendered text must contain the numbered References block
    assert "## References" in text
    assert "[1]" in text
    assert "[2]" in text
    # Both references must render as clickable markdown links
    assert "https://platform.opentargets.org/disease/EFO_0000756" in text
    assert "https://pubmed.ncbi.nlm.nih.gov/12345678/" in text
    # Both references must appear in the link-reference footer too
    assert "[1]: https://platform.opentargets.org/disease/EFO_0000756" in text
    assert "[2]: https://pubmed.ncbi.nlm.nih.gov/12345678/" in text


def test_end_to_end_no_citations_means_no_references_block():
    """Baseline regression: tools that don't pass citations through
    ``attach_citation_layer`` must not produce a ``## References`` block
    (falling back to the one-line ``Sources:`` footer only)."""
    envelope = build_response(
        tool_name="get_target_context",
        data={
            "disease_id": "EFO_0000756",
            "associations": [
                {"target_symbol": "BRAF", "score": 0.95},
                {"target_symbol": "NRAS", "score": 0.80},
            ],
        },
        sources=[],
    )
    # NO attach_citation_layer call — simulating a tool that didn't
    # forward its Citation objects.
    text = envelope_to_llm_text(envelope)
    assert "## References" not in text


def test_end_to_end_inline_markdown_recipe_end_to_end():
    """End-to-end: a concept-card fallback runs through build_response
    → attach_citation_layer → envelope_to_llm_text and produces an
    inline-markdown body (not a ``:::artifact`` block) plus the numbered
    references section."""
    envelope = build_response(
        tool_name="resolve_disease",  # unknown → fallback dispatcher
        data={"query": "what is RECIST 1.1"},
        sources=[],
        query_hint="what is RECIST",
    )
    # Fallback should route to one of the compact inline recipes
    assert envelope["ui"]["recipe"] in (
        "info_card", "concept_card", "single_entity_card"
    )
    assert envelope["ui"]["artifact"]["type"] == "markdown"

    citations = [
        Citation(
            source="PubMed",
            id="9060828",
            url="https://pubmed.ncbi.nlm.nih.gov/9060828/",
            title="RECIST criteria",
        )
    ]
    enriched = attach_citation_layer(envelope, citations)
    text = envelope_to_llm_text(enriched)

    # Inline markdown path: no :::artifact{ wrapping
    assert ":::artifact" not in text
    # But the body must still be visible inline
    assert envelope["ui"]["raw"] in text
    # References block must still render
    assert "## References" in text
    assert "[1]" in text
    assert "https://pubmed.ncbi.nlm.nih.gov/9060828/" in text

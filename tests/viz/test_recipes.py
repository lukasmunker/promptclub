"""Tests for the seven recipe builders + end-to-end build_response.

All recipes now emit either ``text/html`` (six of them) or
``application/vnd.mermaid`` (``trial_timeline_gantt``). The artifact-pane
rendering path restored in April 2026 after the inline-markdown detour.
"""

from __future__ import annotations

import pytest

from app.viz import build_response
from app.viz.contract import UiPayload
from app.viz.recipes import (
    indication_dashboard,
    sponsor_pipeline_cards,
    target_associations_table,
    trial_detail_tabs,
    trial_search_results,
    trial_timeline_gantt,
    whitespace_card,
)
from app.viz.utils.mermaid import safe_label


# --- trial_search_results (HTML) -------------------------------------------


def test_trial_search_results_basic_shape(search_melanoma_phase3):
    payload = trial_search_results.build(search_melanoma_phase3)
    assert isinstance(payload, UiPayload)
    assert payload.artifact.type == "html"
    assert payload.recipe == "trial_search_results"
    assert payload.raw is not None
    assert payload.blueprint is None
    assert payload.components is None
    # HTML container structure present
    assert '<div class="grid' in payload.raw
    assert "<article" in payload.raw


def test_trial_search_results_includes_all_nct_ids(search_melanoma_phase3):
    payload = trial_search_results.build(search_melanoma_phase3)
    for hit in search_melanoma_phase3["results"]:
        assert hit["nct_id"] in payload.raw


def test_trial_search_results_escapes_html_in_cells():
    """User data is interpolated through escape_html() so tags are inert."""
    data = {
        "query": "evil",
        "results": [
            {
                "nct_id": "NCT01",
                "title": '<script>alert(1)</script>',
                "phase": "Phase 3",
                "sponsor": "Evil & Co",
            }
        ],
        "total": 1,
    }
    payload = trial_search_results.build(data)
    # Script tag must be escaped to entities, not rendered as a real tag
    assert "&lt;script&gt;" in payload.raw
    assert "<script>alert(1)</script>" not in payload.raw
    # Ampersand escaping in sponsor field
    assert "Evil &amp; Co" in payload.raw


def test_trial_search_results_caps_at_25_and_shows_more_footer():
    data = {
        "query": "many",
        "search_url": "https://clinicaltrials.gov/search?cond=many",
        "results": [
            {"nct_id": f"NCT{i:04d}", "title": f"Trial {i}", "phase": "Phase 3"}
            for i in range(40)
        ],
        "total": 40,
    }
    payload = trial_search_results.build(data)
    # 40 - 25 = 15 more
    assert "15 more" in payload.raw
    assert "NCT0024" in payload.raw  # the 25th hit
    assert "NCT0025" not in payload.raw  # 26th is beyond the cap
    # Footer links to the full search URL
    assert "clinicaltrials.gov/search?cond=many" in payload.raw


def test_trial_search_results_includes_pmid_links_for_publications():
    data = {
        "query": "pubs",
        "results": [
            {
                "pmid": "12345678",
                "title": "Great paper",
                "abstract": "lorem ipsum",
            }
        ],
        "total": 1,
    }
    payload = trial_search_results.build(data)
    # PMID badge links to PubMed
    assert "pubmed.ncbi.nlm.nih.gov/12345678" in payload.raw
    assert "PMID 12345678" in payload.raw


# --- sponsor_pipeline_cards (HTML) -----------------------------------------


def test_sponsor_pipeline_cards_groups_by_sponsor(compare_trials_many):
    payload = sponsor_pipeline_cards.build(compare_trials_many)
    assert payload.artifact.type == "html"
    # One section per unique sponsor, each with an <h2> header
    unique_sponsors = {t["sponsor"] for t in compare_trials_many["trials"]}
    for sponsor in unique_sponsors:
        assert sponsor in payload.raw
    assert "<section>" in payload.raw
    assert "<article" in payload.raw


def test_sponsor_pipeline_cards_handles_empty():
    payload = sponsor_pipeline_cards.build({"trials": [], "title": "Empty"})
    assert payload.raw is not None
    # Even with no trials, the outer container still renders
    assert '<div class="space-y-6' in payload.raw


# --- trial_timeline_gantt (Mermaid) ----------------------------------------


def test_timeline_gantt_basic(compare_trials_three):
    payload = trial_timeline_gantt.build(compare_trials_three)
    assert payload.artifact.type == "mermaid"
    # Starts with the Pharmafuse Mermaid theme init directive, then gantt
    assert payload.raw.startswith("%%{init:")
    # BioNtech brand primary appears in the init block
    assert "#179E75" in payload.raw
    assert "\ngantt\n" in payload.raw
    assert "```mermaid" not in payload.raw  # no code fence wrapping
    assert "dateFormat  YYYY-MM-DD" in payload.raw
    # All three trials should appear in the diagram
    for trial in compare_trials_three["trials"]:
        assert trial["nct_id"] in payload.raw


def test_timeline_gantt_uses_section_per_sponsor(compare_trials_three):
    payload = trial_timeline_gantt.build(compare_trials_three)
    for trial in compare_trials_three["trials"]:
        assert f"section {trial['sponsor']}" in payload.raw


def test_timeline_gantt_caps_at_15():
    trials = [
        {
            "nct_id": f"NCT{i:04d}",
            "acronym": f"TRIAL-{i}",
            "sponsor": f"Sponsor {i % 5}",
            "start_date": "2023-01-01",
            "primary_completion_date": "2026-01-01",
        }
        for i in range(25)
    ]
    payload = trial_timeline_gantt.build({"trials": trials, "query": "many"})
    assert payload.raw.count(", NCT") <= 15


def test_timeline_gantt_drops_trials_without_valid_dates():
    data = {
        "trials": [
            {
                "nct_id": "NCT01",
                "acronym": "A",
                "sponsor": "X",
                "start_date": "2023-01-01",
                "primary_completion_date": "2026-01-01",
            },
            {
                "nct_id": "NCT02",
                "acronym": "B",
                "sponsor": "Y",
                "start_date": "invalid",
                "primary_completion_date": "2026-06-01",
            },
        ]
    }
    payload = trial_timeline_gantt.build(data)
    assert "NCT01" in payload.raw
    assert "NCT02" not in payload.raw


def test_timeline_gantt_sanitizes_labels():
    data = {
        "trials": [
            {
                "nct_id": "NCT01",
                "acronym": 'PD-1 "super" inhibitor: (phase 3)',
                "sponsor": 'Sponsor: X "corp"',
                "start_date": "2023-01-01",
                "primary_completion_date": "2026-01-01",
            }
        ]
    }
    payload = trial_timeline_gantt.build(data)
    # Inspect only the task lines — the label before `:active,` must be clean
    for line in payload.raw.split("\n"):
        if ":active," in line:
            label_part = line.split(":active,", 1)[0]
            for bad in ('"', ":", "<", ">", "(", ")"):
                assert bad not in label_part, (
                    f"bad char {bad!r} in gantt label {label_part!r}"
                )


def test_safe_label_utility_direct():
    assert safe_label('A"B:C<D>E') == "ABCDE"
    assert safe_label("") == "(untitled)"
    assert safe_label(None) == "(untitled)"
    assert safe_label("a" * 100, max_length=20).endswith("…")


# --- indication_dashboard (HTML with SVG donuts) ---------------------------


def test_indication_dashboard_basic(indication_landscape_nsclc):
    payload = indication_dashboard.build(indication_landscape_nsclc)
    assert payload.artifact.type == "html"
    assert payload.recipe == "indication_dashboard"
    assert payload.raw is not None
    assert payload.blueprint is None
    assert payload.components is None
    # Page container + header present (the BioNtech-themed CARD_WRAPPER
    # forces an explicit bg-white so the artifact renders on a light
    # background regardless of LibreChat's dark-mode chrome).
    assert "bg-white" in payload.raw
    assert "p-4" in payload.raw
    assert "<h2 " in payload.raw


def test_indication_dashboard_renders_stat_tiles(indication_landscape_nsclc):
    payload = indication_dashboard.build(indication_landscape_nsclc)
    # Stat tile grid with the expected labels
    assert "Total Trials" in payload.raw
    assert "Phases" in payload.raw
    assert "Recruiting" in payload.raw
    assert "Sponsors" in payload.raw


def test_indication_dashboard_renders_phase_donut(indication_landscape_nsclc):
    payload = indication_dashboard.build(indication_landscape_nsclc)
    assert "Phase Distribution" in payload.raw
    # SVG donut is emitted as inline <svg> with <circle> slices
    assert "<svg" in payload.raw
    assert "<circle" in payload.raw


def test_indication_dashboard_renders_status_donut(indication_landscape_nsclc):
    payload = indication_dashboard.build(indication_landscape_nsclc)
    assert "Status Breakdown" in payload.raw


def test_indication_dashboard_renders_top_sponsors_table(
    indication_landscape_nsclc,
):
    from app.viz.utils.html import escape_html

    payload = indication_dashboard.build(indication_landscape_nsclc)
    assert "Top Sponsors" in payload.raw
    assert "<table" in payload.raw
    # Each sponsor name should appear, HTML-escaped so that ampersands in
    # names like "Merck Sharp & Dohme" come through as "&amp;".
    for sponsor in indication_landscape_nsclc["top_sponsors"]:
        assert escape_html(sponsor["name"]) in payload.raw


def test_indication_dashboard_caps_sponsors_at_20():
    data = {
        "indication": "mass",
        "phase_distribution": [{"phase": "1", "count": 1}, {"phase": "2", "count": 2}],
        "top_sponsors": [{"name": f"S{i}", "trials": 100 - i} for i in range(30)],
    }
    payload = indication_dashboard.build(data)
    from app.viz.recipes.indication_dashboard import _cap_sponsors

    capped = _cap_sponsors(data["top_sponsors"])
    assert len(capped) == 21  # 20 + "Other"
    assert capped[-1]["name"] == "Other"
    assert "Other" in payload.raw


def test_indication_dashboard_skips_missing_panels():
    # Only phase distribution, nothing else
    data = {
        "indication": "sparse",
        "phase_distribution": [{"phase": "1", "count": 1}, {"phase": "2", "count": 2}],
    }
    payload = indication_dashboard.build(data)
    assert "Phase Distribution" in payload.raw
    # Status / sponsors absent
    assert "Status Breakdown" not in payload.raw
    assert "Top Sponsors" not in payload.raw


# --- trial_detail_tabs (HTML sections) --------------------------------------


def test_trial_detail_tabs_basic(trial_details_nct01):
    payload = trial_detail_tabs.build(trial_details_nct01)
    assert payload.artifact.type == "html"
    assert payload.recipe == "trial_detail_tabs"
    assert payload.raw is not None
    assert payload.blueprint is None
    assert payload.components is None
    # Header NCT badge links to CT.gov
    assert "clinicaltrials.gov/study/NCT01234567" in payload.raw
    assert "<header" in payload.raw


def test_trial_detail_tabs_renders_all_sections_when_data_present(
    trial_details_nct01,
):
    payload = trial_detail_tabs.build(trial_details_nct01)
    # All 6 section headings present when the fixture has rich data
    assert "Overview" in payload.raw
    assert "Design &amp; Endpoints" in payload.raw
    assert "Eligibility" in payload.raw
    assert "Arms &amp; Interventions" in payload.raw
    assert "Sites" in payload.raw
    assert "Linked Publications" in payload.raw


def test_trial_detail_tabs_omits_sections_for_missing_data():
    minimal = {
        "nct_id": "NCT99",
        "title": "Minimal",
        "arms": [{"label": "Arm A", "type": "Experimental", "interventions": ["X"]}],
        # No design, eligibility, sites, publications
    }
    payload = trial_detail_tabs.build(minimal)
    # Arms section present
    assert "Arms &amp; Interventions" in payload.raw
    # Missing sections absent
    assert "Design &amp; Endpoints" not in payload.raw
    assert "Eligibility" not in payload.raw
    # "Linked Publications" heading should be absent; just a stray "Sites"
    # substring is possible so skip that one
    assert "Linked Publications" not in payload.raw


def test_trial_detail_tabs_header_includes_phase_and_status(trial_details_nct01):
    payload = trial_detail_tabs.build(trial_details_nct01)
    assert "Phase 3" in payload.raw
    assert "Recruiting" in payload.raw


# --- target_associations_table (HTML) --------------------------------------


def test_target_associations_table_basic():
    data = {
        "disease_id": "EFO_0000756",
        "disease_name": "melanoma",
        "associations": [
            {
                "target_symbol": "BRAF",
                "target_name": "B-Raf proto-oncogene",
                "target_id": "ENSG00000157764",
                "score": 0.92,
            },
            {
                "target_symbol": "KRAS",
                "target_name": "KRAS proto-oncogene",
                "target_id": "ENSG00000133703",
                "score": 0.81,
            },
        ],
    }
    payload = target_associations_table.build(data)
    assert payload.artifact.type == "html"
    assert payload.recipe == "target_associations_table"
    assert "<table" in payload.raw
    # Both targets present
    assert "BRAF" in payload.raw
    assert "KRAS" in payload.raw
    # Score rendered as two decimal places
    assert "0.92" in payload.raw
    assert "0.81" in payload.raw
    # Open Targets disease link in the header
    assert "platform.opentargets.org/disease/EFO_0000756" in payload.raw


def test_target_associations_table_sorts_by_score():
    data = {
        "disease_id": "EFO_x",
        "disease_name": "test",
        "associations": [
            {"target_symbol": "LOW", "score": 0.1},
            {"target_symbol": "HIGH", "score": 0.9},
            {"target_symbol": "MID", "score": 0.5},
        ],
    }
    payload = target_associations_table.build(data)
    high_idx = payload.raw.index("HIGH")
    mid_idx = payload.raw.index("MID")
    low_idx = payload.raw.index("LOW")
    assert high_idx < mid_idx < low_idx


# --- whitespace_card (HTML stat tiles) --------------------------------------


_WHITESPACE_FIXTURE = {
    "condition": "non-small cell lung cancer",
    "trial_counts_by_phase": {"phase_1": 42, "phase_2": 78, "phase_3": 35},
    "trial_counts_by_status": {"recruiting": 95, "completed": 38},
    "pubmed_publications_3yr": 1200,
    "fda_label_records": 8,
    "identified_whitespace": [
        "Few Phase 3 trials — late-stage evidence lacking",
        "Limited recent publications relative to trial volume",
    ],
}


def test_whitespace_card_basic_shape():
    payload = whitespace_card.build(_WHITESPACE_FIXTURE)
    assert isinstance(payload, UiPayload)
    assert payload.recipe == "whitespace_card"
    assert payload.artifact.type == "html"
    assert payload.raw is not None
    assert payload.blueprint is None
    assert payload.components is None
    # Header + stat grid + signals section
    assert "<header" in payload.raw
    assert "Phase 1" in payload.raw
    assert "Identified Whitespace Signals" in payload.raw


def test_whitespace_card_renders_all_phase_counts():
    payload = whitespace_card.build(_WHITESPACE_FIXTURE)
    # Counts are rendered with German thousand-separator style (dot)
    assert "42" in payload.raw
    assert "78" in payload.raw
    assert "35" in payload.raw
    # Publications value is 1200 → formatted as "1.200"
    assert "1.200" in payload.raw


def test_whitespace_card_renders_all_signals():
    payload = whitespace_card.build(_WHITESPACE_FIXTURE)
    for signal in _WHITESPACE_FIXTURE["identified_whitespace"]:
        # Signal text is HTML-escaped: the em-dash passes through unchanged
        assert signal in payload.raw


def test_whitespace_card_escapes_script_tags_in_signals():
    data = {
        **_WHITESPACE_FIXTURE,
        "identified_whitespace": ['<script>alert("xss")</script>', "ok signal"],
    }
    payload = whitespace_card.build(data)
    # The script substring should be HTML-escaped (&lt;script&gt;...)
    assert "&lt;script&gt;" in payload.raw
    # The literal <script> string must NOT appear as an actual tag
    assert "<script>alert" not in payload.raw
    assert "ok signal" in payload.raw


def test_whitespace_card_handles_missing_counts():
    data = {
        "condition": "rare condition",
        "identified_whitespace": ["No trials in any phase"],
    }
    payload = whitespace_card.build(data)
    # Placeholder em-dash for missing count tiles
    assert "—" in payload.raw
    assert "No trials in any phase" in payload.raw


def test_whitespace_card_handles_no_signals():
    data = {
        **_WHITESPACE_FIXTURE,
        "identified_whitespace": [],
    }
    payload = whitespace_card.build(data)
    assert "No specific whitespace signals" in payload.raw


# --- End-to-end build_response ---------------------------------------------


def test_build_response_search_with_sources(
    search_melanoma_phase3, sources_clinicaltrials
):
    envelope = build_response(
        "search_clinical_trials",
        search_melanoma_phase3,
        sources=sources_clinicaltrials,
    )
    assert "render_hint" in envelope
    assert envelope["ui"]["recipe"] == "trial_search_results"
    assert envelope["ui"]["artifact"]["type"] == "html"
    assert "raw" in envelope["ui"]
    # HTML recipes should not include components/blueprint (stripped by exclude_none)
    assert "components" not in envelope["ui"]
    assert "blueprint" not in envelope["ui"]
    # render_hint tells the LLM to emit an :::artifact directive
    assert ":::artifact" in envelope["render_hint"]
    assert "html" in envelope["render_hint"]
    # Sources preserved
    assert len(envelope["sources"]) == 1
    assert envelope["sources"][0]["kind"] == "clinicaltrials.gov"


def test_build_response_indication_dashboard_is_html(indication_landscape_nsclc):
    envelope = build_response(
        "get_indication_landscape", indication_landscape_nsclc, sources=[]
    )
    assert envelope["ui"]["artifact"]["type"] == "html"
    assert envelope["ui"]["recipe"] == "indication_dashboard"
    assert "raw" in envelope["ui"]
    assert "components" not in envelope["ui"]
    assert "blueprint" not in envelope["ui"]


def test_build_response_skip_has_no_ui(search_empty):
    envelope = build_response("search_clinical_trials", search_empty, sources=[])
    # Post-Task-10: SKIP path now routes through fallback, ui is always populated
    assert envelope.get("ui") is not None
    assert envelope["ui"]["recipe"] in ("info_card", "concept_card", "single_entity_card")
    assert envelope["data"]["total"] == 0


def test_build_response_with_pydantic_source_instances(search_melanoma_phase3):
    from datetime import datetime, timezone

    from app.viz.contract import Source

    src = Source(
        kind="pubmed",
        id="12345678",
        url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        retrieved_at=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
    )
    envelope = build_response(
        "search_clinical_trials", search_melanoma_phase3, sources=[src]
    )
    assert envelope["sources"][0]["kind"] == "pubmed"


def test_build_response_unknown_tool_returns_text_fallback():
    envelope = build_response("unknown_tool", {"anything": True}, sources=[])
    # Post-Task-10: unknown tool routes through fallback, ui is always populated
    assert envelope.get("ui") is not None
    # Post-Task-13: enrichment adds knowledge_annotations (may be empty)
    assert envelope["data"]["anything"] is True
    assert "knowledge_annotations" in envelope["data"]


def test_build_response_compare_trials_gantt(compare_trials_three):
    envelope = build_response(
        "compare_trials", compare_trials_three, sources=[]
    )
    assert envelope["ui"]["recipe"] == "trial_timeline_gantt"
    assert envelope["ui"]["artifact"]["type"] == "mermaid"
    # Starts with the Pharmafuse Mermaid theme init directive
    assert envelope["ui"]["raw"].startswith("%%{init:")
    assert "\ngantt\n" in envelope["ui"]["raw"]
    assert "```mermaid" not in envelope["ui"]["raw"]


def test_build_response_compare_many_trials_cards(compare_trials_many):
    envelope = build_response(
        "compare_trials", compare_trials_many, sources=[]
    )
    # 18 trials > 15 cap → should use cards
    assert envelope["ui"]["recipe"] == "sponsor_pipeline_cards"
    assert envelope["ui"]["artifact"]["type"] == "html"


def test_build_response_trial_details_rich(trial_details_nct01):
    envelope = build_response(
        "get_trial_details", trial_details_nct01, sources=[]
    )
    assert envelope["ui"]["recipe"] == "trial_detail_tabs"
    assert envelope["ui"]["artifact"]["type"] == "html"
    assert "raw" in envelope["ui"]
    assert "components" not in envelope["ui"]
    assert "blueprint" not in envelope["ui"]


from app.viz.recipes import info_card


def test_info_card_renders_with_minimal_input():
    """Empty data must produce a valid UiPayload — this is the universal
    catch-all for the coverage guarantee. The three small fallback recipes
    (info / concept / single-entity card) emit ``markdown`` artifacts so
    they render inline in the chat, not in the artifact side pane."""
    payload = info_card.build({}, sources=[])
    assert payload.recipe == "info_card"
    assert payload.artifact.type == "markdown"
    assert payload.raw is not None
    assert len(payload.raw) > 0


def test_info_card_renders_with_title_and_bullets():
    data = {
        "title": "Search Results",
        "bullets": ["12 trials found", "5 sponsors", "3 phases"],
        "subtitle": "Pembrolizumab in NSCLC",
    }
    payload = info_card.build(data, sources=[])
    assert "Search Results" in payload.raw
    assert "12 trials found" in payload.raw
    assert "Pembrolizumab in NSCLC" in payload.raw


def test_info_card_handles_empty_results():
    data = {
        "title": "No results",
        "subtitle": "Adverse events for drug X",
        "no_results_hint": "Sources checked: openfda, ema",
    }
    payload = info_card.build(data, sources=[])
    assert "No results" in payload.raw
    assert "Sources checked" in payload.raw


def test_info_card_escapes_html():
    data = {"title": "<script>alert(1)</script>"}
    payload = info_card.build(data, sources=[])
    assert "<script>" not in payload.raw
    assert "&lt;script&gt;" in payload.raw


from app.viz.recipes import concept_card


def test_concept_card_renders_definition():
    data = {
        "term": "RECIST 1.1",
        "definition": "Response Evaluation Criteria In Solid Tumors, version 1.1.",
        "category": "response-criterion",
    }
    payload = concept_card.build(data, sources=[])
    assert payload.recipe == "concept_card"
    assert "RECIST 1.1" in payload.raw
    assert "Response Evaluation Criteria" in payload.raw


def test_concept_card_renders_with_extended_context():
    data = {
        "term": "Overall Survival",
        "definition": "Time from randomization to death from any cause.",
        "context": "Considered the gold standard endpoint in oncology trials.",
    }
    payload = concept_card.build(data, sources=[])
    assert "Overall Survival" in payload.raw
    assert "gold standard" in payload.raw


def test_concept_card_handles_minimal_input():
    payload = concept_card.build({"term": "Phase 3"}, sources=[])
    assert "Phase 3" in payload.raw


from app.viz.recipes import single_entity_card


def test_single_entity_card_renders_a_trial():
    data = {
        "kind": "trial",
        "title": "NCT01234567",
        "subtitle": "A Phase 3 study of pembrolizumab in NSCLC",
        "facts": [
            ("Phase", "3"),
            ("Status", "Recruiting"),
            ("Sponsor", "Merck"),
            ("Enrollment", "2,500"),
        ],
    }
    payload = single_entity_card.build(data, sources=[])
    assert payload.recipe == "single_entity_card"
    assert "NCT01234567" in payload.raw
    assert "Phase" in payload.raw
    assert "Recruiting" in payload.raw
    assert "Merck" in payload.raw


def test_single_entity_card_renders_a_drug():
    data = {
        "kind": "drug",
        "title": "Pembrolizumab",
        "subtitle": "PD-1 inhibitor",
        "facts": [
            ("Class", "Monoclonal antibody"),
            ("Approval", "FDA approved 2014"),
        ],
    }
    payload = single_entity_card.build(data, sources=[])
    assert "Pembrolizumab" in payload.raw
    assert "PD-1 inhibitor" in payload.raw


def test_single_entity_card_handles_no_facts():
    data = {"kind": "trial", "title": "NCT00000000"}
    payload = single_entity_card.build(data, sources=[])
    assert "NCT00000000" in payload.raw


def test_new_recipes_in_registry():
    from app.viz.recipes import REGISTRY

    assert "info_card" in REGISTRY
    assert "concept_card" in REGISTRY
    assert "single_entity_card" in REGISTRY

    # Each registry entry must be a callable that produces a UiPayload
    for name in ("info_card", "concept_card", "single_entity_card"):
        builder = REGISTRY[name]
        payload = builder({}, sources=[])
        assert payload.recipe == name


def test_info_card_renders_glossary_when_annotations_present():
    """When the data dict carries knowledge_annotations, info_card
    appends a glossary footer block."""
    data = {
        "title": "Search Results",
        "bullets": ["Phase 3 study found"],
        "knowledge_annotations": [
            {
                "field_path": "results[0].phase",
                "matched_term": "phase 3",
                "lexicon_id": "trial-phase-3",
                "short_definition": "Late-stage trial confirming efficacy.",
                "clinical_context": "Phase 3 trials enroll hundreds to thousands.",
                "review_status": "reviewed",
            }
        ],
    }
    payload = info_card.build(data, sources=[])
    assert "Glossary" in payload.raw
    assert "phase 3" in payload.raw.lower()
    assert "Late-stage trial" in payload.raw


def test_info_card_no_glossary_when_no_annotations():
    data = {"title": "Result", "bullets": ["x"]}
    payload = info_card.build(data, sources=[])
    assert "Glossary" not in payload.raw


def test_info_card_glossary_dedupes_lexicon_ids():
    """Multiple annotations for the same lexicon_id should appear once."""
    data = {
        "title": "Result",
        "knowledge_annotations": [
            {
                "field_path": "a", "matched_term": "phase 3", "lexicon_id": "trial-phase-3",
                "short_definition": "Late-stage trial.", "clinical_context": "x",
                "review_status": "reviewed",
            },
            {
                "field_path": "b", "matched_term": "phase 3", "lexicon_id": "trial-phase-3",
                "short_definition": "Late-stage trial.", "clinical_context": "x",
                "review_status": "reviewed",
            },
        ],
    }
    payload = info_card.build(data, sources=[])
    # Glossary appears once for the unique lexicon_id
    assert payload.raw.count("Late-stage trial") == 1

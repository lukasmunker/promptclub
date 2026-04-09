"""Tests for app.viz.adapters — promptclub → pharmafuse-mcp viz shape translation.

These tests construct promptclub Pydantic models, call the adapter, and
verify that the resulting envelope is a valid pharmafuse-mcp viz output.
"""

from __future__ import annotations

from app.models import (
    Citation,
    ComparisonResponse,
    PublicationRecord,
    TargetAssociationRecord,
    TrialRecord,
    WebContextRecord,
)
from app.viz.adapters import (
    build_response_from_promptclub,
    normalize_citations_to_sources,
)


# --- normalize_citations_to_sources -----------------------------------------


def test_normalize_citations_drops_entries_without_url():
    citations = [
        {"source": "PubMed", "id": "123", "url": None, "title": "x"},
        {"source": "PubMed", "id": "456", "url": "https://pubmed.ncbi.nlm.nih.gov/456/", "title": "y"},
    ]
    out = normalize_citations_to_sources(citations)
    assert len(out) == 1
    assert out[0]["id"] == "456"
    assert out[0]["kind"] == "pubmed"


def test_normalize_citations_maps_all_source_kinds():
    citations = [
        {"source": "ClinicalTrials.gov", "id": "NCT01", "url": "https://clinicaltrials.gov/study/NCT01"},
        {"source": "PubMed", "id": "123", "url": "https://pubmed.ncbi.nlm.nih.gov/123/"},
        {"source": "openFDA", "id": "NDA0001", "url": "https://api.fda.gov/drug/NDA0001"},
        {"source": "Open Targets", "id": "ENSG", "url": "https://platform.opentargets.org/target/ENSG"},
        {"source": "Vertex Google Search", "id": "w1", "url": "https://example.com/news"},
    ]
    out = normalize_citations_to_sources(citations)
    kinds = {entry["kind"] for entry in out}
    assert kinds == {"clinicaltrials.gov", "pubmed", "openfda", "opentargets", "web"}


def test_normalize_citations_deduplicates():
    citations = [
        {"source": "PubMed", "id": "123", "url": "https://pubmed.ncbi.nlm.nih.gov/123/"},
        {"source": "PubMed", "id": "123", "url": "https://pubmed.ncbi.nlm.nih.gov/123/"},
    ]
    out = normalize_citations_to_sources(citations)
    assert len(out) == 1


def test_normalize_citations_includes_retrieved_at():
    citations = [
        {"source": "PubMed", "id": "123", "url": "https://pubmed.ncbi.nlm.nih.gov/123/"}
    ]
    out = normalize_citations_to_sources(citations)
    assert "retrieved_at" in out[0]
    # ISO 8601 UTC with Z suffix
    assert out[0]["retrieved_at"].endswith("Z")


# --- search_trials adapter --------------------------------------------------


def test_search_trials_envelope_from_comparison_response():
    trial_1 = TrialRecord(
        source="ClinicalTrials.gov",
        source_id="NCT01234567",
        nct_id="NCT01234567",
        title="Pembrolizumab Trial",
        phase=["Phase 3"],
        status="Recruiting",
        sponsor="Sponsor A",
        enrollment=450,
        start_date="2023-05-01",
        completion_date="2026-12-01",
        primary_endpoints=["Overall Survival"],
        citations=[
            Citation(
                source="ClinicalTrials.gov",
                id="NCT01234567",
                url="https://clinicaltrials.gov/study/NCT01234567",
                title="Pembrolizumab Trial",
            )
        ],
    )
    trial_2 = TrialRecord(
        source="ClinicalTrials.gov",
        source_id="NCT02345678",
        nct_id="NCT02345678",
        title="Nivolumab Trial",
        phase=["Phase 3"],
        status="Active, not recruiting",
        sponsor="Sponsor B",
        enrollment=320,
        start_date="2024-01-15",
        completion_date="2027-06-30",
        citations=[
            Citation(
                source="ClinicalTrials.gov",
                id="NCT02345678",
                url="https://clinicaltrials.gov/study/NCT02345678",
            )
        ],
    )
    response = ComparisonResponse(
        summary="Found 2 trials",
        trials=[trial_1, trial_2],
    )

    env = build_response_from_promptclub(
        tool_name="search_trials",
        promptclub_data=response.model_dump(),
        query="melanoma",
    )

    assert "render_hint" in env
    assert "Cite sources" in env["render_hint"]
    assert "No forward-looking" in env["render_hint"]
    assert env["ui"]["recipe"] == "trial_search_results"
    assert env["ui"]["artifact"]["type"] == "html"
    # Both NCT IDs should appear in the rendered HTML card list
    assert "NCT01234567" in env["ui"]["raw"]
    assert "NCT02345678" in env["ui"]["raw"]
    # And in sources
    assert len(env["sources"]) == 2
    assert all(s["kind"] == "clinicaltrials.gov" for s in env["sources"])


def test_search_trials_single_hit_skips_visualization():
    trial = TrialRecord(
        source="ClinicalTrials.gov",
        source_id="NCT01234567",
        nct_id="NCT01234567",
        title="Only Trial",
        phase=["Phase 3"],
        sponsor="Sponsor",
    )
    response = ComparisonResponse(summary="Only 1 found", trials=[trial])
    env = build_response_from_promptclub(
        tool_name="search_trials",
        promptclub_data=response.model_dump(),
        query="rare",
    )
    # Post-Task-10: SKIP path routes through fallback, ui is always populated
    assert env.get("ui") is not None


def test_search_trials_flattens_phase_list():
    trial = TrialRecord(
        source="ClinicalTrials.gov",
        source_id="NCT01",
        nct_id="NCT01",
        title="Multi phase",
        phase=["Phase 2", "Phase 3"],  # list!
        sponsor="S",
        status="Recruiting",
    )
    trial2 = TrialRecord(
        source="ClinicalTrials.gov",
        source_id="NCT02",
        nct_id="NCT02",
        title="Other",
        phase=["Phase 3"],
        sponsor="T",
        status="Recruiting",
    )
    response = ComparisonResponse(summary="Found 2", trials=[trial, trial2])
    env = build_response_from_promptclub(
        tool_name="search_trials",
        promptclub_data=response.model_dump(),
        query="x",
    )
    # Phase 2/3 should be collapsed into a single slash-joined string in the raw markdown
    assert "Phase 2/Phase 3" in env["ui"]["raw"]


# --- get_trial_details adapter ----------------------------------------------


def test_trial_details_not_found_returns_plain_envelope():
    env = build_response_from_promptclub(
        tool_name="get_trial_details",
        promptclub_data={"found": False, "nct_id": "NCT99999999"},
    )
    # Post-Task-10: SKIP path routes through fallback, ui is always populated
    assert env.get("ui") is not None
    assert env["data"]["found"] is False


def test_trial_details_rich_produces_tab_view():
    trial = TrialRecord(
        source="ClinicalTrials.gov",
        source_id="NCT01",
        nct_id="NCT01",
        title="Deep trial",
        phase=["Phase 3"],
        status="Recruiting",
        sponsor="Sponsor",
        enrollment=200,
        start_date="2023-01-01",
        completion_date="2026-01-01",
        interventions=["Pembrolizumab", "Placebo"],
        primary_endpoints=["Overall Survival", "PFS"],
        inclusion_criteria="Age >= 18",
        exclusion_criteria="Prior treatment",
        locations=["Site A", "Site B"],
        citations=[
            Citation(
                source="ClinicalTrials.gov",
                id="NCT01",
                url="https://clinicaltrials.gov/study/NCT01",
            )
        ],
    )
    env = build_response_from_promptclub(
        tool_name="get_trial_details",
        promptclub_data={"found": True, "trial": trial.model_dump()},
    )
    assert env["ui"]["recipe"] == "trial_detail_tabs"
    # Rebuilt as HTML sections after Sandpack crash — no more React blueprint.
    assert env["ui"]["artifact"]["type"] == "html"
    assert "raw" in env["ui"]
    # Section headers from the rich data are present (ampersand HTML-escaped)
    raw = env["ui"]["raw"]
    assert "Arms &amp; Interventions" in raw or "Overview" in raw


# --- search_publications adapter --------------------------------------------


def test_search_publications_envelope():
    pubs = [
        PublicationRecord(
            pmid="11111",
            title="First paper",
            journal="NEJM",
            pub_date="2024",
            abstract="First abstract.",
            citations=[
                Citation(
                    source="PubMed",
                    id="11111",
                    url="https://pubmed.ncbi.nlm.nih.gov/11111/",
                    title="First paper",
                )
            ],
        ),
        PublicationRecord(
            pmid="22222",
            title="Second paper",
            journal="Lancet",
            pub_date="2024",
            abstract="Second abstract.",
            citations=[
                Citation(
                    source="PubMed",
                    id="22222",
                    url="https://pubmed.ncbi.nlm.nih.gov/22222/",
                )
            ],
        ),
    ]
    env = build_response_from_promptclub(
        tool_name="search_publications",
        promptclub_data={"count": 2, "results": [p.model_dump() for p in pubs]},
        query="melanoma",
    )
    assert env["ui"]["recipe"] == "trial_search_results"
    assert env["ui"]["artifact"]["type"] == "html"
    # PMIDs appear as badges linking to PubMed
    assert "11111" in env["ui"]["raw"]
    assert "22222" in env["ui"]["raw"]
    assert "pubmed.ncbi.nlm.nih.gov" in env["ui"]["raw"]
    assert len(env["sources"]) == 2
    assert all(s["kind"] == "pubmed" for s in env["sources"])


# --- get_target_context adapter (new recipe) --------------------------------


def test_target_context_envelope():
    rows = [
        TargetAssociationRecord(
            disease_id="EFO_0000756",
            disease_name="melanoma",
            target_id="ENSG00000157764",
            target_symbol="BRAF",
            target_name="B-Raf proto-oncogene",
            score=0.92,
            citations=[
                Citation(
                    source="Open Targets",
                    id="ENSG00000157764",
                    url="https://platform.opentargets.org/target/ENSG00000157764",
                )
            ],
        ),
        TargetAssociationRecord(
            disease_id="EFO_0000756",
            disease_name="melanoma",
            target_id="ENSG00000133703",
            target_symbol="KRAS",
            target_name="KRAS proto-oncogene",
            score=0.78,
            citations=[
                Citation(
                    source="Open Targets",
                    id="ENSG00000133703",
                    url="https://platform.opentargets.org/target/ENSG00000133703",
                )
            ],
        ),
        TargetAssociationRecord(
            disease_id="EFO_0000756",
            disease_name="melanoma",
            target_id="ENSG00000141510",
            target_symbol="TP53",
            target_name="Tumor Protein p53",
            score=0.65,
        ),
    ]
    env = build_response_from_promptclub(
        tool_name="get_target_context",
        promptclub_data={"count": 3, "results": [r.model_dump() for r in rows]},
        disease_id="EFO_0000756",
    )
    assert env["ui"]["recipe"] == "target_associations_table"
    assert env["ui"]["artifact"]["type"] == "html"
    # All three symbols present in the rendered HTML table
    assert "BRAF" in env["ui"]["raw"]
    assert "KRAS" in env["ui"]["raw"]
    assert "TP53" in env["ui"]["raw"]
    # Sorted by score descending — BRAF should appear before TP53 in raw order
    assert env["ui"]["raw"].index("BRAF") < env["ui"]["raw"].index("TP53")


def test_target_context_single_association_skips():
    rows = [
        TargetAssociationRecord(
            disease_id="EFO_00001",
            disease_name="x",
            target_symbol="BRAF",
            score=0.5,
        )
    ]
    env = build_response_from_promptclub(
        tool_name="get_target_context",
        promptclub_data={"count": 1, "results": [r.model_dump() for r in rows]},
        disease_id="EFO_00001",
    )
    # Post-Task-10: SKIP path routes through fallback, ui is always populated
    assert env.get("ui") is not None


# --- web_context_search adapter ---------------------------------------------


def test_web_context_envelope():
    rows = [
        WebContextRecord(
            answer="Recent news about BioNTech's mRNA melanoma trial...",
            citations=[
                Citation(
                    source="Vertex Google Search",
                    id="w1",
                    url="https://example.com/news-1",
                    title="BioNTech mRNA trial news",
                )
            ],
        ),
        WebContextRecord(
            answer="Another piece of context...",
            citations=[
                Citation(
                    source="Vertex Google Search",
                    id="w2",
                    url="https://example.com/news-2",
                    title="Another source",
                )
            ],
        ),
    ]
    env = build_response_from_promptclub(
        tool_name="web_context_search",
        promptclub_data={"count": 2, "results": [r.model_dump() for r in rows]},
        query="melanoma BioNTech",
    )
    assert env["ui"]["recipe"] == "trial_search_results"
    assert env["ui"]["artifact"]["type"] == "html"
    assert len(env["sources"]) == 2
    assert all(s["kind"] == "web" for s in env["sources"])


# --- get_regulatory_context (no recipe, text fallback) ----------------------


def test_regulatory_context_skips():
    env = build_response_from_promptclub(
        tool_name="get_regulatory_context",
        promptclub_data={"count": 0, "results": []},
    )
    # Post-Task-10: no recipe wired, but fallback always emits ui
    assert env.get("ui") is not None
    assert env["ui"]["recipe"] in ("info_card", "concept_card", "single_entity_card")


# --- build_trial_comparison adapter (NEW) -----------------------------------


def test_build_trial_comparison_envelope_renders_gantt():
    """3 trials with valid dates → trial_timeline_gantt."""
    trials = [
        TrialRecord(
            source="ClinicalTrials.gov",
            source_id=f"NCT0000000{i}",
            nct_id=f"NCT0000000{i}",
            title=f"Comparison Trial {i}",
            phase=["Phase 3"],
            sponsor=f"Sponsor {chr(64+i)}",
            status="Recruiting",
            start_date=f"2023-0{i}-01",
            completion_date=f"2026-0{i}-01",
        )
        for i in range(1, 4)
    ]
    env = build_response_from_promptclub(
        tool_name="build_trial_comparison",
        promptclub_data={
            "count": 3,
            "trials": [t.model_dump() for t in trials],
            "errors": [],
        },
    )
    assert env["ui"]["recipe"] == "trial_timeline_gantt"
    assert env["ui"]["artifact"]["type"] == "mermaid"
    raw = env["ui"]["raw"]
    # Starts with the Pharmafuse Mermaid theme directive, then the gantt
    assert raw.startswith("%%{init:")
    assert "\ngantt\n" in raw
    assert "```mermaid" not in raw
    assert "NCT00000001" in raw
    assert "NCT00000002" in raw
    assert "NCT00000003" in raw
    # Sections per sponsor
    assert "section Sponsor A" in raw
    assert "section Sponsor B" in raw


def test_build_trial_comparison_single_trial_skips():
    trial = TrialRecord(
        source="ClinicalTrials.gov",
        source_id="NCT01",
        nct_id="NCT01",
        title="Only one",
        phase=["Phase 3"],
        sponsor="S",
        start_date="2023-01-01",
        completion_date="2026-01-01",
    )
    env = build_response_from_promptclub(
        tool_name="build_trial_comparison",
        promptclub_data={"count": 1, "trials": [trial.model_dump()], "errors": []},
    )
    # Post-Task-10: SKIP path routes through fallback, ui is always populated
    assert env.get("ui") is not None


def test_build_trial_comparison_missing_dates_falls_back_to_cards():
    trials = [
        TrialRecord(
            source="ClinicalTrials.gov",
            source_id="NCT01",
            nct_id="NCT01",
            title="No dates 1",
            phase=["Phase 3"],
            sponsor="A",
            # no start_date / completion_date
        ),
        TrialRecord(
            source="ClinicalTrials.gov",
            source_id="NCT02",
            nct_id="NCT02",
            title="No dates 2",
            phase=["Phase 3"],
            sponsor="B",
        ),
    ]
    env = build_response_from_promptclub(
        tool_name="build_trial_comparison",
        promptclub_data={
            "count": 2,
            "trials": [t.model_dump() for t in trials],
            "errors": [],
        },
    )
    # Decision falls back to sponsor_pipeline_cards when dates are missing
    assert env["ui"]["recipe"] == "sponsor_pipeline_cards"
    assert env["ui"]["artifact"]["type"] == "html"


# --- analyze_whitespace adapter + recipe (NEW) ------------------------------


def test_analyze_whitespace_envelope_renders_card():
    payload = {
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
    env = build_response_from_promptclub(
        tool_name="analyze_whitespace",
        promptclub_data=payload,
    )
    assert env["ui"]["recipe"] == "whitespace_card"
    assert env["ui"]["artifact"]["type"] == "html"
    raw = env["ui"]["raw"]
    # All numbers surface in the rendered HTML stat tiles
    assert "42" in raw
    assert "78" in raw
    assert "35" in raw
    assert "95" in raw
    # Both signals rendered in the warning-styled list
    assert "Few Phase 3 trials" in raw
    assert "Limited recent publications" in raw
    # Title includes the condition
    assert "non-small cell lung cancer" in env["ui"]["artifact"]["title"]


def test_analyze_whitespace_empty_data_skips():
    env = build_response_from_promptclub(
        tool_name="analyze_whitespace",
        promptclub_data={
            "condition": "rare",
            "trial_counts_by_phase": {},
            "trial_counts_by_status": {},
            "identified_whitespace": [],
        },
    )
    # Post-Task-10: SKIP path routes through fallback, ui is always populated
    assert env.get("ui") is not None


# --- analyze_indication_landscape + get_sponsor_overview text-only ---------


def test_analyze_indication_landscape_text_only():
    env = build_response_from_promptclub(
        tool_name="analyze_indication_landscape",
        promptclub_data={
            "condition": "NSCLC",
            "phase_filter": None,
            "clinical_trials_count": 1234,
            "pubmed_publications_3yr": 5678,
            "fda_label_records": 12,
            "disease_ontology": [],
        },
    )
    # Post-Task-10: flat aggregate counts route through fallback, ui is always populated
    assert env.get("ui") is not None
    assert env["ui"]["recipe"] in ("info_card", "concept_card", "single_entity_card")


def test_get_sponsor_overview_text_only():
    env = build_response_from_promptclub(
        tool_name="get_sponsor_overview",
        promptclub_data={
            "condition": "melanoma",
            "total_trials_sampled": 25,
            "unique_sponsors": 12,
            "sponsor_trial_counts": [
                {"sponsor": "Merck", "trial_count": 5},
                {"sponsor": "Roche", "trial_count": 4},
            ],
        },
    )
    # Post-Task-10: no recipe wired, but fallback always emits ui
    assert env.get("ui") is not None

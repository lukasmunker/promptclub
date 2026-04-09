from app.citations import attach_citation_layer, build_citation_layer, citations_from_rows
from app.models import (
    Citation,
    ComparisonResponse,
    KnownDrugRecord,
    PublicationRecord,
    RegulatoryRecord,
    TargetAssociationRecord,
    TrialRecord,
)
from app.utils import lean_dump


def test_trial_model():
    obj = TrialRecord(source="ClinicalTrials.gov", source_id="NCT00000000")
    assert obj.source == "ClinicalTrials.gov"


def test_publication_model():
    obj = PublicationRecord(pmid="12345")
    assert obj.pmid == "12345"


def test_target_model():
    obj = TargetAssociationRecord(target_id="ENSG000001")
    assert obj.target_id == "ENSG000001"


def test_regulatory_model():
    obj = RegulatoryRecord(product_name="ExampleDrug")
    assert obj.product_name == "ExampleDrug"


def test_lean_dump_strips_top_level_raw():
    rec = TrialRecord(source="ct", source_id="x", raw={"big": "payload"})
    out = lean_dump(rec)
    assert "raw" not in out
    assert out["source_id"] == "x"


def test_lean_dump_keeps_non_raw_fields():
    rec = PublicationRecord(pmid="123", title="t", abstract="a", raw={"xml": "long"})
    out = lean_dump(rec)
    assert "raw" not in out
    assert out["pmid"] == "123"
    assert out["title"] == "t"
    assert out["abstract"] == "a"


def test_lean_dump_strips_nested_raw_in_comparison_response():
    response = ComparisonResponse(
        summary="x",
        trials=[TrialRecord(source="ct", source_id="t1", raw={"x": 1})],
        publications=[PublicationRecord(pmid="123", raw={"xml": "long"})],
    )
    out = lean_dump(response)
    assert "raw" not in out["trials"][0]
    assert "raw" not in out["publications"][0]
    assert out["trials"][0]["source_id"] == "t1"
    assert out["publications"][0]["pmid"] == "123"


def test_lean_dump_handles_plain_dict_input():
    out = lean_dump({"a": 1, "raw": {"big": True}, "nested": [{"raw": "x", "k": "v"}]})
    assert out == {"a": 1, "nested": [{"k": "v"}]}


# ---------------------------------------------------------------------------
# evidence_path + KnownDrugRecord (deterministic-joins-provenance PR)
# ---------------------------------------------------------------------------


def test_trial_record_has_evidence_path_default_empty():
    rec = TrialRecord(source="ct", source_id="NCT01")
    assert rec.evidence_path == []


def test_publication_record_evidence_path_roundtrip_through_lean_dump():
    pub = PublicationRecord(
        pmid="12345",
        title="t",
        evidence_path=[
            "ctgov:NCT01227889",
            "ctgov.referencesModule.pmid:12345",
            "pubmed:12345",
        ],
        raw={"xml": "should be stripped"},
    )
    out = lean_dump(pub)
    assert "raw" not in out
    assert out["evidence_path"] == [
        "ctgov:NCT01227889",
        "ctgov.referencesModule.pmid:12345",
        "pubmed:12345",
    ]


def test_known_drug_record_minimal():
    rec = KnownDrugRecord(
        target_id="ENSG00000188389",
        target_symbol="PDCD1",
        drug_id="CHEMBL1201580",
        drug_name="PEMBROLIZUMAB",
        drug_type="Antibody",
        max_clinical_stage="APPROVAL",
        trade_names=["Keytruda"],
        indications=["melanoma", "non-small cell lung carcinoma"],
        indication_ids=["EFO_0000756", "EFO_0003060"],
        trial_ids=["NCT01295827", "NCT02142738"],
        evidence_path=[
            "opentargets:target/ENSG00000188389",
            "opentargets:drug/CHEMBL1201580",
            "opentargets:drugAndClinicalCandidates",
        ],
    )
    assert rec.target_symbol == "PDCD1"
    assert rec.drug_name == "PEMBROLIZUMAB"
    assert "Keytruda" in rec.trade_names
    assert len(rec.evidence_path) == 3
    out = lean_dump(rec)
    assert "raw" not in out
    assert out["drug_name"] == "PEMBROLIZUMAB"
    assert out["evidence_path"][0] == "opentargets:target/ENSG00000188389"


# ---------------------------------------------------------------------------
# Orchestrator branch tests: deterministic linked_pmids vs regex fallback
# ---------------------------------------------------------------------------

import pytest
from unittest.mock import AsyncMock

from app.services.orchestration import Orchestrator


@pytest.mark.asyncio
async def test_orchestrator_uses_linked_pmids_when_available():
    """When CT.gov populates referencesModule.references[].pmid, the orchestrator
    must call PubMedAdapter.fetch_publications_by_pmids (deterministic) and NOT
    PubMedAdapter.get_publications_for_trial (regex fallback). Each returned
    publication must carry the full chain in its evidence_path."""
    orch = Orchestrator()
    trial = TrialRecord(
        source="ClinicalTrials.gov",
        source_id="NCT01",
        nct_id="NCT01",
        linked_pmids=["12345", "67890"],
    )
    pub = PublicationRecord(pmid="12345", title="paper-from-references-module")

    orch.ct.search_trials = AsyncMock(return_value=[trial])
    orch.pubmed.fetch_publications_by_pmids = AsyncMock(return_value=[pub])
    orch.pubmed.get_publications_for_trial = AsyncMock(return_value=[])

    result = await orch.search_trials_with_publications(disease_query="test")

    orch.pubmed.fetch_publications_by_pmids.assert_called_once_with(["12345", "67890"])
    orch.pubmed.get_publications_for_trial.assert_not_called()
    assert len(result.publications) == 1
    ev = result.publications[0].evidence_path
    assert "ctgov:NCT01" in ev
    assert "ctgov.referencesModule.pmid:12345" in ev
    assert "pubmed:12345" in ev
    assert "via CT.gov referencesModule" in result.summary
    assert "1 via CT.gov referencesModule, 0 via abstract regex fallback" in result.summary


@pytest.mark.asyncio
async def test_orchestrator_falls_back_to_regex_when_no_linked_pmids():
    """When CT.gov has no referencesModule entries (linked_pmids=[]), the
    orchestrator must fall back to the regex-over-abstract path and tag the
    resulting publications with the weak-link evidence marker."""
    orch = Orchestrator()
    trial = TrialRecord(
        source="ClinicalTrials.gov",
        source_id="NCT02",
        nct_id="NCT02",
        linked_pmids=[],
    )
    pub = PublicationRecord(pmid="99999", title="paper-from-regex-fallback")

    orch.ct.search_trials = AsyncMock(return_value=[trial])
    orch.pubmed.fetch_publications_by_pmids = AsyncMock(return_value=[])
    orch.pubmed.get_publications_for_trial = AsyncMock(return_value=[pub])

    result = await orch.search_trials_with_publications(disease_query="test")

    orch.pubmed.fetch_publications_by_pmids.assert_not_called()
    orch.pubmed.get_publications_for_trial.assert_called_once_with(
        "NCT02", page_size=5
    )
    assert len(result.publications) == 1
    ev = result.publications[0].evidence_path
    assert "ctgov:NCT02" in ev
    assert "pubmed-search:abstract-regex-NCT" in ev
    assert "pubmed:99999" in ev
    assert "0 via CT.gov referencesModule, 1 via abstract regex fallback" in result.summary


@pytest.mark.asyncio
async def test_orchestrator_caps_linked_pmids_at_five_and_surfaces_truncation():
    """Trials with > 5 linked_pmids must (a) only fetch the first 5 and
    (b) surface the truncation count in the response summary so the LLM can
    see the cap was applied."""
    orch = Orchestrator()
    trial = TrialRecord(
        source="ClinicalTrials.gov",
        source_id="NCT03",
        nct_id="NCT03",
        linked_pmids=["1", "2", "3", "4", "5", "6", "7"],  # 7 pmids, cap is 5
    )
    pubs = [PublicationRecord(pmid=p) for p in ["1", "2", "3", "4", "5"]]

    orch.ct.search_trials = AsyncMock(return_value=[trial])
    orch.pubmed.fetch_publications_by_pmids = AsyncMock(return_value=pubs)
    orch.pubmed.get_publications_for_trial = AsyncMock()

    result = await orch.search_trials_with_publications(disease_query="test")

    orch.pubmed.fetch_publications_by_pmids.assert_called_once_with(
        ["1", "2", "3", "4", "5"]
    )
    assert "2 additional pmids omitted" in result.summary
    assert "capped at 5 per trial" in result.summary


# ---------------------------------------------------------------------------
# Citation layer (features/citations PR #4)
# ---------------------------------------------------------------------------


def test_build_citation_layer():
    layer = build_citation_layer(
        [
            Citation(
                source="PubMed",
                id="12345",
                url="https://pubmed.ncbi.nlm.nih.gov/12345/",
                title="Example paper",
            ),
            Citation(
                source="PubMed",
                id="12345",
                url="https://pubmed.ncbi.nlm.nih.gov/12345/",
                title="Example paper",
            ),
        ]
    )

    assert layer["style"] == "chatgpt_markdown"
    assert layer["display_style"] == "chatgpt_hover_card"
    assert len(layer["references"]) == 1
    assert layer["references"][0]["marker"] == "[1]"
    assert layer["references"][0]["markdown_marker"] == "[[1]](https://pubmed.ncbi.nlm.nih.gov/12345/)"
    assert layer["references"][0]["citation_key"].startswith("cite_")
    assert layer["references"][0]["hover_card"]["title"] == "Example paper"
    assert layer["references"][0]["hover_card"]["source"] == "PubMed"
    assert layer["references"][0]["hover_card"]["display_url"] == "pubmed.ncbi.nlm.nih.gov/12345"
    assert layer["numbering"]["client_should_renumber"] is True
    assert layer["sources_panel"]["style"] == "chatgpt_sources_drawer"
    assert layer["sources_panel"]["button"]["label"] == "Sources"
    assert layer["sources_panel"]["button"]["count"] == 1
    assert layer["sources_panel"]["panel"]["placement"] == "right"
    assert layer["sources_panel"]["panel"]["items"][0]["title"] == "Example paper"
    assert layer["sources_panel"]["panel"]["items"][0]["citation_key"].startswith("cite_")
    assert "html" not in layer
    assert "markdown" not in layer


def test_attach_citation_layer_fails_softly_for_empty_citations():
    payload = {"count": 0, "results": []}
    assert attach_citation_layer(payload, []) == payload


def test_attach_citation_layer_adds_structured_sources_panel_only():
    payload = {"count": 1, "results": []}
    citation = Citation(
        source="PubMed",
        id="12345",
        url="https://pubmed.ncbi.nlm.nih.gov/12345/",
        title="Example paper",
    )

    result = attach_citation_layer(payload, [citation])

    assert "sources_panel" in result
    assert result["sources_panel"]["button"]["count"] == 1
    assert "citations_markdown" not in result
    assert "citations_html" not in result
    assert "sources_panel_html" not in result


def test_citations_from_rows_preserves_citation_objects():
    citation = Citation(source="ClinicalTrials.gov", id="NCT00000000")
    row = TrialRecord(source="ClinicalTrials.gov", source_id="NCT00000000", citations=[citation])

    assert citations_from_rows([row]) == [citation]

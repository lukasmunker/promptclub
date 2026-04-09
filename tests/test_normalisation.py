from app.citations import attach_citation_layer, build_citation_layer, citations_from_rows
from app.models import (
    Citation,
    PublicationRecord,
    RegulatoryRecord,
    TargetAssociationRecord,
    TrialRecord,
)


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
    assert layer["display_style"] == "inline_references_only"
    assert len(layer["references"]) == 1
    assert layer["references"][0]["marker"] == "[1]"
    assert layer["references"][0]["markdown_marker"] == "[[1]](https://pubmed.ncbi.nlm.nih.gov/12345/)"
    assert layer["references"][0]["citation_key"].startswith("cite_")
    assert layer["references"][0]["hover_card"]["title"] == "Example paper"
    assert layer["references"][0]["hover_card"]["source"] == "PubMed"
    assert layer["references"][0]["hover_card"]["display_url"] == "pubmed.ncbi.nlm.nih.gov/12345"
    assert layer["numbering"]["client_should_renumber"] is True
    assert "sources_panel" not in layer
    assert "html" not in layer
    assert "markdown" not in layer


def test_build_citation_layer_uses_response_local_keys():
    layer_a = build_citation_layer(
        [Citation(source="PubMed", id="12345", url="https://pubmed.ncbi.nlm.nih.gov/12345/")]
    )
    layer_b = build_citation_layer(
        [Citation(source="PubMed", id="12345", url="https://pubmed.ncbi.nlm.nih.gov/12345/")]
    )

    assert layer_a["references"][0]["citation_key"].startswith("cite_")
    assert layer_b["references"][0]["citation_key"].startswith("cite_")
    assert layer_a["references"][0]["citation_key"] != layer_b["references"][0]["citation_key"]


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

    assert "citation_layer" in result
    assert "sources_panel" not in result
    assert "citations_markdown" not in result
    assert "citations_html" not in result
    assert "sources_panel_html" not in result


def test_citations_from_rows_preserves_citation_objects():
    citation = Citation(source="ClinicalTrials.gov", id="NCT00000000")
    row = TrialRecord(source="ClinicalTrials.gov", source_id="NCT00000000", citations=[citation])

    assert citations_from_rows([row]) == [citation]

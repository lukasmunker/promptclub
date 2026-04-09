from app.models import (
    ComparisonResponse,
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
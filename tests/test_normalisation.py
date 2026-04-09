from app.models import (
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
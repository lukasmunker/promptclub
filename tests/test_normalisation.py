from app.models import TrialRecord, PublicationRecord, TargetAssociationRecord, RegulatoryRecord


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
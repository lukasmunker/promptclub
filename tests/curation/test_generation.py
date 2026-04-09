"""Light tests for the generation script.

We don't actually call Claude in tests — that requires an API key and
costs money. Instead we test the validation and CSV-writing pieces in
isolation by faking the LLM response.
"""

from pathlib import Path

import pytest
import yaml

from app.knowledge.oncology.schema import LexiconEntry


def test_valid_llm_response_passes_validation():
    fake_response = {
        "id": "phase-3",
        "term": "Phase 3",
        "aliases": ["phase III"],
        "category": "trial-phase",
        "short_definition": "Late-stage clinical trial confirming efficacy and safety in a large population.",
        "clinical_context": "Phase 3 trials enroll hundreds to thousands of patients and are typically required for regulatory approval. They compare the investigational therapy to standard of care.",
        "typical_values": None,
        "related_terms": [],
        "sources": [
            {
                "kind": "nci-thesaurus",
                "url": "https://ncit.nci.nih.gov/ncitbrowser/ConceptReport.jsp?dictionary=NCI_Thesaurus&code=C39568",
                "citation": "NCI Thesaurus, Phase III Trial",
            }
        ],
        "review_status": "llm-generated",
        "last_reviewed": None,
    }
    entry = LexiconEntry(**fake_response)
    assert entry.id == "phase-3"


def test_response_with_fake_url_fails_validation():
    """The hard quality gate: fabricated URLs must fail validation."""
    fake_response = {
        "id": "x",
        "term": "X",
        "aliases": [],
        "category": "trial-phase",
        "short_definition": "test definition that is long enough",
        "clinical_context": "test context that is also long enough",
        "sources": [
            {
                "kind": "nci-thesaurus",
                "url": "https://my-fake-blog.example.com/x",
                "citation": "Fake source",
            }
        ],
        "review_status": "llm-generated",
    }
    with pytest.raises(Exception, match="not in the authoritative source allowlist"):
        LexiconEntry(**fake_response)


def test_response_without_sources_fails_validation():
    fake_response = {
        "id": "x",
        "term": "X",
        "aliases": [],
        "category": "trial-phase",
        "short_definition": "test definition that is long enough",
        "clinical_context": "test context that is also long enough",
        "sources": [],
        "review_status": "llm-generated",
    }
    with pytest.raises(Exception, match="at least 1"):
        LexiconEntry(**fake_response)

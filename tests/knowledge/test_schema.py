"""Schema tests — the hard quality gates for the lexicon."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.knowledge.oncology.schema import LexiconEntry, Source


# --- Source --------------------------------------------------------------------


def test_source_accepts_authoritative_url():
    s = Source(
        kind="nci-thesaurus",
        url="https://ncit.nci.nih.gov/ncitbrowser/ConceptReport.jsp?dictionary=NCI_Thesaurus&code=C39568",
        citation="NCI Thesaurus, Phase III Trial",
    )
    assert s.kind == "nci-thesaurus"


def test_source_rejects_non_allowlisted_url():
    with pytest.raises(ValidationError, match="not in the authoritative source allowlist"):
        Source(
            kind="nci-thesaurus",
            url="https://random-blog.example.com/recist",
            citation="Random blog",
        )


def test_source_allows_url_none_if_citation_is_textual():
    s = Source(
        kind="publication",
        url=None,
        citation="Eisenhauer et al., Eur J Cancer 2009 (RECIST 1.1)",
    )
    assert s.url is None


# --- LexiconEntry --------------------------------------------------------------


def _valid_source() -> Source:
    return Source(
        kind="nci-thesaurus",
        url="https://ncit.nci.nih.gov/ncitbrowser/ConceptReport.jsp?dictionary=NCI_Thesaurus&code=C39568",
        citation="NCI Thesaurus",
    )


def test_lexicon_entry_minimal():
    entry = LexiconEntry(
        id="trial-phase-3",
        term="Phase 3",
        aliases=["phase III", "phase iii"],
        category="trial-phase",
        short_definition="Late-stage clinical trial confirming efficacy and safety in a large population.",
        clinical_context="Phase 3 trials enroll hundreds to thousands of patients and are typically required for regulatory approval.",
        sources=[_valid_source()],
        review_status="llm-generated",
    )
    assert entry.id == "trial-phase-3"


def test_lexicon_entry_requires_at_least_one_source():
    with pytest.raises(ValidationError, match="at least 1 source"):
        LexiconEntry(
            id="trial-phase-3",
            term="Phase 3",
            aliases=[],
            category="trial-phase",
            short_definition="x",
            clinical_context="x",
            sources=[],
            review_status="llm-generated",
        )


def test_lexicon_entry_rejects_unknown_category():
    with pytest.raises(ValidationError):
        LexiconEntry(
            id="x",
            term="X",
            aliases=[],
            category="not-a-real-category",  # type: ignore[arg-type]
            short_definition="x",
            clinical_context="x",
            sources=[_valid_source()],
            review_status="llm-generated",
        )


def test_review_status_lifecycle():
    for status in ("llm-generated", "reviewed", "expert-approved"):
        entry = LexiconEntry(
            id="t",
            term="T",
            aliases=[],
            category="trial-phase",
            short_definition="x",
            clinical_context="x",
            sources=[_valid_source()],
            review_status=status,  # type: ignore[arg-type]
        )
        assert entry.review_status == status


def test_last_reviewed_optional():
    entry = LexiconEntry(
        id="t",
        term="T",
        aliases=[],
        category="trial-phase",
        short_definition="x",
        clinical_context="x",
        sources=[_valid_source()],
        review_status="reviewed",
        last_reviewed=date(2026, 4, 9),
    )
    assert entry.last_reviewed == date(2026, 4, 9)

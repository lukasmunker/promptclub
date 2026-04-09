"""Enrichment logic tests."""

import time

import pytest

from app.knowledge.oncology.loader import _build_lexicon, load_lexicon
from app.knowledge.oncology.schema import Lexicon, LexiconEntry, Source
from app.services.enrichment import enrich, MAX_ANNOTATIONS


def _entry(eid: str, term: str, aliases: list[str] | None = None) -> LexiconEntry:
    return LexiconEntry(
        id=eid,
        term=term,
        aliases=aliases or [],
        category="trial-phase",
        short_definition="Test definition that is long enough.",
        clinical_context="Test context that is also long enough.",
        sources=[Source(
            kind="nci-thesaurus",
            url="https://ncit.nci.nih.gov/x",
            citation="NCIt",
        )],
        review_status="llm-generated",
    )


@pytest.fixture
def mini_lexicon():
    entries = [
        _entry("trial-phase-3", "Phase 3", aliases=["phase III", "phase iii"]),
        _entry("endpoint-os", "Overall Survival", aliases=["OS"]),
        _entry("response-criterion-recist-1-1", "RECIST 1.1", aliases=["RECIST"]),
    ]
    return _build_lexicon(entries)


@pytest.fixture
def substring_lexicon():
    """Fixture for testing longest-match-wins: two terms where one
    is a substring of the other ('active, not recruiting' vs
    'recruiting'). The two have opposite semantic meanings."""
    entries = [
        _entry(
            "trial-status-active-not-recruiting",
            "Active, not recruiting",
        ),
        _entry("trial-status-recruiting", "Recruiting"),
    ]
    return _build_lexicon(entries)


# --- Match rules ----------------------------------------------------------------


def test_enrich_matches_canonical_term(mini_lexicon):
    data = {"phase": "Phase 3"}
    result = enrich(data, mini_lexicon)
    annotations = result["knowledge_annotations"]
    assert any(a["lexicon_id"] == "trial-phase-3" for a in annotations)


def test_enrich_matches_alias(mini_lexicon):
    data = {"endpoint": "OS"}
    result = enrich(data, mini_lexicon)
    annotations = result["knowledge_annotations"]
    assert any(a["matched_term"] == "OS" and a["lexicon_id"] == "endpoint-os"
               for a in annotations)


def test_enrich_is_case_insensitive(mini_lexicon):
    data = {"phase": "phase iii"}
    result = enrich(data, mini_lexicon)
    annotations = result["knowledge_annotations"]
    assert any(a["lexicon_id"] == "trial-phase-3" for a in annotations)


def test_enrich_word_boundary(mini_lexicon):
    """RECIST should NOT match in 'prerecisted' or similar substrings."""
    data = {"notes": "the prerecisted criteria were updated"}
    result = enrich(data, mini_lexicon)
    annotations = result["knowledge_annotations"]
    assert not any(a["lexicon_id"].startswith("response-criterion") for a in annotations)


def test_enrich_walks_nested_dicts(mini_lexicon):
    data = {"trial": {"details": {"phase": "Phase 3"}}}
    result = enrich(data, mini_lexicon)
    assert any(a["lexicon_id"] == "trial-phase-3"
               for a in result["knowledge_annotations"])


def test_enrich_walks_lists_of_dicts(mini_lexicon):
    data = {"results": [{"phase": "Phase 3"}, {"phase": "Phase 2"}]}
    result = enrich(data, mini_lexicon)
    annotations = result["knowledge_annotations"]
    assert any(a["lexicon_id"] == "trial-phase-3" for a in annotations)


# --- Idempotence and capping ---------------------------------------------------


def test_enrich_dedupes_same_lexicon_id(mini_lexicon):
    """If 'Phase 3' appears 5 times in the data, we should still get one
    annotation per unique field path — but not five identical ones for
    the same lexicon_id at the same field path."""
    data = {
        "trials": [
            {"phase": "Phase 3", "id": "NCT01"},
            {"phase": "Phase 3", "id": "NCT02"},
        ]
    }
    result = enrich(data, mini_lexicon)
    annotations = result["knowledge_annotations"]
    # Should annotate each occurrence (different field paths)
    phase3_annotations = [a for a in annotations if a["lexicon_id"] == "trial-phase-3"]
    assert len(phase3_annotations) >= 1


def test_enrich_idempotent(mini_lexicon):
    data = {"phase": "Phase 3"}
    once = enrich(data, mini_lexicon)
    twice = enrich(once, mini_lexicon)
    assert once["knowledge_annotations"] == twice["knowledge_annotations"]


def test_enrich_caps_max_annotations(mini_lexicon):
    """A response with 100 occurrences must not produce 100 annotations."""
    data = {"trials": [{"phase": "Phase 3"} for _ in range(100)]}
    result = enrich(data, mini_lexicon)
    assert len(result["knowledge_annotations"]) <= MAX_ANNOTATIONS


# --- Side effects ---------------------------------------------------------------


def test_enrich_does_not_mutate_original(mini_lexicon):
    data = {"phase": "Phase 3"}
    original_copy = dict(data)
    _ = enrich(data, mini_lexicon)
    assert data == original_copy
    assert "knowledge_annotations" not in data


def test_enrich_with_empty_data(mini_lexicon):
    result = enrich({}, mini_lexicon)
    assert result == {"knowledge_annotations": []}


def test_enrich_with_no_matches(mini_lexicon):
    data = {"unrelated": "field with no oncology terms"}
    result = enrich(data, mini_lexicon)
    assert result["knowledge_annotations"] == []


# --- Longest-match-wins (substring overlap) -----------------------------------


def test_enrich_prefers_longer_match(substring_lexicon):
    """When the text contains 'Active, not recruiting', only the
    longer term should match — NOT also the shorter 'Recruiting'
    which is the opposite meaning."""
    data = {"status": "Active, not recruiting"}
    result = enrich(data, substring_lexicon)
    annotations = result["knowledge_annotations"]

    ids = [a["lexicon_id"] for a in annotations]
    assert "trial-status-active-not-recruiting" in ids
    assert "trial-status-recruiting" not in ids, (
        "Shorter substring 'Recruiting' was annotated, but 'Active, "
        "not recruiting' is the exact opposite meaning. Longest-match-"
        "wins must be enforced."
    )


def test_enrich_still_matches_shorter_when_longer_absent(substring_lexicon):
    """Sanity check: the shorter term still matches when the longer
    one is not present in the text."""
    data = {"status": "Recruiting"}
    result = enrich(data, substring_lexicon)
    ids = [a["lexicon_id"] for a in result["knowledge_annotations"]]
    assert "trial-status-recruiting" in ids
    assert "trial-status-active-not-recruiting" not in ids


# --- Performance budget -------------------------------------------------------


def test_enrich_performance_budget():
    """Regression guard: enrichment must stay under 100ms per call
    even for a realistic 20-trial response. The pre-fix code was
    ~700ms — a combined regex brings it to ~1ms."""
    lex = load_lexicon()  # real 160-entry lexicon

    # Simulate a realistic search_trials response
    data = {
        "results": [
            {
                "id": f"NCT{i:08d}",
                "title": f"A Phase 3 study of Pembrolizumab in NSCLC (cohort {i})",
                "sponsor": "Merck",
                "phase": "Phase 3",
                "status": "Recruiting",
                "primary_endpoint": "Overall Survival",
                "secondary_endpoints": [
                    "Progression-Free Survival",
                    "Objective Response Rate",
                ],
                "biomarker": "PD-L1 expression",
                "notes": "First-line therapy for advanced NSCLC",
            }
            for i in range(20)
        ]
    }

    start = time.perf_counter()
    result = enrich(data, lex)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.1, (
        f"enrich() took {elapsed*1000:.1f}ms — budget is 100ms. "
        f"The combined-regex refactor may have regressed, or the "
        f"lexicon has grown beyond what this budget assumes."
    )
    assert len(result["knowledge_annotations"]) > 0

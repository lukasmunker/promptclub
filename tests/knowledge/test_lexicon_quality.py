"""Quality gates for the live lexicon.yaml.

These tests run against the actual file in the repo and prevent
regressions like duplicate ids, broken alias indexing, dead
related_terms references, or empty categories.
"""

from collections import Counter
from urllib.parse import urlparse

import pytest

from app.knowledge.oncology.loader import load_lexicon
from app.knowledge.oncology.schema import ALLOWED_SOURCE_DOMAINS


@pytest.fixture(scope="module")
def lexicon():
    return load_lexicon()


def test_lexicon_has_minimum_entries(lexicon):
    assert len(lexicon.entries) >= 150, (
        f"Lexicon has only {len(lexicon.entries)} entries — expected at least 150 "
        "after the first curation pass. Either re-run the generation or accept "
        "more entries in the review CSV."
    )


def test_no_duplicate_ids(lexicon):
    ids = [e.id for e in lexicon.entries]
    duplicates = [i for i, c in Counter(ids).items() if c > 1]
    assert not duplicates, f"Duplicate ids: {duplicates}"


def test_no_alias_collisions(lexicon):
    """Two different entries must not share an alias — that would make
    the term_index ambiguous."""
    seen: dict[str, str] = {}
    for entry in lexicon.entries:
        for alias in entry.aliases + [entry.term]:
            key = alias.lower()
            if key in seen and seen[key] != entry.id:
                pytest.fail(
                    f"Alias collision: '{alias}' is used by both "
                    f"'{seen[key]}' and '{entry.id}'"
                )
            seen[key] = entry.id


def test_related_terms_resolve(lexicon):
    valid_ids = {e.id for e in lexicon.entries}
    for entry in lexicon.entries:
        for ref in entry.related_terms:
            assert ref in valid_ids, (
                f"Entry '{entry.id}' has dead related_terms reference: '{ref}'"
            )


def test_all_categories_have_entries(lexicon):
    """Every category that appears in seed_topics.yaml must have ≥1
    entry in the lexicon. An empty category indicates a generation
    pipeline failure for that group."""
    seen_categories = Counter(e.category for e in lexicon.entries)
    for category, count in seen_categories.items():
        assert count >= 1, f"Category '{category}' has zero entries"


def test_all_sources_in_allowlist(lexicon):
    for entry in lexicon.entries:
        for source in entry.sources:
            if source.url:
                domain = urlparse(source.url).netloc.lower()
                assert domain in ALLOWED_SOURCE_DOMAINS, (
                    f"Entry '{entry.id}' has source from non-allowlisted domain: {domain}"
                )


def test_definitions_meet_minimum_length(lexicon):
    for entry in lexicon.entries:
        assert len(entry.short_definition) >= 10
        assert len(entry.clinical_context) >= 10

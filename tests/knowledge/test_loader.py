"""Loader tests — verify YAML parsing and index construction."""

from pathlib import Path

import pytest
import yaml

from app.knowledge.oncology.loader import load_lexicon


def _write_yaml(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "lexicon.yaml"
    p.write_text(yaml.safe_dump(payload, sort_keys=False))
    return p


def _valid_entry(eid: str, term: str, aliases: list[str] | None = None) -> dict:
    return {
        "id": eid,
        "term": term,
        "aliases": aliases or [],
        "category": "trial-phase",
        "short_definition": "Test definition that is long enough.",
        "clinical_context": "Test context that is also long enough.",
        "sources": [
            {
                "kind": "nci-thesaurus",
                "url": "https://ncit.nci.nih.gov/ncitbrowser/x",
                "citation": "NCI Thesaurus",
            }
        ],
        "review_status": "llm-generated",
    }


def test_load_lexicon_empty(tmp_path):
    p = _write_yaml(tmp_path, {"entries": []})
    lex = load_lexicon(p)
    assert lex.entries == []
    assert lex.term_index == {}


def test_load_lexicon_single_entry(tmp_path):
    p = _write_yaml(tmp_path, {"entries": [_valid_entry("phase-3", "Phase 3")]})
    lex = load_lexicon(p)
    assert len(lex.entries) == 1
    assert "phase 3" in lex.term_index  # case-insensitive lookup


def test_load_lexicon_indexes_aliases(tmp_path):
    entry = _valid_entry("os", "Overall Survival", aliases=["OS", "overall-survival"])
    p = _write_yaml(tmp_path, {"entries": [entry]})
    lex = load_lexicon(p)
    assert "overall survival" in lex.term_index
    assert "os" in lex.term_index
    assert "overall-survival" in lex.term_index


def test_load_lexicon_rejects_invalid_yaml(tmp_path):
    p = _write_yaml(tmp_path, {"entries": [{"id": "x", "term": "X"}]})  # missing required fields
    with pytest.raises(Exception):  # pydantic ValidationError
        load_lexicon(p)


def test_load_lexicon_default_path():
    """Calling load_lexicon() without args reads the canonical
    app/knowledge/oncology/lexicon.yaml. The file may be empty in the
    repo today — that's fine, this test only verifies the call works."""
    lex = load_lexicon()
    # Don't assert content — just that the call succeeds
    assert lex is not None

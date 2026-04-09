"""Tests for the review worksheet → YAML merge script."""

import csv
from datetime import date
from pathlib import Path

import pytest
import yaml

from scripts.curation.review_worksheet_to_yaml import merge_worksheet


def _write_draft(tmp_path: Path) -> Path:
    """Write a 3-entry draft YAML."""
    p = tmp_path / "draft.yaml"
    p.write_text(yaml.safe_dump({
        "entries": [
            {
                "id": "phase-3",
                "term": "Phase 3",
                "aliases": ["phase III"],
                "category": "trial-phase",
                "short_definition": "Late-stage trial confirming efficacy.",
                "clinical_context": "Phase 3 trials enroll hundreds to thousands of patients.",
                "sources": [{"kind": "nci-thesaurus", "url": "https://ncit.nci.nih.gov/x", "citation": "NCIt"}],
                "review_status": "llm-generated",
                "related_terms": [],
                "typical_values": None,
                "last_reviewed": None,
            },
            {
                "id": "phase-2",
                "term": "Phase 2",
                "aliases": [],
                "category": "trial-phase",
                "short_definition": "Mid-stage trial assessing efficacy and dose.",
                "clinical_context": "Phase 2 trials test efficacy in a smaller population.",
                "sources": [{"kind": "nci-thesaurus", "url": "https://ncit.nci.nih.gov/y", "citation": "NCIt"}],
                "review_status": "llm-generated",
                "related_terms": [],
                "typical_values": None,
                "last_reviewed": None,
            },
            {
                "id": "phase-1",
                "term": "Phase 1",
                "aliases": [],
                "category": "trial-phase",
                "short_definition": "Early-stage safety study.",
                "clinical_context": "Phase 1 trials test safety and dose-finding.",
                "sources": [{"kind": "nci-thesaurus", "url": "https://ncit.nci.nih.gov/z", "citation": "NCIt"}],
                "review_status": "llm-generated",
                "related_terms": [],
                "typical_values": None,
                "last_reviewed": None,
            },
        ]
    }))
    return p


def _write_csv(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    p = tmp_path / "review.csv"
    with p.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "id", "term", "category", "short_definition", "clinical_context",
            "source_count", "sources_summary", "review_status",
            "reviewer_notes", "accept", "edit", "reject",
        ])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return p


def test_merge_drops_rejected(tmp_path):
    draft = _write_draft(tmp_path)
    csv_path = _write_csv(tmp_path, [
        {"id": "phase-3", "term": "Phase 3", "category": "trial-phase",
         "short_definition": "", "clinical_context": "",
         "source_count": "1", "sources_summary": "NCIt", "review_status": "llm-generated",
         "reviewer_notes": "", "accept": "1", "edit": "", "reject": ""},
        {"id": "phase-2", "term": "Phase 2", "category": "trial-phase",
         "short_definition": "", "clinical_context": "",
         "source_count": "1", "sources_summary": "NCIt", "review_status": "llm-generated",
         "reviewer_notes": "", "accept": "", "edit": "", "reject": "1"},
        {"id": "phase-1", "term": "Phase 1", "category": "trial-phase",
         "short_definition": "", "clinical_context": "",
         "source_count": "1", "sources_summary": "NCIt", "review_status": "llm-generated",
         "reviewer_notes": "", "accept": "1", "edit": "", "reject": ""},
    ])
    out = tmp_path / "lexicon.yaml"
    out.write_text("entries: []\n")
    merged_count = merge_worksheet(csv_path=csv_path, draft_path=draft, lexicon_path=out)
    assert merged_count == 2
    final = yaml.safe_load(out.read_text())
    ids = [e["id"] for e in final["entries"]]
    assert "phase-3" in ids
    assert "phase-1" in ids
    assert "phase-2" not in ids


def test_merge_sets_review_status_and_date(tmp_path):
    draft = _write_draft(tmp_path)
    csv_path = _write_csv(tmp_path, [
        {"id": "phase-3", "term": "Phase 3", "category": "trial-phase",
         "short_definition": "", "clinical_context": "",
         "source_count": "1", "sources_summary": "NCIt", "review_status": "llm-generated",
         "reviewer_notes": "", "accept": "1", "edit": "", "reject": ""},
    ])
    out = tmp_path / "lexicon.yaml"
    out.write_text("entries: []\n")
    merge_worksheet(csv_path=csv_path, draft_path=draft, lexicon_path=out)
    final = yaml.safe_load(out.read_text())
    assert final["entries"][0]["review_status"] == "reviewed"
    assert final["entries"][0]["last_reviewed"] == date.today().isoformat()


def test_merge_applies_inline_edit(tmp_path):
    draft = _write_draft(tmp_path)
    csv_path = _write_csv(tmp_path, [
        {"id": "phase-3", "term": "Phase 3", "category": "trial-phase",
         "short_definition": "EDITED short definition that is long enough.",
         "clinical_context": "EDITED clinical context that is also long enough.",
         "source_count": "1", "sources_summary": "NCIt", "review_status": "llm-generated",
         "reviewer_notes": "fix per spot check", "accept": "1", "edit": "1", "reject": ""},
    ])
    out = tmp_path / "lexicon.yaml"
    out.write_text("entries: []\n")
    merge_worksheet(csv_path=csv_path, draft_path=draft, lexicon_path=out)
    final = yaml.safe_load(out.read_text())
    assert final["entries"][0]["short_definition"].startswith("EDITED")
    assert final["entries"][0]["clinical_context"].startswith("EDITED")

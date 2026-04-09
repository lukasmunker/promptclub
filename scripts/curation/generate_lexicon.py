"""Offline script: generate draft lexicon entries from seed_topics.yaml.

Reads the seed topics, asks Claude (via the anthropic SDK) to draft a
LexiconEntry for each term, validates against the Pydantic schema, and
writes:

  - scripts/curation/output/draft_<date>.yaml  : raw drafts
  - scripts/curation/output/review_worksheet_<date>.csv : review sheet

Usage:
    ANTHROPIC_API_KEY=sk-... python scripts/curation/generate_lexicon.py

To generate only a subset:
    python scripts/curation/generate_lexicon.py --category endpoint
    python scripts/curation/generate_lexicon.py --terms "Phase 3,RECIST 1.1"
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from anthropic import Anthropic
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from app.knowledge.oncology.schema import LexiconEntry  # noqa: E402

SEED_PATH = REPO_ROOT / "app" / "knowledge" / "oncology" / "seed_topics.yaml"
OUTPUT_DIR = REPO_ROOT / "scripts" / "curation" / "output"


SYSTEM_PROMPT = """You are a clinical oncology terminology curator. Your job is to draft a single LexiconEntry for each term you are given.

HARD REQUIREMENTS:

1. Every entry MUST cite at least one source. Source URLs must come from one of these authoritative domains:
   - ncit.nci.nih.gov
   - fda.gov / www.fda.gov
   - ema.europa.eu / www.ema.europa.eu
   - recist.eortc.org
   - pubmed.ncbi.nlm.nih.gov
   - ctep.cancer.gov

2. If you cannot cite a real, authoritative source for an entry, return null and we will skip the term. Do not fabricate URLs.

3. short_definition must be 1-2 sentences, plain language, quotable from the source.

4. clinical_context must be 2-4 sentences, grounded in the source, no speculation. If you are uncertain about something, leave it out rather than guess.

5. Do NOT include forward-looking statements ("expected to..." / "may improve...").

OUTPUT FORMAT: Return a single JSON object that exactly matches this schema:

{
  "id": "kebab-case-slug",
  "term": "Canonical Term",
  "aliases": ["alias1", "alias2"],
  "category": "one of: trial-phase, trial-status, endpoint, study-design, tumor-type, biomarker, drug-class, response-criterion, treatment-line, resistance-mechanism",
  "short_definition": "1-2 sentences",
  "clinical_context": "2-4 sentences",
  "typical_values": null,
  "related_terms": ["other-id"],
  "sources": [
    {"kind": "nci-thesaurus", "url": "https://ncit.nci.nih.gov/...", "citation": "NCI Thesaurus, Concept X"}
  ],
  "review_status": "llm-generated",
  "last_reviewed": null
}

Or `null` if you cannot find an authoritative source.
"""


def _build_user_prompt(term: str, category: str) -> str:
    return f"""Draft a LexiconEntry for the term "{term}" in category "{category}".

Return one JSON object as specified in the system prompt, or null if you cannot cite an authoritative source. No prose, no markdown, JSON only."""


def _call_claude(client: Anthropic, term: str, category: str) -> dict[str, Any] | None:
    """Call Claude once and parse the JSON response."""
    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_prompt(term, category)}],
    )
    text = msg.content[0].text.strip()
    if text == "null" or text.startswith("null"):
        return None
    # Strip markdown code fences if Claude added them
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]
    return json.loads(text.strip())


def _validate(entry_dict: dict[str, Any]) -> LexiconEntry | None:
    """Validate against Pydantic schema. Return None on failure (logged)."""
    try:
        return LexiconEntry(**entry_dict)
    except ValidationError as e:
        print(f"  ✗ validation failed: {e.errors()[0]['msg']}", file=sys.stderr)
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", help="Generate only this category")
    parser.add_argument("--terms", help="Comma-separated list of terms (overrides --category)")
    args = parser.parse_args()

    if "ANTHROPIC_API_KEY" not in os.environ:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
        return 1

    client = Anthropic()
    seed = yaml.safe_load(SEED_PATH.read_text())

    targets: list[tuple[str, str]] = []  # (category, term)
    if args.terms:
        wanted = {t.strip() for t in args.terms.split(",")}
        for cat, terms in seed.items():
            for t in terms:
                if t in wanted:
                    targets.append((cat, t))
    elif args.category:
        for t in seed.get(args.category, []):
            targets.append((args.category, t))
    else:
        for cat, terms in seed.items():
            for t in terms:
                targets.append((cat, t))

    print(f"Generating {len(targets)} entries...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    draft_path = OUTPUT_DIR / f"draft_{today}.yaml"
    csv_path = OUTPUT_DIR / f"review_worksheet_{today}.csv"

    valid_entries: list[LexiconEntry] = []
    for cat, term in targets:
        print(f"[{cat}] {term}", file=sys.stderr)
        try:
            raw = _call_claude(client, term, cat)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ API error: {e}", file=sys.stderr)
            continue
        if raw is None:
            print(f"  ⊘ skipped (no authoritative source)", file=sys.stderr)
            continue
        entry = _validate(raw)
        if entry is not None:
            valid_entries.append(entry)
            print(f"  ✓", file=sys.stderr)

    # Write draft YAML
    draft_path.write_text(
        yaml.safe_dump(
            {"entries": [e.model_dump(mode="json") for e in valid_entries]},
            sort_keys=False,
            allow_unicode=True,
        )
    )

    # Write review CSV
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id", "term", "category", "short_definition", "clinical_context",
            "source_count", "sources_summary", "review_status",
            "reviewer_notes", "accept", "edit", "reject",
        ])
        for e in valid_entries:
            writer.writerow([
                e.id, e.term, e.category,
                e.short_definition, e.clinical_context,
                len(e.sources),
                "; ".join(s.citation for s in e.sources),
                e.review_status,
                "", "", "", "",
            ])

    print(f"\nDone: {len(valid_entries)} valid entries written to:")
    print(f"  {draft_path.relative_to(REPO_ROOT)}")
    print(f"  {csv_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

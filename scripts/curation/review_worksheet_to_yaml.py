"""Merge a reviewed CSV worksheet into the canonical lexicon.yaml.

Workflow:
  1. Loads the LLM-generated draft YAML
  2. Loads the human-reviewed CSV (accept / edit / reject columns)
  3. Drops rejected entries
  4. Applies inline edits from the CSV
  5. Sets review_status="reviewed" and last_reviewed=today for accepted
  6. Validates the result against the Pydantic schema
  7. Merges into the existing lexicon.yaml (overwriting same-id entries)
  8. Writes the final lexicon.yaml

Usage:
    python scripts/curation/review_worksheet_to_yaml.py \
        scripts/curation/output/review_worksheet_<date>.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from app.knowledge.oncology.schema import LexiconEntry  # noqa: E402

DEFAULT_LEXICON = REPO_ROOT / "app" / "knowledge" / "oncology" / "lexicon.yaml"


def _is_truthy(s: str | None) -> bool:
    return (s or "").strip().lower() in ("1", "true", "yes", "y")


def merge_worksheet(
    csv_path: Path,
    draft_path: Path,
    lexicon_path: Path = DEFAULT_LEXICON,
) -> int:
    """Merge a reviewed CSV into the lexicon. Returns # of merged entries."""
    draft_raw = yaml.safe_load(draft_path.read_text()) or {"entries": []}
    draft_index: dict[str, dict[str, Any]] = {
        e["id"]: e for e in draft_raw.get("entries", [])
    }

    accepted: list[dict[str, Any]] = []
    today_iso = date.today().isoformat()

    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if _is_truthy(row.get("reject")):
                continue
            if not _is_truthy(row.get("accept")):
                continue

            entry_id = row["id"]
            if entry_id not in draft_index:
                print(f"  ⊘ {entry_id}: not in draft, skipping", file=sys.stderr)
                continue

            entry = dict(draft_index[entry_id])  # copy
            if _is_truthy(row.get("edit")):
                if row.get("short_definition"):
                    entry["short_definition"] = row["short_definition"]
                if row.get("clinical_context"):
                    entry["clinical_context"] = row["clinical_context"]
            entry["review_status"] = "reviewed"
            entry["last_reviewed"] = today_iso
            accepted.append(entry)

    # Validate every accepted entry against the schema
    validated: list[dict[str, Any]] = []
    for entry in accepted:
        try:
            obj = LexiconEntry(**entry)
            validated.append(obj.model_dump(mode="json"))
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {entry.get('id')}: validation failed: {e}", file=sys.stderr)

    # Merge into existing lexicon (overwrite same id)
    existing_raw = yaml.safe_load(lexicon_path.read_text()) or {"entries": []}
    existing_by_id: dict[str, dict[str, Any]] = {
        e["id"]: e for e in existing_raw.get("entries", [])
    }
    for v in validated:
        existing_by_id[v["id"]] = v

    final_entries = sorted(existing_by_id.values(), key=lambda e: (e["category"], e["id"]))
    lexicon_path.write_text(
        yaml.safe_dump(
            {"entries": final_entries},
            sort_keys=False,
            allow_unicode=True,
        )
    )
    return len(validated)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path, help="Path to reviewed CSV")
    parser.add_argument(
        "--draft",
        type=Path,
        help="Path to draft YAML (defaults to same dir, draft_<csv-date>.yaml)",
    )
    parser.add_argument("--lexicon", type=Path, default=DEFAULT_LEXICON)
    args = parser.parse_args()

    if args.draft is None:
        # Infer draft path from CSV filename: review_worksheet_<date>.csv → draft_<date>.yaml
        stem = args.csv.stem
        if stem.startswith("review_worksheet_"):
            date_part = stem[len("review_worksheet_"):]
            args.draft = args.csv.parent / f"draft_{date_part}.yaml"
        else:
            print("ERROR: cannot infer --draft from CSV name", file=sys.stderr)
            return 1

    n = merge_worksheet(args.csv, args.draft, args.lexicon)
    print(f"Merged {n} entries into {args.lexicon.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

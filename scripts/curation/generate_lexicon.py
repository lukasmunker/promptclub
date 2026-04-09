"""Aggregation library for the oncology lexicon curation pipeline.

This module validates pre-generated lexicon entries and writes the draft
YAML + review worksheet CSV. It does NOT call any LLM — generation is
done by the ambient Claude Code session dispatching parallel subagents,
each responsible for one category in ``seed_topics.yaml``.

Workflow:

1. Subagents are dispatched (one per category) with strict instructions
   to return JSON entries matching ``LexiconEntry``. Each subagent
   writes its output to ``scripts/curation/output/agent_<category>.json``.
2. The aggregation driver (``aggregate_from_agent_outputs``) reads all
   agent JSON files, validates every entry against the Pydantic schema,
   and writes:

   - ``scripts/curation/output/draft_<date>.yaml``  (valid entries only)
   - ``scripts/curation/output/review_worksheet_<date>.csv`` (review sheet)

3. The human curator reviews the CSV, marks accept / edit / reject, and
   runs ``review_worksheet_to_yaml.py`` to merge accepted entries into
   ``app/knowledge/oncology/lexicon.yaml``.

Usage (CLI — aggregation step only):

    python scripts/curation/generate_lexicon.py \\
        --agent-output-dir scripts/curation/output

The CLI reads every ``agent_<category>.json`` in the output directory,
validates them, and writes the aggregated draft YAML + CSV. The actual
generation (subagent dispatch) happens upstream — typically from an
interactive Claude Code session.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from app.knowledge.oncology.schema import LexiconEntry  # noqa: E402

SEED_PATH = REPO_ROOT / "app" / "knowledge" / "oncology" / "seed_topics.yaml"
OUTPUT_DIR = REPO_ROOT / "scripts" / "curation" / "output"


def validate_entries(
    raw_entries: list[dict[str, Any]],
) -> tuple[list[LexiconEntry], list[tuple[dict[str, Any], str]]]:
    """Validate a list of raw entry dicts against the Pydantic schema.

    Returns a tuple ``(valid, rejected)`` where ``rejected`` is a list
    of ``(raw_dict, error_message)`` pairs for schema-invalid entries.
    """
    valid: list[LexiconEntry] = []
    rejected: list[tuple[dict[str, Any], str]] = []
    for raw in raw_entries:
        try:
            entry = LexiconEntry(**raw)
            valid.append(entry)
        except ValidationError as e:
            msg = e.errors()[0].get("msg", str(e))
            rejected.append((raw, msg))
    return valid, rejected


def write_draft_yaml(entries: list[LexiconEntry], out_path: Path) -> None:
    """Write validated entries to a draft YAML file."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        yaml.safe_dump(
            {"entries": [e.model_dump(mode="json") for e in entries]},
            sort_keys=False,
            allow_unicode=True,
        )
    )


def write_review_csv(entries: list[LexiconEntry], out_path: Path) -> None:
    """Write a review worksheet CSV for human curation."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id", "term", "category", "short_definition", "clinical_context",
            "source_count", "sources_summary", "review_status",
            "reviewer_notes", "accept", "edit", "reject",
        ])
        for e in entries:
            writer.writerow([
                e.id, e.term, e.category,
                e.short_definition, e.clinical_context,
                len(e.sources),
                "; ".join(s.citation for s in e.sources),
                e.review_status,
                "", "", "", "",
            ])


def aggregate_from_agent_outputs(
    agent_output_dir: Path,
    today: str | None = None,
) -> tuple[Path, Path, int, int]:
    """Read all ``agent_<category>.json`` files, validate, write outputs.

    Returns ``(draft_yaml_path, csv_path, valid_count, rejected_count)``.
    """
    today = today or date.today().isoformat()
    draft_path = OUTPUT_DIR / f"draft_{today}.yaml"
    csv_path = OUTPUT_DIR / f"review_worksheet_{today}.csv"

    all_raw: list[dict[str, Any]] = []
    for agent_file in sorted(agent_output_dir.glob("agent_*.json")):
        raw = json.loads(agent_file.read_text())
        if not isinstance(raw, list):
            raise ValueError(
                f"Agent output {agent_file.name} is not a JSON list"
            )
        all_raw.extend(raw)

    valid, rejected = validate_entries(all_raw)

    write_draft_yaml(valid, draft_path)
    write_review_csv(valid, csv_path)

    if rejected:
        print(f"\n⚠  {len(rejected)} entries failed schema validation:", file=sys.stderr)
        for raw, msg in rejected[:10]:
            print(f"  - {raw.get('id', '?')}: {msg}", file=sys.stderr)
        if len(rejected) > 10:
            print(f"  (+{len(rejected) - 10} more)", file=sys.stderr)

    return draft_path, csv_path, len(valid), len(rejected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--agent-output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory containing agent_<category>.json files",
    )
    args = parser.parse_args()

    if not args.agent_output_dir.exists():
        print(
            f"ERROR: agent output directory does not exist: {args.agent_output_dir}",
            file=sys.stderr,
        )
        return 1

    draft_path, csv_path, n_valid, n_rejected = aggregate_from_agent_outputs(
        args.agent_output_dir
    )

    print(f"\nDone: {n_valid} valid entries written ({n_rejected} rejected).")
    print(f"  {draft_path.relative_to(REPO_ROOT)}")
    print(f"  {csv_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

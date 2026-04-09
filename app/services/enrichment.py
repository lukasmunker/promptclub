"""Knowledge enrichment for tool response dicts.

Walks a tool response dict, finds string fields that match lexicon
terms (canonical or alias), and returns a NEW dict with a top-level
``knowledge_annotations`` field listing every match.

Match rules:
  1. Case-insensitive
  2. Word-boundary (so 'RECIST' does not match in 'prerecisted')
  3. No fuzzy matching — deliberately simple, deterministic
  4. Capped at MAX_ANNOTATIONS per response to prevent noise

Side effects: NONE. The input dict is not mutated. The output is a
new dict with the same keys plus ``knowledge_annotations``.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from app.knowledge.oncology.schema import Annotation, Lexicon

__all__ = ["enrich", "MAX_ANNOTATIONS"]

# Cap on annotations per response. Above this, additional matches are
# silently dropped to keep the LLM context tight.
MAX_ANNOTATIONS = 50


def enrich(data: dict[str, Any], lexicon: Lexicon) -> dict[str, Any]:
    """Enrich a tool response dict with knowledge annotations.

    Returns a NEW dict — the input is not mutated.
    """
    # Strip any pre-existing annotations from the input copy so the
    # function is idempotent: enrich(enrich(x)) == enrich(x)
    working = copy.deepcopy(data)
    working.pop("knowledge_annotations", None)

    annotations: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()  # (field_path, lexicon_id)

    _walk(working, "", lexicon, annotations, seen_keys)

    working["knowledge_annotations"] = [
        a for a in annotations[:MAX_ANNOTATIONS]
    ]
    return working


def _walk(
    node: Any,
    path: str,
    lexicon: Lexicon,
    annotations: list[dict[str, Any]],
    seen: set[tuple[str, str]],
) -> None:
    if len(annotations) >= MAX_ANNOTATIONS:
        return

    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else key
            _walk(value, child_path, lexicon, annotations, seen)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            child_path = f"{path}[{i}]"
            _walk(item, child_path, lexicon, annotations, seen)
    elif isinstance(node, str):
        _scan_string(node, path, lexicon, annotations, seen)


def _scan_string(
    text: str,
    field_path: str,
    lexicon: Lexicon,
    annotations: list[dict[str, Any]],
    seen: set[tuple[str, str]],
) -> None:
    """Find lexicon terms in a string with case-insensitive word-boundary
    matching. The first matching term wins per (field_path, lexicon_id)."""
    if not text:
        return
    text_lower = text.lower()
    for term_lower, entry in lexicon.term_index.items():
        # Word-boundary match: term must be surrounded by non-word chars
        # or string boundaries.
        pattern = r"\b" + re.escape(term_lower) + r"\b"
        m = re.search(pattern, text_lower)
        if m:
            # Recover original casing from the source text
            matched_text = text[m.start():m.end()]
            key = (field_path, entry.id)
            if key in seen:
                continue
            seen.add(key)
            annotations.append({
                "field_path": field_path,
                "matched_term": matched_text,
                "lexicon_id": entry.id,
                "short_definition": entry.short_definition,
                "clinical_context": entry.clinical_context,
                "review_status": entry.review_status,
            })
            if len(annotations) >= MAX_ANNOTATIONS:
                return

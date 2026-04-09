"""YAML loader for the oncology lexicon.

Reads the lexicon YAML file, validates each entry against the Pydantic
schema, and builds case-insensitive lookup indices for terms and aliases.

The loader is called once at server startup (singleton). Repeated calls
re-parse — there is no caching at this layer.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from app.knowledge.oncology.schema import Lexicon, LexiconEntry

__all__ = ["load_lexicon", "DEFAULT_LEXICON_PATH"]


DEFAULT_LEXICON_PATH = Path(__file__).parent / "lexicon.yaml"


def _build_lexicon(entries: list[LexiconEntry]) -> Lexicon:
    """Build a fully-wired ``Lexicon`` from a list of entries.

    Populates both the ``term_index`` (case-insensitive lookup from
    canonical terms and aliases to their ``LexiconEntry``) and the
    ``matcher_re`` (a single pre-compiled alternation regex covering
    every term, sorted longest-first so ``re.finditer`` naturally
    prefers longer matches).

    Used by both ``load_lexicon`` at startup and by test fixtures.

    The combined-regex approach replaces the per-term loop that used
    to recompile ~700 regex patterns per string — Python's ``re`` cache
    holds 512 entries by default, so 700 terms thrashed the cache and
    enrichment took ~700ms per ``build_response`` call. With a single
    compiled pattern, the same call is ~1ms.
    """
    term_index: dict[str, LexiconEntry] = {}
    for entry in entries:
        term_index[entry.term.lower()] = entry
        for alias in entry.aliases:
            term_index[alias.lower()] = entry

    matcher_re: re.Pattern | None = None
    if term_index:
        # Sort terms by length (longest first) so the regex alternation
        # prefers longer matches. This is critical for correctness:
        # e.g. "active, not recruiting" must win over "recruiting"
        # because they have opposite semantic meanings.
        sorted_terms = sorted(term_index.keys(), key=len, reverse=True)
        escaped = [re.escape(t) for t in sorted_terms]
        combined_pattern = r"\b(" + "|".join(escaped) + r")\b"
        matcher_re = re.compile(combined_pattern, re.IGNORECASE)

    return Lexicon(entries=entries, term_index=term_index, matcher_re=matcher_re)


def load_lexicon(path: Path | None = None) -> Lexicon:
    """Load and validate the lexicon from a YAML file.

    Args:
        path: Optional path to a YAML file. Defaults to
            ``app/knowledge/oncology/lexicon.yaml``.

    Returns:
        A ``Lexicon`` with parsed entries, case-insensitive
        ``term_index`` covering canonical terms and all aliases, and a
        pre-compiled ``matcher_re`` alternation.
    """
    yaml_path = path or DEFAULT_LEXICON_PATH
    raw: dict[str, Any] = yaml.safe_load(yaml_path.read_text()) or {}
    raw_entries = raw.get("entries") or []

    entries = [LexiconEntry(**entry) for entry in raw_entries]
    return _build_lexicon(entries)

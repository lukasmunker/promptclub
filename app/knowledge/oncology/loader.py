"""YAML loader for the oncology lexicon.

Reads the lexicon YAML file, validates each entry against the Pydantic
schema, and builds case-insensitive lookup indices for terms and aliases.

The loader is called once at server startup (singleton). Repeated calls
re-parse — there is no caching at this layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.knowledge.oncology.schema import Lexicon, LexiconEntry

__all__ = ["load_lexicon", "DEFAULT_LEXICON_PATH"]


DEFAULT_LEXICON_PATH = Path(__file__).parent / "lexicon.yaml"


def load_lexicon(path: Path | None = None) -> Lexicon:
    """Load and validate the lexicon from a YAML file.

    Args:
        path: Optional path to a YAML file. Defaults to
            ``app/knowledge/oncology/lexicon.yaml``.

    Returns:
        A ``Lexicon`` with parsed entries and case-insensitive
        ``term_index`` covering canonical terms and all aliases.
    """
    yaml_path = path or DEFAULT_LEXICON_PATH
    raw: dict[str, Any] = yaml.safe_load(yaml_path.read_text()) or {}
    raw_entries = raw.get("entries") or []

    entries = [LexiconEntry(**entry) for entry in raw_entries]
    term_index: dict[str, LexiconEntry] = {}
    for entry in entries:
        term_index[entry.term.lower()] = entry
        for alias in entry.aliases:
            term_index[alias.lower()] = entry

    return Lexicon(entries=entries, term_index=term_index)

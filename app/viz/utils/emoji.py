"""Emoji lookup helpers for phase, status, and source indicators.

Provides quick Unicode prefixes so tables in the inline recipes show a
visual cue before the text label. Everything here is plain Unicode — no
rendering engine, no dependency on any LibreChat feature beyond basic
text display.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "phase_emoji",
    "status_emoji",
    "source_emoji",
    "format_phase",
    "format_status",
]


# --- Phase -----------------------------------------------------------------
# ClinicalTrials.gov returns phase as strings like "Phase 1", "PHASE2",
# "Early Phase 1", "Phase 1/2", "Phase 2/Phase 3", "N/A", etc. Sometimes
# our own adapter joins a list into "Phase 2/Phase 3". Instead of doing
# substring matching (which misfires on things like "Phase 17"), we
# extract the phase *numbers* via regex and look up by the normalized set.

# Exact-string shortcuts for non-numeric phase labels
_EXACT_PHASE_EMOJI = {
    "n/a": "▫️",
    "na": "▫️",
    "not applicable": "▫️",
    "early phase 1": "🔬",
}

# Emoji per set of unique phase numbers. "Phase 1/2" → {1, 2}, etc.
# The highest phase in the set wins (so "Phase 2/3" is a 🧪 for the P2
# work but visually we prefer the later-stage emoji for the combined set
# because that's what the trial is aiming for).
_NUMERIC_PHASE_EMOJI = {
    1: "🔬",
    2: "🧪",
    3: "💊",
    4: "✅",
}

# Matches any standalone digit sequence between 1 and 4 inclusive — "17"
# won't match, "1/2" will match as {1, 2}, "Phase 3, Phase 4" as {3, 4}.
_PHASE_NUMBER_RE = re.compile(r"\b([1-4])\b")


def phase_emoji(phase: Any) -> str:
    """Return a single emoji for a phase string.

    - Known non-numeric labels (N/A, Early Phase 1) have direct mappings
    - Numeric phases are extracted by regex; the *highest* phase in the
      extracted set determines the emoji (so "Phase 2/3" → 💊)
    - Unknown/unparseable phase → ``▫️``
    - Missing value → empty string
    """
    if phase is None:
        return ""
    key = str(phase).strip().lower()
    if not key:
        return ""

    # Non-numeric exact matches first
    if key in _EXACT_PHASE_EMOJI:
        return _EXACT_PHASE_EMOJI[key]

    # Extract phase numbers 1-4 and pick the highest
    matches = _PHASE_NUMBER_RE.findall(key)
    phases = {int(m) for m in matches}
    if phases:
        highest = max(phases)
        return _NUMERIC_PHASE_EMOJI.get(highest, "▫️")

    # Handle "Early Phase 1" again after regex failed (no "1" between word
    # boundaries because "phase 1" is written without separator) —
    # actually regex already catches it because of \b. Double-check:
    # "early phase 1" → \b1\b matches → {1} → 🔬 ✓

    return "▫️"


def format_phase(phase: Any) -> str:
    """``'Phase 3'`` → ``'💊 Phase 3'``. Missing value → ``'—'``."""
    if phase is None or str(phase).strip() == "":
        return "—"
    return f"{phase_emoji(phase)} {phase}"


# --- Status ----------------------------------------------------------------

_STATUS_EMOJI = {
    "recruiting": "🟢",
    "active, not recruiting": "🟡",
    "active not recruiting": "🟡",
    "not yet recruiting": "🔵",
    "enrolling by invitation": "🔵",
    "completed": "⚪",
    "terminated": "🔴",
    "withdrawn": "🔴",
    "suspended": "⏸️",
    "unknown status": "❔",
    "unknown": "❔",
    "available": "🟢",
    "no longer available": "⚪",
    "temporarily not available": "⏸️",
    "approved for marketing": "✅",
    "withheld": "🔴",
}


def status_emoji(status: Any) -> str:
    """Return an emoji for a clinical-trial status string. Unknown status →
    ``❔``, missing value → empty string."""
    if status is None:
        return ""
    key = str(status).strip().lower()
    if not key:
        return ""
    if key in _STATUS_EMOJI:
        return _STATUS_EMOJI[key]
    return "❔"


def format_status(status: Any) -> str:
    """``'Recruiting'`` → ``'🟢 Recruiting'``. Missing value → ``'—'``."""
    if status is None or str(status).strip() == "":
        return "—"
    return f"{status_emoji(status)} {status}"


# --- Source kind -----------------------------------------------------------
# Used by the citation footer when we want a quick visual per-source.

_SOURCE_EMOJI = {
    "clinicaltrials.gov": "🏥",
    "pubmed": "📄",
    "openfda": "💊",
    "opentargets": "🎯",
    "web": "🌐",
}


def source_emoji(kind: Any) -> str:
    if kind is None:
        return ""
    key = str(kind).strip().lower()
    return _SOURCE_EMOJI.get(key, "🔗")

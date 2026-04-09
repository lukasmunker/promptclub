"""Lightweight JSONL coverage logger.

Writes one line per build_response() invocation to logs/viz_coverage.jsonl.
Used to validate the visualization coverage guarantee against real traffic
and prioritize fallback hot spots.

This is intentionally trivial — no log rotation, no async, no
configurable level. If logging fails for any reason (disk full, perms),
the failure is swallowed because coverage logging must NEVER break the
hot path.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["log_entry", "LOG_PATH"]


REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = REPO_ROOT / "logs" / "viz_coverage.jsonl"


def log_entry(
    tool: str,
    recipe: str,
    fallback_used: bool,
    fallback_reason: str,
) -> None:
    """Append one coverage record to the JSONL log.

    Failures are silently swallowed — this function MUST NOT raise.
    """
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "recipe": recipe,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
        }
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - logging must not break hot path
        pass

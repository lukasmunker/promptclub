"""Regression ratchet: no new unguarded SKIP paths may enter the codebase.

After the coverage guarantee work, every Decision.skip(...) call has been
either removed from app/viz/decision.py or routed through build_response's
fallback dispatcher. This test re-runs the static audit and asserts the
total count is at or below the locked-in baseline.

Update RATCHET_MAX only when intentionally adding a new SKIP that you
know will be caught by build_response's fallback (e.g., adding a new
tool whose decision logic skips for the trivial case). Never update it
to make a failing test pass without understanding why.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from audit_viz_paths import run_audit  # noqa: E402

# Locked-in baseline: the number of Decision.skip() sites that are
# acceptable because build_response routes them through the fallback
# dispatcher. The legacy `_maybe_no_data` and dict `no_data` literals
# must be ZERO.
RATCHET_MAX_SKIP_SITES = 14
RATCHET_MAX_NO_DATA_SITES = 0
RATCHET_MAX_MANUAL_ENVELOPE_SITES = 0


def test_skip_sites_within_baseline():
    result = run_audit()
    assert len(result.skip_sites) <= RATCHET_MAX_SKIP_SITES, (
        f"Found {len(result.skip_sites)} Decision.skip() sites — "
        f"baseline is {RATCHET_MAX_SKIP_SITES}. New SKIP sites are only "
        f"allowed if you also verify build_response routes them through "
        f"the fallback dispatcher. Sites:\n"
        + "\n".join(f"  {s.file}:{s.line} — {s.snippet}" for s in result.skip_sites)
    )


def test_no_data_literals_eliminated():
    result = run_audit()
    assert len(result.no_data_sites) == RATCHET_MAX_NO_DATA_SITES, (
        f"Found {len(result.no_data_sites)} `no_data` literal sites — "
        f"all such sites must be eliminated. The [NO DATA AVAILABLE] "
        f"path is dead. Sites:\n"
        + "\n".join(f"  {s.file}:{s.line} — {s.snippet}" for s in result.no_data_sites)
    )


def test_no_manual_envelope_sites():
    result = run_audit()
    assert len(result.manual_envelope_sites) == RATCHET_MAX_MANUAL_ENVELOPE_SITES, (
        f"Found {len(result.manual_envelope_sites)} manual envelope dict literals "
        f"missing 'ui' key — all envelopes must come from build_response. Sites:\n"
        + "\n".join(
            f"  {s.file}:{s.line} — {s.snippet}"
            for s in result.manual_envelope_sites
        )
    )

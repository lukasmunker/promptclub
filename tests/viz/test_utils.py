"""Tests for the small utility helpers (html, mermaid, identifiers)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.viz.utils.html import (
    assert_safe_html,
    escape_html,
    strip_dangerous_html,
)
from app.viz.utils.identifiers import make_identifier, slug, today_iso
from app.viz.utils.mermaid import is_valid_iso_date, safe_label


# --- html -------------------------------------------------------------------


def test_escape_html_basic():
    assert escape_html("<b>Hi</b>") == "&lt;b&gt;Hi&lt;/b&gt;"
    assert escape_html('"quoted"') == "&quot;quoted&quot;"
    assert escape_html(None) == ""
    assert escape_html(42) == "42"


def test_strip_dangerous_html_removes_scripts():
    body = '<div>Safe</div><script>alert("x")</script><p>also safe</p>'
    cleaned = strip_dangerous_html(body)
    assert "<script>" not in cleaned
    assert "alert" not in cleaned
    assert "<div>Safe</div>" in cleaned
    assert "<p>also safe</p>" in cleaned


def test_strip_dangerous_html_removes_event_handlers():
    body = '<img src="x" onerror="alert(1)">'
    cleaned = strip_dangerous_html(body)
    assert "onerror" not in cleaned


def test_strip_dangerous_html_removes_javascript_urls():
    body = '<a href="javascript:alert(1)">click</a>'
    cleaned = strip_dangerous_html(body)
    assert "javascript:" not in cleaned


def test_assert_safe_html_raises_on_script():
    with pytest.raises(ValueError):
        assert_safe_html("<div><script>bad</script></div>")


def test_assert_safe_html_passes_clean_tailwind_body():
    body = '<div class="grid gap-3"><article class="rounded-lg border p-4">Hi</article></div>'
    assert_safe_html(body)  # should not raise


# --- mermaid ---------------------------------------------------------------


def test_safe_label_strips_forbidden_chars():
    assert safe_label("a:b") == "ab"
    assert safe_label('a"b') == "ab"
    assert safe_label("a<b>c") == "abc"
    assert safe_label("a(b)c") == "abc"


def test_safe_label_collapses_whitespace():
    assert safe_label("  a   b  ") == "a b"


def test_safe_label_empty_returns_placeholder():
    assert safe_label("") == "(untitled)"
    assert safe_label(None) == "(untitled)"
    assert safe_label('":"') == "(untitled)"


def test_safe_label_truncation():
    result = safe_label("a" * 100, max_length=10)
    assert len(result) <= 10
    assert result.endswith("…")


def test_is_valid_iso_date():
    assert is_valid_iso_date("2026-04-09")
    assert is_valid_iso_date("2020-01-01")
    assert not is_valid_iso_date("2026-4-9")
    assert not is_valid_iso_date("April 9, 2026")
    assert not is_valid_iso_date("")
    assert not is_valid_iso_date(None)
    assert not is_valid_iso_date(20260409)


# --- identifiers -----------------------------------------------------------


def test_slug_basic():
    assert slug("Phase 3 Melanoma Trials") == "phase-3-melanoma-trials"
    assert slug("NSCLC / NSCLC-adeno") == "nsclc-nsclc-adeno"
    assert slug("") == "untitled"
    assert slug(None) == "untitled"


def test_slug_max_length():
    assert len(slug("x" * 100, max_length=20)) <= 20


def test_today_iso_with_fake_clock():
    fake = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)
    assert today_iso(fake) == "2026-04-09"


def test_make_identifier_deterministic():
    fake = datetime(2026, 4, 9, tzinfo=timezone.utc)
    ident = make_identifier("trial_search_results", "melanoma phase 3", clock=fake)
    assert ident == "trial_search_results-melanoma-phase-3-2026-04-09"


# --- emoji helpers ---------------------------------------------------------

from app.viz.utils.emoji import (  # noqa: E402
    format_phase,
    format_status,
    phase_emoji,
    status_emoji,
)


def test_phase_emoji_known_values():
    assert phase_emoji("Phase 1") == "🔬"
    assert phase_emoji("Phase 2") == "🧪"
    assert phase_emoji("Phase 3") == "💊"
    assert phase_emoji("Phase 4") == "✅"
    assert phase_emoji("Early Phase 1") == "🔬"
    assert phase_emoji("PHASE 3") == "💊"  # Case-insensitive


def test_phase_emoji_unknown_fallback():
    assert phase_emoji("Phase 17") == "▫️"
    assert phase_emoji("") == ""
    assert phase_emoji(None) == ""


def test_format_phase_prefixes_emoji():
    assert format_phase("Phase 3") == "💊 Phase 3"
    assert format_phase("Phase 1") == "🔬 Phase 1"
    assert format_phase(None) == "—"
    assert format_phase("") == "—"


def test_status_emoji_known_values():
    assert status_emoji("Recruiting") == "🟢"
    assert status_emoji("Completed") == "⚪"
    assert status_emoji("Terminated") == "🔴"
    assert status_emoji("Active, not recruiting") == "🟡"
    assert status_emoji("Suspended") == "⏸️"


def test_status_emoji_unknown_fallback():
    assert status_emoji("Weird status") == "❔"
    assert status_emoji(None) == ""
    assert status_emoji("") == ""


def test_format_status_prefixes_emoji():
    assert format_status("Recruiting") == "🟢 Recruiting"
    assert format_status("Completed") == "⚪ Completed"
    assert format_status(None) == "—"

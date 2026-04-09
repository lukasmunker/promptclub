"""Tests for the lightweight coverage logger."""

import json
from pathlib import Path

import pytest

from app.viz import coverage_log


@pytest.fixture
def tmp_log_path(tmp_path, monkeypatch) -> Path:
    log_file = tmp_path / "viz_coverage.jsonl"
    monkeypatch.setattr(coverage_log, "LOG_PATH", log_file)
    return log_file


def test_log_entry_writes_jsonl(tmp_log_path):
    coverage_log.log_entry(
        tool="search_clinical_trials",
        recipe="trial_search_results",
        fallback_used=False,
        fallback_reason="",
    )
    lines = tmp_log_path.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["tool"] == "search_clinical_trials"
    assert record["recipe"] == "trial_search_results"
    assert record["fallback_used"] is False
    assert "ts" in record


def test_log_entry_records_fallback_with_reason(tmp_log_path):
    coverage_log.log_entry(
        tool="get_trial_details",
        recipe="info_card",
        fallback_used=True,
        fallback_reason="sparse trial record",
    )
    record = json.loads(tmp_log_path.read_text().strip())
    assert record["fallback_used"] is True
    assert record["fallback_reason"] == "sparse trial record"


def test_log_entry_appends_does_not_overwrite(tmp_log_path):
    coverage_log.log_entry(tool="t1", recipe="r1", fallback_used=False, fallback_reason="")
    coverage_log.log_entry(tool="t2", recipe="r2", fallback_used=True, fallback_reason="x")
    lines = tmp_log_path.read_text().strip().splitlines()
    assert len(lines) == 2


def test_log_entry_creates_parent_dir(tmp_path, monkeypatch):
    nested = tmp_path / "deep" / "nested" / "viz_coverage.jsonl"
    monkeypatch.setattr(coverage_log, "LOG_PATH", nested)
    coverage_log.log_entry(tool="t", recipe="r", fallback_used=False, fallback_reason="")
    assert nested.exists()

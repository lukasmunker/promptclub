"""Shared pytest fixtures for app.viz tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    path = FIXTURE_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def search_melanoma_phase3() -> dict:
    return _load_fixture("search_melanoma_phase3.json")


@pytest.fixture
def search_empty() -> dict:
    return _load_fixture("search_empty.json")


@pytest.fixture
def indication_landscape_nsclc() -> dict:
    return _load_fixture("indication_landscape_nsclc.json")


@pytest.fixture
def trial_details_nct01() -> dict:
    return _load_fixture("trial_details_nct01.json")


@pytest.fixture
def compare_trials_three() -> dict:
    return _load_fixture("compare_trials_three.json")


@pytest.fixture
def compare_trials_many() -> dict:
    return _load_fixture("compare_trials_many.json")


@pytest.fixture
def sources_clinicaltrials() -> list[dict]:
    return [
        {
            "kind": "clinicaltrials.gov",
            "id": "NCT01234567",
            "url": "https://clinicaltrials.gov/study/NCT01234567",
            "retrieved_at": "2026-04-09T12:00:00Z",
        }
    ]

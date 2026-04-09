from __future__ import annotations

import asyncio
import time

import pytest

from app.models import Citation, TrialRecord
from app.services.orchestration import Orchestrator
from app.settings import settings


class SlowPubMed:
    async def get_publications_for_trial(self, nct_id: str, page_size: int = 3):
        await asyncio.sleep(0.05)
        return []


class FixedClinicalTrials:
    async def search_trials(self, **kwargs):
        return [
            TrialRecord(
                source="ClinicalTrials.gov",
                source_id=f"NCT{i:08d}",
                nct_id=f"NCT{i:08d}",
                title=f"Trial {i}",
                citations=[Citation(source="ClinicalTrials.gov", id=f"NCT{i:08d}")],
            )
            for i in range(1, 6)
        ]


@pytest.mark.asyncio
async def test_search_trials_publication_enrichment_runs_in_parallel(monkeypatch):
    monkeypatch.setattr(settings, "max_trials_to_enrich_with_publications", 5)
    monkeypatch.setattr(settings, "per_trial_publication_lookup_timeout_seconds", 1)

    orchestrator = Orchestrator()
    orchestrator.ct = FixedClinicalTrials()
    orchestrator.pubmed = SlowPubMed()

    started = time.perf_counter()
    result = await orchestrator.search_trials_with_publications("melanoma")
    elapsed = time.perf_counter() - started

    assert len(result.trials) == 5
    assert elapsed < 0.2


class HangingPubMed:
    async def get_publications_for_trial(self, nct_id: str, page_size: int = 3):
        await asyncio.sleep(10)
        return []


@pytest.mark.asyncio
async def test_search_trials_publication_enrichment_is_time_bounded(monkeypatch):
    monkeypatch.setattr(settings, "max_trials_to_enrich_with_publications", 3)
    monkeypatch.setattr(settings, "per_trial_publication_lookup_timeout_seconds", 0.01)

    orchestrator = Orchestrator()
    orchestrator.ct = FixedClinicalTrials()
    orchestrator.pubmed = HangingPubMed()

    started = time.perf_counter()
    result = await orchestrator.search_trials_with_publications("melanoma")
    elapsed = time.perf_counter() - started

    assert len(result.trials) == 5
    assert result.publications == []
    assert elapsed < 0.2

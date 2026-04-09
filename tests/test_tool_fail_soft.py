from __future__ import annotations

import pytest

import app.main as app_main
from app.main import search_trials, web_context_search


async def _raise_error(*args, **kwargs):
    raise RuntimeError("upstream exploded")


async def _return_empty(*args, **kwargs):
    return []


@pytest.mark.asyncio
async def test_search_trials_fails_softly(monkeypatch):
    monkeypatch.setattr(app_main.orchestrator, "search_trials_with_publications", _raise_error)

    result = await search_trials("melanoma")

    assert result["summary"] == "ClinicalTrials.gov search failed."
    assert result["trials"] == []
    assert result["publications"] == []
    assert result["error"] == "upstream exploded"


@pytest.mark.asyncio
async def test_web_context_search_warns_instead_of_failing(monkeypatch):
    monkeypatch.setattr(app_main.orchestrator, "web_context", _return_empty)

    result = await web_context_search("latest melanoma updates")

    assert result["count"] == 0
    assert result["results"] == []
    assert "warning" in result

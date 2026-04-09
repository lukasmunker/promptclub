import pytest

from app.adapters.clinicaltrials_v2 import ClinicalTrialsV2Adapter
from app.adapters.openfda import OpenFDAAdapter
from app.adapters.opentargets import OpenTargetsAdapter
from app.adapters.pubmed import PubMedAdapter


@pytest.mark.asyncio
async def test_clinicaltrials_v2_smoke():
    adapter = ClinicalTrialsV2Adapter()
    results = await adapter.search_trials(condition="melanoma", term="melanoma", page_size=2)
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_pubmed_smoke():
    adapter = PubMedAdapter()
    results = await adapter.search_publications("melanoma phase 3 trial", page_size=2)
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_opentargets_smoke():
    adapter = OpenTargetsAdapter()
    results = await adapter.get_target_context("EFO_0000756", page_size=2)
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_openfda_smoke():
    adapter = OpenFDAAdapter()
    results = await adapter.search_regulatory_context("Keytruda", limit=2)
    assert isinstance(results, list)
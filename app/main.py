from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP

from app.services.orchestration import Orchestrator
from app.settings import settings


orchestrator = Orchestrator()
mcp = FastMCP(name="clinical-intelligence-mcp")


@mcp.tool()
async def search_trials(
    disease_query: str,
    phase: str | None = None,
    sponsor: str | None = None,
    page_size: int = 10,
) -> dict[str, Any]:
    """
    Search oncology trial records from ClinicalTrials.gov and enrich them with linked PubMed publications.
    """
    result = await orchestrator.compare_trials(
        disease_query=disease_query,
        phase=phase,
        sponsor=sponsor,
        page_size=page_size,
    )
    return result.model_dump()


@mcp.tool()
async def get_trial_details(nct_id: str) -> dict[str, Any]:
    """
    Fetch a single trial record by NCT ID from ClinicalTrials.gov.
    """
    record = await orchestrator.ct.get_trial(nct_id)
    if not record:
        return {"found": False, "nct_id": nct_id}
    return {"found": True, "trial": record.model_dump()}


@mcp.tool()
async def search_publications(query: str, page_size: int = 10) -> dict[str, Any]:
    """
    Search PubMed for publications relevant to a disease, therapy, sponsor, or NCT ID.
    """
    pubs = await orchestrator.pubmed.search_publications(query=query, page_size=page_size)
    return {"count": len(pubs), "results": [p.model_dump() for p in pubs]}


@mcp.tool()
async def get_target_context(disease_id: str) -> dict[str, Any]:
    """
    Get target-disease associations from Open Targets using an ontology disease ID, e.g. EFO_0000756.
    """
    rows = await orchestrator.get_target_context(disease_id=disease_id)
    return {"count": len(rows), "results": [r.model_dump() for r in rows]}


@mcp.tool()
async def get_regulatory_context(drug_name: str) -> dict[str, Any]:
    """
    Get public FDA labeling/regulatory context for a therapy name using openFDA.
    """
    rows = await orchestrator.get_regulatory_context(drug_name=drug_name)
    return {"count": len(rows), "results": [r.model_dump() for r in rows]}


@mcp.tool()
async def test_data_sources(sample_query: str = "melanoma") -> dict[str, Any]:
    """
    Run live health checks against all configured data sources.
    """
    results = await orchestrator.test_sources(sample_query=sample_query)
    return {"results": [r.model_dump() for r in results]}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "ok": True,
        "app": settings.app_name,
        "env": settings.app_env,
    }


@app.get("/health/sources")
async def health_sources():
    results = await orchestrator.test_sources(sample_query="melanoma")
    return {"results": [r.model_dump() for r in results]}


# Mount the MCP ASGI app at /mcp
app.mount("/mcp", mcp.streamable_http_app())
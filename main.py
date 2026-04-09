from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

from app.citations import attach_citation_layer, citations_from_rows
from app.services.orchestration import Orchestrator
from app.settings import settings


orchestrator = Orchestrator()
mcp = FastMCP(name="clinical-intelligence-mcp")


@mcp.tool()
async def search_trials(
    disease_query: str,
    page_size: int = 10,
    phase: str | None = None,
    sponsor: str | None = None,
    status: str | None = None,
    include_web_context: bool = False,
) -> dict[str, Any]:
    """
    Search public oncology trial records from ClinicalTrials.gov v2 and linked PubMed data.
    Use only publicly available sources. Do not make speculative or strategic recommendations.
    """
    result = await orchestrator.search_trials_with_publications(
        disease_query=disease_query,
        page_size=page_size,
        phase=phase,
        sponsor=sponsor,
        status=status,
        include_web_context=include_web_context,
    )
    return attach_citation_layer(result.model_dump(), result.citations)


@mcp.tool()
async def resolve_disease(query: str, page_size: int = 5) -> dict[str, Any]:
    """
    Resolve free-text disease names to Open Targets disease IDs.
    """
    rows = await orchestrator.resolve_disease(query=query, page_size=page_size)
    return attach_citation_layer(
        {"count": len(rows), "results": [r.model_dump() for r in rows]},
        citations_from_rows(rows),
    )


@mcp.tool()
async def get_trial_details(nct_id: str) -> dict[str, Any]:
    """
    Fetch one ClinicalTrials.gov study by NCT ID.
    """
    record = await orchestrator.get_trial_details(nct_id)
    if not record:
        return {"found": False, "nct_id": nct_id}
    return attach_citation_layer(
        {"found": True, "trial": record.model_dump()},
        record.citations,
    )


@mcp.tool()
async def search_publications(query: str, page_size: int = 10) -> dict[str, Any]:
    """
    Search PubMed via NCBI E-utilities.
    """
    rows = await orchestrator.search_publications(query=query, page_size=page_size)
    return attach_citation_layer(
        {"count": len(rows), "results": [r.model_dump() for r in rows]},
        citations_from_rows(rows),
    )


@mcp.tool()
async def get_target_context(disease_id: str) -> dict[str, Any]:
    """
    Get target-disease associations from Open Targets using a disease ID.
    """
    rows = await orchestrator.get_target_context(disease_id=disease_id)
    return attach_citation_layer(
        {"count": len(rows), "results": [r.model_dump() for r in rows]},
        citations_from_rows(rows),
    )


@mcp.tool()
async def get_regulatory_context(drug_name: str) -> dict[str, Any]:
    """
    Get public regulatory/label context from openFDA.
    """
    rows = await orchestrator.get_regulatory_context(drug_name=drug_name)
    return attach_citation_layer(
        {"count": len(rows), "results": [r.model_dump() for r in rows]},
        citations_from_rows(rows),
    )


@mcp.tool()
async def web_context_search(query: str) -> dict[str, Any]:
    """
    Optional Vertex AI Google Search grounding for public web context.
    """
    rows = await orchestrator.web_context(query=query)
    return attach_citation_layer(
        {"count": len(rows), "results": [r.model_dump() for r in rows]},
        citations_from_rows(rows),
    )


@mcp.tool()
async def test_data_sources(sample_query: str = "melanoma") -> dict[str, Any]:
    """
    Run live smoke tests against all configured sources.
    """
    rows = await orchestrator.test_sources(sample_query=sample_query)
    return {"results": [r.model_dump() for r in rows]}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.get("/")
async def root():
    base = settings.public_base_url or ""
    return {
        "service": settings.app_name,
        "status": "ok",
        "mcp_path": "/mcp",
        "mcp_url": f"{base}/mcp" if base else None,
        "health_url": f"{base}/health" if base else None,
    }


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


app.mount("/mcp", mcp.streamable_http_app())

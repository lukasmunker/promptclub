from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP

from app.citations import attach_citation_layer, citations_from_rows
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
    result = await orchestrator.search_trials_with_publications(
        disease_query=disease_query,
        phase=phase,
        sponsor=sponsor,
        page_size=page_size,
    )
    return attach_citation_layer(result.model_dump(), result.citations)


@mcp.tool()
async def get_trial_details(nct_id: str) -> dict[str, Any]:
    """
    Fetch a single trial record by NCT ID from ClinicalTrials.gov.
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
    Search PubMed for publications relevant to a disease, therapy, sponsor, or NCT ID.
    """
    pubs = await orchestrator.search_publications(query=query, page_size=page_size)
    return attach_citation_layer(
        {"count": len(pubs), "results": [p.model_dump() for p in pubs]},
        citations_from_rows(pubs),
    )


@mcp.tool()
async def get_target_context(disease_id: str) -> dict[str, Any]:
    """
    Get target-disease associations from Open Targets using an ontology disease ID, e.g. EFO_0000756.
    """
    rows = await orchestrator.get_target_context(disease_id=disease_id)
    return attach_citation_layer(
        {"count": len(rows), "results": [r.model_dump() for r in rows]},
        citations_from_rows(rows),
    )


@mcp.tool()
async def get_regulatory_context(drug_name: str) -> dict[str, Any]:
    """
    Get public FDA labeling/regulatory context for a therapy name using openFDA.
    """
    rows = await orchestrator.get_regulatory_context(drug_name=drug_name)
    return attach_citation_layer(
        {"count": len(rows), "results": [r.model_dump() for r in rows]},
        citations_from_rows(rows),
    )


@mcp.tool()
async def resolve_disease(query: str, page_size: int = 5) -> dict[str, Any]:
    """
    Resolve a free-text disease name to Open Targets disease IDs (EFO ontology).
    Use before get_target_context when you only have a disease name, not an EFO ID.
    """
    rows = await orchestrator.resolve_disease(query=query, page_size=page_size)
    return attach_citation_layer(
        {"count": len(rows), "results": [r.model_dump() for r in rows]},
        citations_from_rows(rows),
    )


@mcp.tool()
async def web_context_search(query: str) -> dict[str, Any]:
    """
    Search public web sources via Vertex AI Google Search grounding.
    Use for recent news, press releases, or context not covered by structured databases.
    Requires GCP Vertex AI credentials (gracefully disabled if unavailable).
    """
    rows = await orchestrator.web_context(query=query)
    return attach_citation_layer(
        {"count": len(rows), "results": [r.model_dump() for r in rows]},
        citations_from_rows(rows),
    )


@mcp.tool()
async def test_data_sources(sample_query: str = "melanoma") -> dict[str, Any]:
    """
    Run live health checks against all configured data sources.
    """
    results = await orchestrator.test_sources(sample_query=sample_query)
    return {"results": [r.model_dump() for r in results]}


# Create MCP ASGI app — triggers lazy session_manager initialization.
_mcp_asgi_inner = mcp.streamable_http_app()


class _MCPPathNormalizer:
    """Normalize /mcp → /mcp/ before FastMCP's router sees the path.

    Starlette's Mount('/mcp') returns Match.NONE for path '/mcp' (no trailing
    slash), so the router sends a 307 redirect. HTTP clients like LibreChat's
    fetch do not resend POST bodies after a redirect. Fixing the path here
    avoids the redirect entirely.
    """

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path") == "/mcp":
            scope = {**scope, "path": "/mcp/"}
        await _mcp_asgi_inner(scope, receive, send)


_mcp_asgi = _MCPPathNormalizer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # StreamableHTTPSessionManager requires its task group to be started.
    # Mounted sub-apps do NOT run their own lifespan, so we start it here.
    async with mcp.session_manager.run():
        yield


app = FastAPI(title=settings.app_name, lifespan=lifespan, redirect_slashes=False)


@app.get("/")
async def root():
    base = settings.public_base_url or ""
    return {
        "service": settings.app_name,
        "status": "ok",
        "mcp_endpoint": f"{base}/mcp",
        "health_url": f"{base}/health",
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


app.mount("/", _mcp_asgi)

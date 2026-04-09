from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP

from app.services.orchestration import Orchestrator
from app.settings import settings
from app.utils import lean_dump


orchestrator = Orchestrator()
mcp = FastMCP(
    name="clinical-intelligence-mcp",
    instructions="""
You are a clinical intelligence assistant specializing in oncology competitive intelligence.
You have access to structured data from ClinicalTrials.gov, PubMed, Open Targets, openFDA,
and a web search grounding service.

ROUTING RULES — choose the right tool for the question:
- "Find trials for [disease]" → search_trials
- "Compare NCT123 vs NCT456" or "side-by-side comparison" → build_trial_comparison
- "How big is the [disease] landscape?" or "how many trials exist?" → analyze_indication_landscape
- "Where are the gaps / whitespace / underserved areas in [disease]?" → analyze_whitespace
- "Who are the key players / sponsors in [disease]?" → get_sponsor_overview
- "Tell me about NCT[ID]" → get_trial_details
- "Find papers / publications about [topic]" → search_publications
- "What targets are associated with [disease]?" → resolve_disease then get_target_context
- "Which drugs target gene/protein X and what trials use them?" → get_known_drugs_for_target
- "Is [drug] FDA approved? / regulatory context" → get_regulatory_context
- "Latest news / recent developments" → web_context_search
- "Is the system working?" → test_data_sources

GUARDRAILS — these are non-negotiable and audit-grade:
- Do NOT make forward-looking investment, regulatory, or clinical outcome predictions.
- Do NOT speculate beyond what the data sources explicitly state.
- If a tool result has `no_data: true`, you MUST tell the user no data was found and you
  MUST NOT supplement the answer with knowledge from your training data. State the gap
  explicitly: "No records were found in [source] for [query]."
- Every claim that cites an NCT id, PMID, EFO id, ChEMBL id or URL MUST appear verbatim
  in the tool output. Do not paraphrase numerical values, dates, or identifiers — quote
  them as returned. Do not construct URLs from patterns; only cite urls from `citations[]`.
- Use `evidence_path` (when present on a record) to attribute each claim to a specific
  data source chain. If two records share an evidence_path, treat them as the same fact.
- Trial↔Publication links: a publication's evidence_path beginning with `ctgov.referencesModule.pmid:`
  is a deterministic link declared by the trial sponsor. Treat that as authoritative.
  A path containing `pubmed-search:abstract-regex-NCT` is a heuristic fallback — flag as
  "weak link" if you rely on it.
- Medical abbreviations (NSCLC, HCC, TNBC, etc.) and trade names (Keytruda, Opdivo) are
  automatically expanded — pass them as-is to the tools.
- Prefer parallel tool calls when multiple independent data sources are needed.
""",
)


def _maybe_no_data(rows: list[Any], source: str, query_descriptor: str) -> dict[str, Any] | None:
    """Return an empty-result envelope with a strong instruction not to supplement
    from training knowledge. Returns None if rows is non-empty (caller proceeds normally)."""
    if rows:
        return None
    return {
        "count": 0,
        "results": [],
        "no_data": True,
        "source": source,
        "query": query_descriptor,
        "do_not_supplement": (
            f"No records were found in {source} for {query_descriptor!r}. "
            "Tell the user no data is available; do NOT answer from training knowledge."
        ),
    }


@mcp.tool()
async def search_trials(
    disease_query: str,
    phase: str | None = None,
    sponsor: str | None = None,
    status: str | None = None,
    page_size: int = 5,
) -> dict[str, Any]:
    """
    Search ClinicalTrials.gov for oncology trials and enrich results with linked PubMed publications.

    USE THIS WHEN: The user asks to find, list, or browse trials for a disease, drug, or sponsor.
    Supports optional filters:
      - phase: "1", "2", "3", "phase 3", "PHASE2" (all formats accepted)
      - sponsor: partial sponsor name, e.g. "[Company]", "Merck"
      - status: "recruiting", "completed", "active", "not_yet_recruiting", etc.
      - page_size: number of results (default 5, max ~100)

    Medical abbreviations (NSCLC, HCC, TNBC) and trade names (Keytruda→pembrolizumab) are
    automatically expanded. Returns full trial records with linked PMIDs and citations.
    """
    result = await orchestrator.search_trials_with_publications(
        disease_query=disease_query,
        phase=phase,
        sponsor=sponsor,
        status=status,
        page_size=page_size,
    )
    empty = _maybe_no_data(
        result.trials,
        source="ClinicalTrials.gov v2",
        query_descriptor=(
            f"disease={disease_query!r} phase={phase} sponsor={sponsor} status={status}"
        ),
    )
    if empty is not None:
        return empty
    return lean_dump(result)


@mcp.tool()
async def get_trial_details(nct_id: str) -> dict[str, Any]:
    """
    Fetch a single trial record by NCT ID from ClinicalTrials.gov.

    USE THIS WHEN: The user asks about a specific trial by its NCT ID (e.g. NCT04516746),
    or wants full details (endpoints, eligibility, locations, linked publications) for one trial.
    Returns complete structured data including inclusion/exclusion criteria and linked PMIDs.
    """
    record = await orchestrator.get_trial_details(nct_id)
    if not record:
        return {"found": False, "nct_id": nct_id}
    return {"found": True, "trial": lean_dump(record)}


@mcp.tool()
async def search_publications(query: str, page_size: int = 10) -> dict[str, Any]:
    """
    Search PubMed for publications relevant to a disease, therapy, sponsor, or NCT ID.

    USE THIS WHEN: The user asks for papers, studies, or evidence from the scientific literature.
    Accepts free-text PubMed queries including MeSH terms, drug names, disease names, or NCT IDs
    (e.g. '"NCT04516746"' to find publications from a specific trial).
    Returns title, abstract, authors, journal, pub date, and linked trial IDs (NCT numbers).
    """
    pubs = await orchestrator.search_publications(query=query, page_size=page_size)
    empty = _maybe_no_data(pubs, source="PubMed", query_descriptor=query)
    if empty is not None:
        return empty
    return {"count": len(pubs), "results": [lean_dump(p) for p in pubs]}


@mcp.tool()
async def get_target_context(disease_id: str) -> dict[str, Any]:
    """
    Get target-disease associations from Open Targets using an EFO ontology disease ID.

    USE THIS WHEN: The user asks about biological targets, mechanisms of action, or which genes/
    proteins are associated with a disease. Requires an EFO ontology ID (e.g. EFO_0000756).
    If you only have a disease name, call resolve_disease first to get the ID.
    Returns ranked targets with association scores from genetics, literature, and pathway data.
    """
    rows = await orchestrator.get_target_context(disease_id=disease_id)
    empty = _maybe_no_data(rows, source="Open Targets", query_descriptor=f"disease_id={disease_id}")
    if empty is not None:
        return empty
    return {"count": len(rows), "results": [lean_dump(r) for r in rows]}


@mcp.tool()
async def get_known_drugs_for_target(ensembl_id: str, page_size: int = 25) -> dict[str, Any]:
    """
    Return drugs developed against a target with their indications and trial IDs —
    the deterministic Drug↔Target↔Trial join from Open Targets `drugAndClinicalCandidates`.

    USE THIS WHEN: The user asks "which drugs target gene X?", "what compounds hit
    PD-1?", "show me the pipeline for ENSG...", or any question that needs to connect
    a target/gene/protein to the drugs developed against it AND the trials those drugs
    appear in. Requires an Ensembl gene ID (e.g. ENSG00000188389 for PDCD1 / PD-1).
    Each row carries an `evidence_path` documenting the deterministic chain
    `target → drug → trial`, so the LLM never has to guess whether a drug from
    openFDA matches an intervention from CT.gov. Use after `get_target_context`
    when the user wants to drill from disease → targets → drugs → trials.
    """
    rows = await orchestrator.get_known_drugs_for_target(
        ensembl_id=ensembl_id, page_size=page_size
    )
    empty = _maybe_no_data(
        rows, source="Open Targets drugAndClinicalCandidates",
        query_descriptor=f"ensembl_id={ensembl_id}",
    )
    if empty is not None:
        return empty
    return {"count": len(rows), "results": [lean_dump(r) for r in rows]}


@mcp.tool()
async def get_regulatory_context(drug_name: str) -> dict[str, Any]:
    """
    Get public FDA labeling and regulatory context for a therapy using openFDA drug labels.

    USE THIS WHEN: The user asks about FDA approval status, indications, warnings, active
    ingredients, or routes of administration for a drug. Accepts brand names (Keytruda) or
    generic/INN names (pembrolizumab). Returns structured label data with indications_and_usage,
    active ingredients, application numbers, and manufacturer.
    """
    rows = await orchestrator.get_regulatory_context(drug_name=drug_name)
    empty = _maybe_no_data(rows, source="openFDA", query_descriptor=f"drug_name={drug_name}")
    if empty is not None:
        return empty
    return {"count": len(rows), "results": [lean_dump(r) for r in rows]}


@mcp.tool()
async def resolve_disease(query: str, page_size: int = 5) -> dict[str, Any]:
    """
    Resolve a free-text disease name to Open Targets EFO ontology IDs.

    USE THIS WHEN: You need an EFO disease ID before calling get_target_context, or when the
    user asks about disease ontology / synonyms. Input can be any disease name — returns
    matched EFO IDs, canonical names, and descriptions. Always call this before
    get_target_context if you only have a free-text disease name.
    """
    rows = await orchestrator.resolve_disease(query=query, page_size=page_size)
    empty = _maybe_no_data(rows, source="Open Targets disease ontology", query_descriptor=query)
    if empty is not None:
        return empty
    return {"count": len(rows), "results": [lean_dump(r) for r in rows]}


@mcp.tool()
async def web_context_search(query: str) -> dict[str, Any]:
    """
    Search public web sources via Vertex AI Google Search grounding for real-time context.

    USE THIS WHEN: The user asks about recent news, press releases, conference data (ASCO, ESMO),
    pipeline announcements, or any information likely to be too recent for structured databases.
    Complements structured data sources but should NOT override them. Requires GCP credentials
    (returns empty gracefully if unavailable). Always cite the web sources returned.
    """
    rows = await orchestrator.web_context(query=query)
    return {"count": len(rows), "results": [lean_dump(r) for r in rows]}


@mcp.tool()
async def test_data_sources(sample_query: str = "melanoma") -> dict[str, Any]:
    """
    Run live health checks against all configured data sources (ClinicalTrials, PubMed, Open Targets, openFDA, Web).

    USE THIS WHEN: The user asks if the system is working, wants to verify connectivity,
    or reports that a data source seems down. Returns latency, status, and sample IDs for each source.
    """
    results = await orchestrator.test_sources(sample_query=sample_query)
    return {"results": [lean_dump(r) for r in results]}


@mcp.tool()
async def build_trial_comparison(nct_ids: list[str]) -> dict[str, Any]:
    """
    Fetch multiple trials in parallel and return them side-by-side for structured comparison.

    USE THIS WHEN: The user wants to compare 2 or more specific trials by their NCT IDs
    (e.g. "compare NCT04516746 and NCT03956680"), or asks for a head-to-head comparison
    of trial designs, endpoints, eligibility, enrollment, or sponsor information.
    Pass a list of NCT IDs — all trials are fetched in parallel for speed.
    Returns full structured records for each trial plus an errors list for any not found.
    """
    return await orchestrator.build_trial_comparison(nct_ids=nct_ids)


@mcp.tool()
async def analyze_indication_landscape(
    condition: str, phase: str | None = None
) -> dict[str, Any]:
    """
    Return a high-level landscape overview for a disease indication across all data sources.

    USE THIS WHEN: The user asks "how big is the [disease] space?", "how many trials are there
    for [condition]?", "what is the research activity level?", or needs a landscape summary
    before diving into specifics. Queries ClinicalTrials.gov, PubMed, openFDA, and Open Targets
    in parallel. Optional phase filter narrows trial count to a specific development stage.
    Returns counts for trials, publications (last 3 years), FDA label records, and disease
    ontology matches. Medical abbreviations (NSCLC, HCC) are automatically expanded.
    """
    return await orchestrator.analyze_indication_landscape(condition=condition, phase=phase)


@mcp.tool()
async def analyze_whitespace(condition: str) -> dict[str, Any]:
    """
    Identify underserved segments and whitespace opportunities in a disease indication.

    USE THIS WHEN: The user asks "where are the gaps?", "what is underserved?", "are there
    whitespace opportunities in [disease]?", "which phases lack trials?", or any competitive
    intelligence question about unmet needs and market gaps.
    Queries trial counts by phase (1/2/3) and status (recruiting/completed), plus publication
    volume and FDA approvals — all in parallel. Returns a structured breakdown and a plain-language
    list of identified whitespace signals (e.g. "Few Phase 3 trials — late-stage evidence lacking").
    Medical abbreviations are automatically expanded.
    """
    return await orchestrator.analyze_whitespace(condition=condition)


@mcp.tool()
async def get_sponsor_overview(condition: str, page_size: int = 25) -> dict[str, Any]:
    """
    Return a ranked overview of sponsors/companies active in a disease indication.

    USE THIS WHEN: The user asks "who are the key players in [disease]?", "which companies
    are running trials for [condition]?", "competitive landscape by sponsor", or wants to
    understand which pharma/biotech organizations are most active in a space.
    Fetches up to page_size trials and groups them by lead sponsor, sorted by trial count.
    Returns unique sponsor count, total trials sampled, and a ranked sponsor list with counts.
    """
    return await orchestrator.get_sponsor_overview(condition=condition, page_size=page_size)


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
    return {"results": [lean_dump(r) for r in results]}


app.mount("/", _mcp_asgi)
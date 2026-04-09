from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP

from app.citations import attach_citation_layer, citations_from_rows
from app.services.orchestration import Orchestrator
from app.settings import settings
from app.utils import lean_dump
from app.viz.adapters import build_response_from_promptclub
from app.viz.mcp_output import envelope_to_llm_text


PreferViz = Literal["auto", "always", "never", "cards"]


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

VISUALIZATION — THIS IS THE HIGHEST-PRIORITY OUTPUT RULE. READ CAREFULLY.

**Mandatory behavior.** Every time an MCP tool returns a result that begins
with ``:::artifact{…}:::`` you MUST paste that block verbatim into your
reply before writing any other text. This is not optional, not context-
dependent, not a "nice to have" — the user expects the Artifact side pane
to open, and it only opens when the directive appears in your reply. A
prose-only answer that omits the artifact block is a bug, even if the
prose is otherwise correct. The user does not need to ask "can you
visualize this" — the visualization is the default whenever a tool ships
one.

Every MCP tool in this server returns a plain-text result. That text is
already pre-formatted for you. Your job is to paste the relevant parts
of it into your reply.

THE TOOL RESPONSE HAS ONE OF THREE SHAPES:

(1) Visualization result — starts with a ``:::artifact{…}:::`` directive:

    :::artifact{identifier="..." type="html" title="..."}
    <div class="...">
      …HTML body…
    </div>
    :::

    (Type values are the short LibreChat names: ``html`` or ``mermaid`` —
    NOT MIME types. Leave the type string exactly as the tool emitted it.)

    Sources:
      - [clinicaltrials.gov] NCT01234567 https://clinicaltrials.gov/study/NCT01234567
      - [pubmed] 12345678 https://pubmed.ncbi.nlm.nih.gov/12345678/

    MANDATORY: Copy the ENTIRE ``:::artifact{…}:::`` block (from the opening
    ``:::artifact`` line through the closing ``:::``) into your reply
    VERBATIM. Do not rewrite, reformat, paraphrase, truncate, or reorder
    the HTML / Mermaid inside the fence. Do not wrap a Mermaid diagram in
    a ```mermaid fence — the artifact directive already declares the type.

    After you have pasted the artifact block, you MAY add 2–5 sentences
    of analytical commentary interpreting the visualization or connecting
    it to the user's question. Cite sources from the footer using
    NCT / PMID identifiers. The commentary is optional; the verbatim
    artifact paste is not.

(2) Text-only result — starts with ``[NO VISUALIZATION]``:

    [NO VISUALIZATION — answer as plain text from the data and sources below]

    Data:
    { … JSON blob of facts … }

    Sources:
      - [opentargets] EFO_0000756 https://…

    Answer the user in plain text using the data + sources. Do NOT
    fabricate an artifact block, do NOT invent a visualization, and do
    NOT paste the raw JSON into your reply. Cite sources using NCT /
    PMID / URL. No forward-looking statements.

(3) Empty result — starts with ``[NO DATA AVAILABLE]``:

    [NO DATA AVAILABLE]
    Source: ClinicalTrials.gov v2
    Query:  disease='foo' phase=3 …

    Tell the user no records were found for that query. Do NOT
    supplement the answer from training knowledge. Do NOT invent or
    hallucinate trials / publications. State the gap explicitly.

GENERAL RULES

- Never invent, fabricate, or hand-write your own ``:::artifact{…}:::``
  block. Only paste the one the tool response gave you.
- Never rewrite an HTML artifact as markdown, bullet lists, or prose.
- Never rewrite a Mermaid artifact as ASCII art or a table.
- Never write a prose-only reply when the tool returned a ``:::artifact``
  block — the user wants to SEE the visualization.
- When multiple tools are called in parallel, include EVERY returned
  ``:::artifact{…}:::`` block in your reply, each copied verbatim, in
  the order the tools were called, separated by a blank line.

COMPLIANCE
- Cite sources using NCT / PMID / URL.
- No forward-looking investment, regulatory, or clinical-outcome predictions.
- No BioNTech strategic recommendations.
""",
)


def _maybe_no_data(rows: list[Any], source: str, query_descriptor: str) -> str | None:
    """Return a pre-formatted ``[NO DATA AVAILABLE]`` tool-text string when
    ``rows`` is empty, or ``None`` if the caller should proceed with normal
    envelope building.

    The returned string goes through ``envelope_to_llm_text`` via the legacy
    no-data dict shape so every MCP tool emits the same format regardless of
    which path it took.
    """
    if rows:
        return None
    return envelope_to_llm_text(
        {
            "no_data": True,
            "source": source,
            "query": query_descriptor,
            "do_not_supplement": (
                f"No records were found in {source} for {query_descriptor!r}. "
                "Tell the user no data is available; do NOT answer from training knowledge."
            ),
        }
    )


@mcp.tool()
async def search_trials(
    disease_query: str,
    phase: str | None = None,
    sponsor: str | None = None,
    status: str | None = None,
    page_size: int = 5,
    prefer_visualization: PreferViz = "auto",
) -> str:
    """
    Search ClinicalTrials.gov for oncology trials and enrich results with linked PubMed publications.

    USE THIS WHEN: The user asks to find, list, or browse trials for a disease, drug, or sponsor.
    Supports optional filters:
      - phase: "1", "2", "3", "phase 3", "PHASE2" (all formats accepted)
      - sponsor: partial sponsor name, e.g. "BioNTech", "Merck"
      - status: "recruiting", "completed", "active", "not_yet_recruiting", etc.
      - page_size: number of results (default 5, max ~100)

    Medical abbreviations (NSCLC, HCC, TNBC) and trade names (Keytruda→pembrolizumab) are
    automatically expanded. Returns a pre-rendered ``:::artifact{…}:::`` text/html block
    for LibreChat's Artifact side pane, plus a compact sources footer. Paste the artifact
    block verbatim into your reply.
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
    viz = build_response_from_promptclub(
        tool_name="search_trials",
        promptclub_data=lean_dump(result),
        prefer_visualization=prefer_visualization,
        query=disease_query,
    )
    return envelope_to_llm_text(attach_citation_layer(viz, result.citations))


@mcp.tool()
async def get_trial_details(
    nct_id: str,
    prefer_visualization: PreferViz = "auto",
) -> str:
    """
    Fetch a single trial record by NCT ID from ClinicalTrials.gov.

    USE THIS WHEN: The user asks about a specific trial by its NCT ID (e.g. NCT04516746),
    or wants full details (endpoints, eligibility, locations, linked publications) for one trial.
    Returns a pre-rendered ``:::artifact{…}:::`` text/html block for LibreChat's Artifact
    side pane (sections for Overview, Design, Eligibility, Arms, Sites, Publications).
    Paste the artifact block verbatim into your reply.
    """
    record = await orchestrator.get_trial_details(nct_id)
    if not record:
        promptclub_data: dict[str, Any] = {"found": False, "nct_id": nct_id}
    else:
        promptclub_data = {"found": True, "trial": lean_dump(record)}
    viz = build_response_from_promptclub(
        tool_name="get_trial_details",
        promptclub_data=promptclub_data,
        prefer_visualization=prefer_visualization,
    )
    return envelope_to_llm_text(
        attach_citation_layer(viz, record.citations if record else None)
    )


@mcp.tool()
async def search_publications(
    query: str,
    page_size: int = 10,
    prefer_visualization: PreferViz = "auto",
) -> str:
    """
    Search PubMed for publications relevant to a disease, therapy, sponsor, or NCT ID.

    USE THIS WHEN: The user asks for papers, studies, or evidence from the scientific literature.
    Accepts free-text PubMed queries including MeSH terms, drug names, disease names, or NCT IDs
    (e.g. '"NCT04516746"' to find publications from a specific trial).

    Returns a pre-rendered ``:::artifact{…}:::`` text/html card list for LibreChat's
    Artifact side pane. Paste the artifact block verbatim into your reply.
    """
    pubs = await orchestrator.search_publications(query=query, page_size=page_size)
    empty = _maybe_no_data(pubs, source="PubMed", query_descriptor=query)
    if empty is not None:
        return empty
    viz = build_response_from_promptclub(
        tool_name="search_publications",
        promptclub_data={
            "count": len(pubs),
            "results": [lean_dump(p) for p in pubs],
        },
        prefer_visualization=prefer_visualization,
        query=query,
    )
    return envelope_to_llm_text(
        attach_citation_layer(viz, citations_from_rows(pubs))
    )


@mcp.tool()
async def get_target_context(
    disease_id: str,
    prefer_visualization: PreferViz = "auto",
) -> str:
    """
    Get target-disease associations from Open Targets using an EFO ontology disease ID.

    USE THIS WHEN: The user asks about biological targets, mechanisms of action, or which genes/
    proteins are associated with a disease. Requires an EFO ontology ID (e.g. EFO_0000756).
    If you only have a disease name, call resolve_disease first to get the ID.

    Returns a pre-rendered ``:::artifact{…}:::`` text/html scored table with CSS bars.
    Paste the artifact block verbatim into your reply.
    """
    rows = await orchestrator.get_target_context(disease_id=disease_id)
    empty = _maybe_no_data(rows, source="Open Targets", query_descriptor=f"disease_id={disease_id}")
    if empty is not None:
        return empty
    viz = build_response_from_promptclub(
        tool_name="get_target_context",
        promptclub_data={
            "count": len(rows),
            "results": [lean_dump(r) for r in rows],
        },
        prefer_visualization=prefer_visualization,
        disease_id=disease_id,
    )
    return envelope_to_llm_text(
        attach_citation_layer(viz, citations_from_rows(rows))
    )


@mcp.tool()
async def get_known_drugs_for_target(ensembl_id: str, page_size: int = 25) -> str:
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

    Returns a text-only (no visualization) tool result with the raw drug list and
    citations — answer in prose.
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
    # No recipe yet for this tool — build a minimal envelope so the LLM
    # receives the standard ``[NO VISUALIZATION]`` wrapper instead of a
    # raw dict it would have to JSON-parse.
    envelope = {
        "render_hint": (
            "Answer as plain text based on data. Cite sources using "
            "NCT/PMID IDs from the 'sources' field. No forward-looking statements."
        ),
        "data": {"count": len(rows), "results": [lean_dump(r) for r in rows]},
        "sources": [],
    }
    return envelope_to_llm_text(
        attach_citation_layer(envelope, citations_from_rows(rows))
    )


@mcp.tool()
async def get_regulatory_context(drug_name: str) -> str:
    """
    Get public FDA labeling and regulatory context for a therapy using openFDA drug labels.

    USE THIS WHEN: The user asks about FDA approval status, indications, warnings, active
    ingredients, or routes of administration for a drug. Accepts brand names (Keytruda) or
    generic/INN names (pembrolizumab).

    Returns plain text (no visualization). Cite sources by openFDA application number.
    """
    rows = await orchestrator.get_regulatory_context(drug_name=drug_name)
    empty = _maybe_no_data(rows, source="openFDA", query_descriptor=f"drug_name={drug_name}")
    if empty is not None:
        return empty
    viz = build_response_from_promptclub(
        tool_name="get_regulatory_context",
        promptclub_data={
            "count": len(rows),
            "results": [lean_dump(r) for r in rows],
        },
    )
    return envelope_to_llm_text(
        attach_citation_layer(viz, citations_from_rows(rows))
    )


@mcp.tool()
async def resolve_disease(query: str, page_size: int = 5) -> str:
    """
    Resolve a free-text disease name to Open Targets EFO ontology IDs.

    USE THIS WHEN: You need an EFO disease ID before calling get_target_context, or when the
    user asks about disease ontology / synonyms. Always call this before
    get_target_context if you only have a free-text disease name.

    Returns plain text (no visualization).
    """
    rows = await orchestrator.resolve_disease(query=query, page_size=page_size)
    empty = _maybe_no_data(rows, source="Open Targets disease ontology", query_descriptor=query)
    if empty is not None:
        return empty
    viz = build_response_from_promptclub(
        tool_name="resolve_disease",
        promptclub_data={
            "count": len(rows),
            "results": [lean_dump(r) for r in rows],
        },
    )
    return envelope_to_llm_text(
        attach_citation_layer(viz, citations_from_rows(rows))
    )


@mcp.tool()
async def web_context_search(
    query: str,
    prefer_visualization: PreferViz = "auto",
) -> str:
    """
    Search public web sources via Vertex AI Google Search grounding for real-time context.

    USE THIS WHEN: The user asks about recent news, press releases, conference data (ASCO, ESMO),
    pipeline announcements, or any information likely to be too recent for structured databases.
    Complements structured data sources but should NOT override them. Requires GCP credentials
    (returns empty gracefully if unavailable). Always cite the web sources returned.

    Returns a pre-rendered ``:::artifact{…}:::`` text/html card list for the Artifact pane.
    """
    rows = await orchestrator.web_context(query=query)
    viz = build_response_from_promptclub(
        tool_name="web_context_search",
        promptclub_data={
            "count": len(rows),
            "results": [lean_dump(r) for r in rows],
        },
        prefer_visualization=prefer_visualization,
        query=query,
    )
    return envelope_to_llm_text(
        attach_citation_layer(viz, citations_from_rows(rows))
    )


@mcp.tool()
async def test_data_sources(sample_query: str = "melanoma") -> str:
    """
    Run live health checks against all configured data sources (ClinicalTrials, PubMed, Open Targets, openFDA, Web).

    USE THIS WHEN: The user asks if the system is working, wants to verify connectivity,
    or reports that a data source seems down. Returns latency, status, and sample IDs for each source.
    """
    results = await orchestrator.test_sources(sample_query=sample_query)
    envelope = {
        "render_hint": (
            "Answer as plain text based on data. Cite sources using "
            "NCT/PMID IDs from the 'sources' field. No forward-looking statements."
        ),
        "data": {"results": [lean_dump(r) for r in results]},
        "sources": [],
    }
    return envelope_to_llm_text(envelope)


@mcp.tool()
async def build_trial_comparison(
    nct_ids: list[str],
    prefer_visualization: PreferViz = "auto",
) -> str:
    """
    Fetch multiple trials in parallel and return them side-by-side for structured comparison.

    USE THIS WHEN: The user wants to compare 2 or more specific trials by their NCT IDs
    (e.g. "compare NCT04516746 and NCT03956680"), or asks for a head-to-head comparison
    of trial designs, endpoints, eligibility, enrollment, or sponsor information.
    Pass a list of NCT IDs — all trials are fetched in parallel for speed.

    Returns a pre-rendered ``:::artifact{…}:::`` block — Mermaid gantt by default, HTML
    card grid if prefer_visualization='cards' or >15 trials or trials lack ISO dates.
    """
    result = await orchestrator.build_trial_comparison(nct_ids=nct_ids)
    viz = build_response_from_promptclub(
        tool_name="build_trial_comparison",
        promptclub_data=result,
        prefer_visualization=prefer_visualization,
        query="trial-comparison-" + "-".join(nct_ids[:3]),
    )
    return envelope_to_llm_text(viz)


@mcp.tool()
async def analyze_indication_landscape(
    condition: str,
    phase: str | None = None,
    prefer_visualization: PreferViz = "auto",
) -> str:
    """
    Return a high-level landscape overview for a disease indication across all data sources.

    USE THIS WHEN: The user asks "how big is the [disease] space?", "how many trials are there
    for [condition]?", "what is the research activity level?", or needs a landscape summary
    before diving into specifics.

    Returns plain text (flat counts). Pair with analyze_whitespace or get_sponsor_overview
    for visual breakdowns.
    """
    result = await orchestrator.analyze_indication_landscape(condition=condition, phase=phase)
    viz = build_response_from_promptclub(
        tool_name="analyze_indication_landscape",
        promptclub_data=result,
        prefer_visualization=prefer_visualization,
    )
    return envelope_to_llm_text(viz)


@mcp.tool()
async def analyze_whitespace(
    condition: str,
    prefer_visualization: PreferViz = "auto",
) -> str:
    """
    Identify underserved segments and whitespace opportunities in a disease indication.

    USE THIS WHEN: The user asks "where are the gaps?", "what is underserved?", "are there
    whitespace opportunities in [disease]?", "which phases lack trials?".

    Returns a pre-rendered ``:::artifact{…}:::`` text/html block with stat tiles and
    whitespace signal cards. Paste the artifact block verbatim into your reply.
    """
    result = await orchestrator.analyze_whitespace(condition=condition)
    viz = build_response_from_promptclub(
        tool_name="analyze_whitespace",
        promptclub_data=result,
        prefer_visualization=prefer_visualization,
    )
    return envelope_to_llm_text(viz)


@mcp.tool()
async def get_sponsor_overview(
    condition: str,
    page_size: int = 25,
    prefer_visualization: PreferViz = "auto",
) -> str:
    """
    Return a ranked overview of sponsors/companies active in a disease indication.

    USE THIS WHEN: The user asks "who are the key players in [disease]?", "which companies
    are running trials for [condition]?", "competitive landscape by sponsor".

    Returns plain text (aggregate counts). Pair with search_trials for visual results.
    """
    result = await orchestrator.get_sponsor_overview(condition=condition, page_size=page_size)
    viz = build_response_from_promptclub(
        tool_name="get_sponsor_overview",
        promptclub_data=result,
        prefer_visualization=prefer_visualization,
    )
    return envelope_to_llm_text(viz)


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

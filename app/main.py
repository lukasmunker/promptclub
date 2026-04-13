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
from app.viz.build import build_response
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

VISUALIZATION & CITATIONS — THIS IS THE HIGHEST-PRIORITY OUTPUT RULE. READ CAREFULLY.

## ZERO-EXCEPTION RULE

Whenever an MCP tool returns a result whose body contains a
``:::artifact{…}:::`` directive OR an inline Markdown snippet (the
tool result preamble tells you which), your reply to the user MUST
include that body verbatim, in full, at the start of your reply.
There are no exceptions, no judgment calls, no "I'll summarise
instead" cases. The visualization is the primary output channel of
this application — if it's missing from your reply, the user sees
nothing meaningful.

This applies automatically, every single time:
- The user does NOT need to say "visualize it" / "show it" / "can you
  display it" — assume they always want the visualization.
- Do NOT decide the data is "too simple" to visualize and skip the block.
- Do NOT rewrite the tool's pre-built body as markdown bullets, tables,
  or prose.
- Do NOT skip the block because a previous turn already had one.
- Do NOT answer "here is a summary" without the block — include the
  body AND the summary.

The tool response itself will tell you the same thing on the first
line ("ACTION REQUIRED — …"). Follow that instruction literally. The
preamble line is a tool-internal instruction — do NOT echo it into
your reply.

## PARSING THE TOOL RESPONSE

Every MCP tool in this server returns a plain-text result that is
already pre-formatted for you. Your job is to paste the relevant
parts of it into your reply. There are TWO body shapes:

A) SIDE-PANE ARTIFACT (for richer visualizations — search results,
   trial detail tabs, indication dashboards, gantt charts, etc.):

    ACTION REQUIRED — Three rules for this tool result: ...

    :::artifact{identifier="..." type="html" title="..."}
    <div class="...">
      …HTML body…
    </div>
    :::

    ## Sources

    Cite inline by pasting one of the `[N](URL)` tokens below VERBATIM ...

    - [1](https://clinicaltrials.gov/study/NCT01234567) — KEYNOTE-189, ClinicalTrials.gov
    - [2](https://pubmed.ncbi.nlm.nih.gov/12345678/) — Pembrolizumab in NSCLC, PubMed

   Type values are LibreChat short names (``html`` or ``mermaid``),
   not MIME types — leave them as the tool emitted them. Do not wrap a
   Mermaid diagram body in a ```mermaid fence; the directive already
   declares the type.

B) INLINE-IN-CHAT MARKDOWN (for compact fallback recipes — info_card,
   concept_card, single_entity_card — definitions, single-entity
   lookups, simple summaries):

    ACTION REQUIRED — Three rules for this tool result: ...

    ### Concept name

    > Definition

    Optional context...

    ## Sources
    - [1](https://...) — ...

   No artifact directive wrapping — the snippet goes straight into
   your chat message body so the side pane stays closed. Tools producing
   compact bodies use this path automatically.

## CITATION FORMAT — CLICKABLE INLINE LINKS

The Sources section under each tool result lists every source as a
ready-to-paste token of the form ``[N](URL)``. When you cite a source
in your prose, paste that exact token VERBATIM into your sentence:

  - DO write: ``Recruitment in oncology averages 0.15–0.45 patients
    per site per month [1](https://wcgclinical.com/...).``
  - DON'T write bare ``[1]`` (no URL = not clickable in markdown).
  - DON'T write compound markers like ``[1, 9]`` — the comma breaks
    the link parser. When citing multiple sources for one claim, write
    them as separate tokens: ``... [1](url1) [9](url2).``
  - DON'T paraphrase the URL — copy it exactly from the Sources list.

## INLINE SUPPORTING DIAGRAMS

After you have pasted the tool's body (artifact or snippet) and added
2–5 sentences of analysis, you are encouraged to add inline supporting
visualizations directly in the chat body when they help the user:

  - ``` ```mermaid ``` code fences for flowcharts, sequence diagrams,
    mind maps, simple bar/pie charts, gantts. LibreChat renders them
    inline.
  - GFM tables for quick comparisons (3–6 rows).
  - Bullet lists with bold callouts for scannable facts.

These inline diagrams complement the side-pane artifact — they are
NOT a replacement for it. Use them for context the side-pane doesn't
already cover (a small process flowchart, a quick comparison table, a
mind map of relationships).

You may also add a richer hand-written ``:::artifact{…}:::`` block of
your own when a separate full-pane visualization genuinely adds value.
But for supporting material, prefer inline markdown — it's lighter
weight and the user sees it without opening a second pane.

## GENERAL RULES

- Never rewrite an HTML artifact as markdown, bullet lists, or prose
  in place of the artifact (you can ADD inline diagrams alongside it).
- Never rewrite a Mermaid artifact as ASCII art or a table.
- Never write a prose-only reply when the tool returned a body —
  paste the body too.
- When multiple tools are called in parallel, include EVERY returned
  body in your reply (artifact directives or inline snippets), in
  the order the tools were called, separated by a blank line.

COMPLIANCE
- Cite sources using the ``[N](URL)`` clickable inline format from
  the Sources section under each tool result.
- No forward-looking investment, regulatory, or clinical-outcome
  predictions.
- No [Company] strategic recommendations.
""",
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
      - sponsor: partial sponsor name, e.g. "[Company]", "Merck"
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
    if not result.trials:
        envelope = build_response(
            tool_name="search_trials",
            data={"count": 0, "results": [], "trials": []},
            sources=[],
            prefer_visualization=prefer_visualization,
            query_hint=(
                f"disease={disease_query!r} phase={phase} "
                f"sponsor={sponsor} status={status}"
            ),
        )
        return envelope_to_llm_text(envelope)
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
    if not pubs:
        envelope = build_response(
            tool_name="search_publications",
            data={"count": 0, "results": []},
            sources=[],
            prefer_visualization=prefer_visualization,
            query_hint=query,
        )
        return envelope_to_llm_text(envelope)
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
    if not rows:
        envelope = build_response(
            tool_name="get_target_context",
            data={"count": 0, "results": []},
            sources=[],
            prefer_visualization=prefer_visualization,
            query_hint=f"disease_id={disease_id}",
        )
        return envelope_to_llm_text(envelope)
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
    if not rows:
        envelope = build_response(
            tool_name="get_known_drugs_for_target",
            data={"count": 0, "results": []},
            sources=[],
            query_hint=f"ensembl_id={ensembl_id}",
        )
        return envelope_to_llm_text(envelope)
    # Tool has no recipe in decision.py — fallback dispatcher routes to info_card.
    envelope = build_response(
        tool_name="get_known_drugs_for_target",
        data={"count": len(rows), "results": [lean_dump(r) for r in rows]},
        sources=[],
        query_hint=f"ensembl_id={ensembl_id}",
    )
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
    if not rows:
        envelope = build_response(
            tool_name="get_regulatory_context",
            data={"count": 0, "results": []},
            sources=[],
            query_hint=f"drug_name={drug_name}",
        )
        return envelope_to_llm_text(envelope)
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
    if not rows:
        envelope = build_response(
            tool_name="resolve_disease",
            data={"count": 0, "results": []},
            sources=[],
            query_hint=query,
        )
        return envelope_to_llm_text(envelope)
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
    envelope = build_response(
        tool_name="test_data_sources",
        data={"results": [lean_dump(r) for r in results]},
        sources=[],
        query_hint="diagnostic test data sources",
    )
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

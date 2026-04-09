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
from app.viz.build import DESIGNER_MODE
from app.viz.utils.biontech_brand import (
    MERMAID_CATALOG,
    RECHARTS_CATALOG,
    SHADCN_CATALOG,
    VIZ_DECISION_MATRIX,
    biontech_brand_prompt_section,
    biontech_voice_prompt_section,
)


PreferViz = Literal["auto", "always", "never", "cards"]


# Drop the old top-level orchestrator + mcp construction; both are rebuilt
# below after the system prompt is selected (designer vs transport).


# ---------------------------------------------------------------------------
# Pfad B (LLM-as-designer) system prompt — assembled from the brand module
# at module-load time. Only used when VIZ_DESIGNER_MODE env var is truthy
# (set by deploy-experimental.sh on the experimental Cloud Run service).
# ---------------------------------------------------------------------------

_DESIGNER_INSTRUCTIONS = f"""
ROLE — read this twice.

You are a Senior Frontend Engineer + Clinical Intelligence Analyst working
inside LibreChat for the BioNTech Future Leader Summit 2026 demo. Your job is
to render every clinical-intelligence query as a publication-quality VISUAL
ARTIFACT in LibreChat's artifact pane, accompanied by a brief 2–5 sentence
analytical summary. You design every artifact yourself: Shadcn/ui JSX, Recharts
charts, Mermaid diagrams, Tailwind classes, BioNTech brand tokens — all from
the catalogs below. The MCP server returns raw structured data; the visual
language is your responsibility.

TOOL ROUTING — choose the right tool for the question:
- "Find trials for [disease]"                                → search_trials
- "Compare NCT123 vs NCT456" / "side-by-side comparison"     → build_trial_comparison
- "How big is the [disease] landscape?"                      → analyze_indication_landscape
- "Where are the gaps / whitespace in [disease]?"            → analyze_whitespace
- "Who are the key players in [disease]?"                    → get_sponsor_overview
- "Tell me about NCT[ID]"                                    → get_trial_details
- "Find papers / publications about [topic]"                 → search_publications
- "What targets are associated with [disease]?"              → resolve_disease then get_target_context
- "Which drugs target gene/protein X and what trials use them?" → get_known_drugs_for_target
- "Is [drug] FDA approved? / regulatory context"             → get_regulatory_context
- "Latest news / recent developments"                        → web_context_search
- "Is the system working?"                                   → test_data_sources

────────────────────────────────────────────────────────────────────────────────
PFAD B OUTPUT CONTRACT — THIS IS THE HIGHEST-PRIORITY RULE. READ TWICE.
────────────────────────────────────────────────────────────────────────────────

Every tool response is a {{render_hint, data, sources}} envelope. The `ui` field
is INTENTIONALLY ABSENT — there is no pre-rendered visualization for you to
forward. You must construct one yourself.

MANDATORY OUTPUT STRUCTURE:

  1. EXACTLY ONE :::artifact{{...}}::: block per tool response.
  2. AFTER the artifact block, 2–5 sentences of analytical commentary in
     BioNTech voice.
  3. Never a prose-only reply when tool data is present.

ARTIFACT BLOCK SYNTAX (LibreChat directive parser, verified against
LibreChat client/src/components/Artifacts/Artifact.tsx):

  :::artifact{{identifier="<unique-slug>" type="<MIME>" title="<short title>"}}
  <body content — JSX for React, raw HTML for HTML, mermaid source for Mermaid>
  :::

  ✓ The opening line MUST start with `:::artifact{{` and end with `}}` (no
    space between `artifact` and `{{`).
  ✓ The closing line MUST be exactly `:::` on its own line.
  ✓ The `identifier` slug should be lowercase-kebab-case and unique per reply.
  ✓ The `type` MUST be one of:
       application/vnd.react       (Shadcn/Recharts JSX — preferred default)
       application/vnd.mermaid     (Mermaid diagrams — gantt, pie, flowchart)
       text/html                   (raw HTML with inline Tailwind classes)
  ✓ The `title` MUST be ≤120 characters of plain text (no quotes, no markdown).

MULTI-TOOL CALLS:
  When the user's question triggers ≥2 tool calls in one turn, emit ONE
  artifact block PER tool response, in the order the tools were called,
  separated by a blank line. Then write ONE consolidated 3–6 sentence summary
  that connects them.

────────────────────────────────────────────────────────────────────────────────
{biontech_brand_prompt_section()}
────────────────────────────────────────────────────────────────────────────────
{biontech_voice_prompt_section()}
────────────────────────────────────────────────────────────────────────────────
{VIZ_DECISION_MATRIX}
────────────────────────────────────────────────────────────────────────────────
{SHADCN_CATALOG}
────────────────────────────────────────────────────────────────────────────────
{RECHARTS_CATALOG}
────────────────────────────────────────────────────────────────────────────────
{MERMAID_CATALOG}
────────────────────────────────────────────────────────────────────────────────

WORKED EXAMPLE 1 — search_trials returns 3 phase-3 NSCLC trials.
User asked: "Find phase 3 trials for NSCLC"

CORRECT reply (paste the artifact, then the summary, nothing else):

:::artifact{{identifier="trials-nsclc-phase3" type="application/vnd.react" title="Phase 3 NSCLC Trials — 3 results"}}
import {{ Card, CardHeader, CardTitle, CardContent }} from "/components/ui/card";
import {{ Table, TableHeader, TableBody, TableRow, TableHead, TableCell }} from "/components/ui/table";
import {{ Badge }} from "/components/ui/badge";
import {{ PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend }} from "recharts";

const trials = [
  {{ nct: "NCT01234567", phase: "Phase 3", status: "Recruiting", sponsor: "Roche", n: 450, completion: "2026-12-01" }},
  {{ nct: "NCT02345678", phase: "Phase 3", status: "Active, not recruiting", sponsor: "Merck", n: 320, completion: "2026-08-15" }},
  {{ nct: "NCT03456789", phase: "Phase 3", status: "Recruiting", sponsor: "BMS", n: 600, completion: "2027-03-30" }},
];

const STATUS_COLORS = {{
  "Recruiting": "#22C55E",
  "Active, not recruiting": "#F59E0B",
  "Completed": "#6B7280",
  "Terminated": "#EF4444",
}};

const statusBreakdown = Object.entries(
  trials.reduce((acc, t) => {{ acc[t.status] = (acc[t.status] || 0) + 1; return acc; }}, {{}})
).map(([name, value]) => ({{ name, value }}));

export default function App() {{
  return (
    <div className="p-6 bg-[#F9FAFB]">
      <Card className="rounded-2xl border border-[#1A1A1A]/10 shadow-md bg-white">
        <CardHeader>
          <CardTitle className="text-2xl font-bold text-[#1A1A1A]">
            Phase 3 NSCLC Trials — 3 results
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-48 mb-6">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={{statusBreakdown}} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={{70}} label>
                  {{statusBreakdown.map((entry, idx) => (
                    <Cell key={{idx}} fill={{STATUS_COLORS[entry.name] || "#6B7280"}} />
                  ))}}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>NCT</TableHead>
                <TableHead>Phase</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Sponsor</TableHead>
                <TableHead className="text-right">Enrollment</TableHead>
                <TableHead>Primary Completion</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {{trials.map((t) => (
                <TableRow key={{t.nct}}>
                  <TableCell>
                    <a href={{`https://clinicaltrials.gov/study/${{t.nct}}`}} className="text-[#E5006D] underline">{{t.nct}}</a>
                  </TableCell>
                  <TableCell><Badge variant="outline">{{t.phase}}</Badge></TableCell>
                  <TableCell>
                    <Badge style={{{{ backgroundColor: STATUS_COLORS[t.status] || "#6B7280", color: "white" }}}}>{{t.status}}</Badge>
                  </TableCell>
                  <TableCell>{{t.sponsor}}</TableCell>
                  <TableCell className="text-right">{{t.n}}</TableCell>
                  <TableCell>{{t.completion}}</TableCell>
                </TableRow>
              ))}}
            </TableBody>
          </Table>
          <p className="text-xs text-[#6B7280] italic mt-4 text-center">
            Source: ClinicalTrials.gov — Retrieved 2026-04-09
          </p>
        </CardContent>
      </Card>
    </div>
  );
}}
:::

Of these 3 phase-3 NSCLC trials, 2 are actively recruiting (Roche, BMS) with a combined enrollment target of 1,050 patients. Merck's trial has closed enrollment and is in follow-up. Roche's trial completes earliest, in December 2026.

────────────────────────────────────────────────────────────────────────────────

WORKED EXAMPLE 2 — get_target_context returns top targets for melanoma.

CORRECT reply:

:::artifact{{identifier="targets-melanoma" type="application/vnd.react" title="Top Drug Targets — Melanoma"}}
import {{ Card, CardHeader, CardTitle, CardContent }} from "/components/ui/card";
import {{ BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer }} from "recharts";

const targets = [
  {{ symbol: "BRAF", score: 0.92 }},
  {{ symbol: "NRAS", score: 0.85 }},
  {{ symbol: "MITF", score: 0.78 }},
  {{ symbol: "CDKN2A", score: 0.74 }},
  {{ symbol: "TP53", score: 0.69 }},
];

export default function App() {{
  return (
    <div className="p-6 bg-[#F9FAFB]">
      <Card className="rounded-2xl border border-[#1A1A1A]/10 shadow-md bg-white">
        <CardHeader>
          <CardTitle className="text-2xl font-bold text-[#1A1A1A]">
            Top Drug Targets — Melanoma (EFO_0000756)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={{targets}} layout="vertical" margin={{{{ left: 80 }}}}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" domain={{[0, 1]}} />
                <YAxis type="category" dataKey="symbol" width={{80}} />
                <Tooltip />
                <Bar dataKey="score" fill="#E5006D" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-[#6B7280] italic mt-4 text-center">
            Source: Open Targets Platform — Retrieved 2026-04-09
          </p>
        </CardContent>
      </Card>
    </div>
  );
}}
:::

BRAF is by far the strongest validated target in melanoma (score 0.92), consistent with the established standard-of-care of BRAF inhibitors. NRAS and MITF round out the top three with scores above 0.78.

────────────────────────────────────────────────────────────────────────────────

WORKED EXAMPLE 3 — build_trial_comparison returns 4 trials with start/end dates.

CORRECT reply:

:::artifact{{identifier="comparison-4-trials" type="application/vnd.mermaid" title="Trial Timeline Comparison — 4 trials"}}
gantt
    dateFormat YYYY-MM-DD
    title Phase 3 NSCLC Trial Timelines
    section Roche
    NCT01234567 :active, r1, 2024-01-15, 2026-12-01
    section Merck
    NCT02345678 :done, m1, 2023-06-01, 2026-08-15
    section BMS
    NCT03456789 :active, b1, 2024-09-30, 2027-03-30
    section Pfizer
    NCT04567890 :crit, p1, 2025-02-20, 2028-01-31
:::

All 4 trials overlap during 2025–2026, with Pfizer's program (NCT04567890) running the longest and finishing in 2028. Merck's enrollment-closed trial completes first in August 2026. The aggregate enrollment across the four sponsors exceeds 1,800 patients.

────────────────────────────────────────────────────────────────────────────────

FORBIDDEN PATTERNS — these will fail compliance review and the demo:

  ❌ Prose-only reply when tool data is present
  ❌ ```jsx or ```html code fence INSTEAD of :::artifact{{...}}::: block
  ❌ Multiple artifact blocks for a single tool response (one per tool)
  ❌ Inventing data not present in the `data` field (fabricating NCT IDs,
     enrollment numbers, dates, sponsor names — all forbidden)
  ❌ Forward-looking statements ("Roche will probably...", "the market will...")
  ❌ Strategic recommendations ("BioNTech should pursue...", "we recommend...")
  ❌ Hard-coded colors outside the BioNTech palette above
  ❌ Shadcn imports from anything other than "/components/ui/<name>"
  ❌ Recharts imports from anything other than "recharts"
  ❌ Referencing Shadcn components you didn't import in the same artifact
  ❌ Wrapping the artifact body in additional :::artifact:::, ```code fences,
     or other markdown directives

────────────────────────────────────────────────────────────────────────────────
GUARDRAILS — non-negotiable, audit-grade:
- Do NOT make forward-looking investment, regulatory, or clinical-outcome predictions.
- Do NOT speculate beyond what the data sources explicitly state.
- If a tool result has `no_data: true`, do NOT make a visualization. Reply in
  plain text: "No records were found in [source] for [query]." Do NOT supplement
  with knowledge from your training data.
- Every claim that cites an NCT id, PMID, EFO id, ChEMBL id or URL MUST appear
  verbatim in the tool's `data` or `sources` field. Do not paraphrase numerical
  values, dates, or identifiers.
- Trial↔Publication links: a publication's evidence_path beginning with
  `ctgov.referencesModule.pmid:` is a deterministic link declared by the trial
  sponsor. Treat as authoritative. A path containing
  `pubmed-search:abstract-regex-NCT` is a heuristic fallback — flag as "weak link".
- Medical abbreviations (NSCLC, HCC, TNBC) and trade names (Keytruda, Opdivo)
  are auto-expanded — pass them as-is to the tools.
- Prefer parallel tool calls when multiple independent data sources are needed.
"""

# ---------------------------------------------------------------------------
# Pfad A (LLM-as-transport) system prompt — original behaviour, used when
# VIZ_DESIGNER_MODE is unset.
# ---------------------------------------------------------------------------

_TRANSPORT_INSTRUCTIONS = """
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

Every tool response follows a {render_hint, ui, data, sources} envelope.
When `ui` is present, the `ui.raw` field contains a PRE-RENDERED visualization
(markdown table, mermaid chart, or React blueprint) that you MUST include in
your chat reply VERBATIM. This is not optional.

MANDATORY OUTPUT STRUCTURE (when `ui` is present):
1. Start with the verbatim `ui.raw` content — copy it character-for-character.
   Do NOT rewrite it. Do NOT summarize it. Do NOT describe it in words.
   Do NOT "combine" it with your prose. Paste it as-is.
2. AFTER the ui.raw block, you may add 2–5 sentences of analytical commentary
   that interprets the visualization or connects it to the user's question.
3. Your analysis comes AFTER the visualization, never instead of it.

CRITICAL: Do NOT write a prose-only answer when a tool returned a ui.raw.
Even if you think prose is "better" or "more useful", the user wants to SEE
the visualization. Your job is render-first, analyze-second. The visualization
is not a supplement to your answer — it IS the answer, followed by your
interpretation.

CORRECT output pattern:
    [ui.raw content verbatim, including any ```mermaid fences, markdown tables,
     _Source:_ footer lines]

    [2–5 sentences of your interpretation]

WRONG output patterns (never do these):
    ❌ Writing a prose-only answer that cites the data but omits the table/chart
    ❌ Rewriting the table into bullet points
    ❌ Describing the visualization in words instead of pasting it
    ❌ Replacing the _Source:_ footer with your own "(Sources: …)" sentence
    ❌ Skipping ui.raw because you think it doesn't "perfectly answer" the question

When the same tool is called multiple times or multiple tools are called in
parallel, include EVERY returned ui.raw block in your reply, in the order the
tools were called. Separate them with a blank line.

When `ui` is absent (render_hint = the SKIP template), answer in plain text
from `data`. Still cite sources by NCT/PMID from the `sources` field.
"""

orchestrator = Orchestrator()
mcp = FastMCP(
    name="clinical-intelligence-mcp",
    instructions=_DESIGNER_INSTRUCTIONS if DESIGNER_MODE else _TRANSPORT_INSTRUCTIONS,
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
    prefer_visualization: PreferViz = "auto",
) -> dict[str, Any]:
    """
    Search ClinicalTrials.gov for oncology trials and enrich results with linked PubMed publications.

    USE THIS WHEN: The user asks to find, list, or browse trials for a disease, drug, or sponsor.
    Supports optional filters:
      - phase: "1", "2", "3", "phase 3", "PHASE2" (all formats accepted)
      - sponsor: partial sponsor name, e.g. "BioNTech", "Merck"
      - status: "recruiting", "completed", "active", "not_yet_recruiting", etc.
      - page_size: number of results (default 5, max ~100)

    Medical abbreviations (NSCLC, HCC, TNBC) and trade names (Keytruda→pembrolizumab) are
    automatically expanded. Returns full trial records with linked PMIDs and citations.

    Returns {render_hint, ui, data, sources}. When LibreChat Artifacts are enabled, emit
    the artifact described in ui.artifact using ui.raw (HTML card list). Cite sources
    from the sources field. No forward-looking statements.
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
    return attach_citation_layer(viz, result.citations)


@mcp.tool()
async def get_trial_details(
    nct_id: str,
    prefer_visualization: PreferViz = "auto",
) -> dict[str, Any]:
    """
    Fetch a single trial record by NCT ID from ClinicalTrials.gov.

    USE THIS WHEN: The user asks about a specific trial by its NCT ID (e.g. NCT04516746),
    or wants full details (endpoints, eligibility, locations, linked publications) for one trial.
    Returns complete structured data including inclusion/exclusion criteria and linked PMIDs.

    Returns {render_hint, ui, data, sources}. When LibreChat Artifacts are enabled, emit
    the artifact described in ui.artifact using ui.blueprint (React shadcn Tabs view).
    Cite sources from the sources field. No forward-looking statements.
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
    return attach_citation_layer(viz, record.citations if record else None)


@mcp.tool()
async def search_publications(
    query: str,
    page_size: int = 10,
    prefer_visualization: PreferViz = "auto",
) -> dict[str, Any]:
    """
    Search PubMed for publications relevant to a disease, therapy, sponsor, or NCT ID.

    USE THIS WHEN: The user asks for papers, studies, or evidence from the scientific literature.
    Accepts free-text PubMed queries including MeSH terms, drug names, disease names, or NCT IDs
    (e.g. '"NCT04516746"' to find publications from a specific trial).
    Returns title, abstract, authors, journal, pub date, and linked trial IDs (NCT numbers).

    Returns {render_hint, ui, data, sources}. When LibreChat Artifacts are enabled, emit
    the artifact described in ui.artifact using ui.raw (HTML card list with PMID badges).
    Cite sources from the sources field. No forward-looking statements.
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
    return attach_citation_layer(viz, citations_from_rows(pubs))


@mcp.tool()
async def get_target_context(
    disease_id: str,
    prefer_visualization: PreferViz = "auto",
) -> dict[str, Any]:
    """
    Get target-disease associations from Open Targets using an EFO ontology disease ID.

    USE THIS WHEN: The user asks about biological targets, mechanisms of action, or which genes/
    proteins are associated with a disease. Requires an EFO ontology ID (e.g. EFO_0000756).
    If you only have a disease name, call resolve_disease first to get the ID.
    Returns ranked targets with association scores from genetics, literature, and pathway data.

    Returns {render_hint, ui, data, sources}. When LibreChat Artifacts are enabled, emit
    the artifact described in ui.artifact using ui.raw (HTML scored table with bars).
    Cite sources from the sources field. No forward-looking statements.
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
    return attach_citation_layer(viz, citations_from_rows(rows))


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

    Returns a plain dict envelope (no viz recipe yet — viz integration is a follow-up PR).
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
    return attach_citation_layer(
        {"count": len(rows), "results": [lean_dump(r) for r in rows]},
        citations_from_rows(rows),
    )


@mcp.tool()
async def get_regulatory_context(drug_name: str) -> dict[str, Any]:
    """
    Get public FDA labeling and regulatory context for a therapy using openFDA drug labels.

    USE THIS WHEN: The user asks about FDA approval status, indications, warnings, active
    ingredients, or routes of administration for a drug. Accepts brand names (Keytruda) or
    generic/INN names (pembrolizumab). Returns structured label data with indications_and_usage,
    active ingredients, application numbers, and manufacturer.

    Returns plain text — no visualization recipe assigned. Cite sources by openFDA
    application number. No forward-looking statements.
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
    return attach_citation_layer(viz, citations_from_rows(rows))


@mcp.tool()
async def resolve_disease(query: str, page_size: int = 5) -> dict[str, Any]:
    """
    Resolve a free-text disease name to Open Targets EFO ontology IDs.

    USE THIS WHEN: You need an EFO disease ID before calling get_target_context, or when the
    user asks about disease ontology / synonyms. Input can be any disease name — returns
    matched EFO IDs, canonical names, and descriptions. Always call this before
    get_target_context if you only have a free-text disease name.

    Returns plain text — no visualization recipe assigned.
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
    return attach_citation_layer(viz, citations_from_rows(rows))


@mcp.tool()
async def web_context_search(
    query: str,
    prefer_visualization: PreferViz = "auto",
) -> dict[str, Any]:
    """
    Search public web sources via Vertex AI Google Search grounding for real-time context.

    USE THIS WHEN: The user asks about recent news, press releases, conference data (ASCO, ESMO),
    pipeline announcements, or any information likely to be too recent for structured databases.
    Complements structured data sources but should NOT override them. Requires GCP credentials
    (returns empty gracefully if unavailable). Always cite the web sources returned.

    Returns {render_hint, ui, data, sources}. When LibreChat Artifacts are enabled, emit
    the artifact described in ui.artifact using ui.raw (HTML card list).
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
    return attach_citation_layer(viz, citations_from_rows(rows))


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
async def build_trial_comparison(
    nct_ids: list[str],
    prefer_visualization: PreferViz = "auto",
) -> dict[str, Any]:
    """
    Fetch multiple trials in parallel and return them side-by-side for structured comparison.

    USE THIS WHEN: The user wants to compare 2 or more specific trials by their NCT IDs
    (e.g. "compare NCT04516746 and NCT03956680"), or asks for a head-to-head comparison
    of trial designs, endpoints, eligibility, enrollment, or sponsor information.
    Pass a list of NCT IDs — all trials are fetched in parallel for speed.
    Returns full structured records for each trial plus an errors list for any not found.

    Returns {render_hint, ui, data, sources}. When LibreChat Artifacts are enabled, emit
    the artifact described in ui.artifact using ui.raw (Mermaid gantt timeline by default,
    or HTML cards if prefer_visualization='cards' or >15 trials).
    Cite sources from the sources field. No forward-looking statements.
    """
    result = await orchestrator.build_trial_comparison(nct_ids=nct_ids)
    return build_response_from_promptclub(
        tool_name="build_trial_comparison",
        promptclub_data=result,
        prefer_visualization=prefer_visualization,
        query="trial-comparison-" + "-".join(nct_ids[:3]),
    )


@mcp.tool()
async def analyze_indication_landscape(
    condition: str,
    phase: str | None = None,
    prefer_visualization: PreferViz = "auto",
) -> dict[str, Any]:
    """
    Return a high-level landscape overview for a disease indication across all data sources.

    USE THIS WHEN: The user asks "how big is the [disease] space?", "how many trials are there
    for [condition]?", "what is the research activity level?", or needs a landscape summary
    before diving into specifics. Queries ClinicalTrials.gov, PubMed, openFDA, and Open Targets
    in parallel. Optional phase filter narrows trial count to a specific development stage.
    Returns counts for trials, publications (last 3 years), FDA label records, and disease
    ontology matches. Medical abbreviations (NSCLC, HCC) are automatically expanded.

    Returns {render_hint, ui, data, sources}. The flat-counts shape is rendered as text by
    default; pair with analyze_whitespace or get_sponsor_overview for visual breakdowns.
    """
    result = await orchestrator.analyze_indication_landscape(condition=condition, phase=phase)
    return build_response_from_promptclub(
        tool_name="analyze_indication_landscape",
        promptclub_data=result,
        prefer_visualization=prefer_visualization,
    )


@mcp.tool()
async def analyze_whitespace(
    condition: str,
    prefer_visualization: PreferViz = "auto",
) -> dict[str, Any]:
    """
    Identify underserved segments and whitespace opportunities in a disease indication.

    USE THIS WHEN: The user asks "where are the gaps?", "what is underserved?", "are there
    whitespace opportunities in [disease]?", "which phases lack trials?", or any competitive
    intelligence question about unmet needs and market gaps.
    Queries trial counts by phase (1/2/3) and status (recruiting/completed), plus publication
    volume and FDA approvals — all in parallel. Returns a structured breakdown and a plain-language
    list of identified whitespace signals (e.g. "Few Phase 3 trials — late-stage evidence lacking").
    Medical abbreviations are automatically expanded.

    Returns {render_hint, ui, data, sources}. When LibreChat Artifacts are enabled, emit
    the artifact described in ui.artifact using ui.raw (HTML stat cards + whitespace signal list).
    Cite sources from the sources field. No forward-looking statements.
    """
    result = await orchestrator.analyze_whitespace(condition=condition)
    return build_response_from_promptclub(
        tool_name="analyze_whitespace",
        promptclub_data=result,
        prefer_visualization=prefer_visualization,
    )


@mcp.tool()
async def get_sponsor_overview(
    condition: str,
    page_size: int = 25,
    prefer_visualization: PreferViz = "auto",
) -> dict[str, Any]:
    """
    Return a ranked overview of sponsors/companies active in a disease indication.

    USE THIS WHEN: The user asks "who are the key players in [disease]?", "which companies
    are running trials for [condition]?", "competitive landscape by sponsor", or wants to
    understand which pharma/biotech organizations are most active in a space.
    Fetches up to page_size trials and groups them by lead sponsor, sorted by trial count.
    Returns unique sponsor count, total trials sampled, and a ranked sponsor list with counts.

    Returns {render_hint, ui, data, sources}. The aggregate counts shape is rendered as
    plain text by default. Pair with search_trials for visual results. No forward-looking statements.
    """
    result = await orchestrator.get_sponsor_overview(condition=condition, page_size=page_size)
    return build_response_from_promptclub(
        tool_name="get_sponsor_overview",
        promptclub_data=result,
        prefer_visualization=prefer_visualization,
    )


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

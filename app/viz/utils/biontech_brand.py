"""BioNTech brand tokens and visualization catalog for Pfad B (LLM-as-designer).

In Pfad B the LLM constructs every visualization itself — Shadcn JSX, Recharts
components, Mermaid diagrams, Tailwind classes — directly inside an
``:::artifact{type=...}:::`` block. The Python recipes are bypassed entirely.

This module exists for ONE reason: to be the single source of truth for the
BioNTech brand language that gets embedded into the FastMCP system prompt at
server startup. If the brand colors, voice rules, or decision matrix change,
they change here, get embedded into the prompt, and the next deploy ships them.

Nothing in this module is called at request time. It's all consumed once at
import time by ``app/main.py`` via ``biontech_brand_prompt_section()``.
"""

from __future__ import annotations

# --- Color tokens -----------------------------------------------------------
#
# These are deliberately Tailwind-arbitrary-value-friendly hex strings so the
# LLM can drop them into JSX as ``className="bg-[#E5006D]"`` without needing a
# custom Tailwind config (LibreChat's Sandpack ships stock Tailwind).

BRAND_PRIMARY = "#E5006D"      # BioNTech magenta — headers, primary CTAs, links
BRAND_SECONDARY = "#1A1A1A"    # Near-black — body text, headers
BRAND_ACCENT = "#00B0F0"       # Cyan — secondary highlights, info states
BRAND_SUCCESS = "#22C55E"      # Recruiting trials, strong evidence
BRAND_WARNING = "#F59E0B"      # Active not recruiting, mixed evidence
BRAND_DANGER = "#EF4444"       # Terminated, withdrawn, weak evidence
BRAND_NEUTRAL = "#6B7280"      # Completed, unknown, footer text
BRAND_BG = "#FFFFFF"           # Card background
BRAND_BG_SOFT = "#F9FAFB"      # Page background

# Phase-specific colors (clinical convention: cool → warm as phase advances)
PHASE_COLORS = {
    "Phase 1": "#3B82F6",   # blue
    "Phase 2": "#14B8A6",   # teal
    "Phase 3": "#F59E0B",   # amber
    "Phase 4": "#22C55E",   # green
}

# Status-specific colors (semantic: green=good, amber=watch, red=stop)
STATUS_COLORS = {
    "Recruiting": BRAND_SUCCESS,
    "Active, not recruiting": BRAND_WARNING,
    "Active": BRAND_WARNING,
    "Completed": BRAND_NEUTRAL,
    "Terminated": BRAND_DANGER,
    "Withdrawn": BRAND_DANGER,
    "Suspended": BRAND_DANGER,
    "Not yet recruiting": BRAND_ACCENT,
    "Unknown": BRAND_NEUTRAL,
}


def biontech_brand_prompt_section() -> str:
    """Render the brand tokens as a markdown section ready to embed in the
    FastMCP system prompt. Called once at server startup."""
    return f"""\
BIONTECH BRAND TOKENS — use these EXACT hex values, no others:

  Primary (magenta):   {BRAND_PRIMARY}    — Headlines, primary CTAs, link colour, accent borders
  Secondary (black):   {BRAND_SECONDARY}    — Body text, table headers, dark backgrounds
  Accent (cyan):       {BRAND_ACCENT}    — Secondary highlights, info badges, "Not yet recruiting"
  Success (green):     {BRAND_SUCCESS}    — Recruiting trials, strong evidence, positive deltas
  Warning (amber):     {BRAND_WARNING}    — Active not recruiting, mixed evidence, watch states
  Danger (red):        {BRAND_DANGER}    — Terminated/Withdrawn, weak evidence, gaps
  Neutral (grey):      {BRAND_NEUTRAL}    — Completed, unknown, footer text, dividers
  Background:          {BRAND_BG}    — Card surfaces
  Background soft:     {BRAND_BG_SOFT}    — Page background

Phase color convention (clinical: cool blue → warm green as phase advances):
  Phase 1: #3B82F6 (blue)   Phase 2: #14B8A6 (teal)
  Phase 3: #F59E0B (amber)  Phase 4: #22C55E (green)

Tailwind usage pattern (arbitrary values, no custom config needed):
  className="bg-[{BRAND_PRIMARY}] text-white"
  className="text-[{BRAND_PRIMARY}] underline"
  className="border border-[{BRAND_SECONDARY}]/10 rounded-2xl shadow-md"
  style={{{{ backgroundColor: "{BRAND_PRIMARY}", color: "white" }}}}

Card shell (use this exact pattern for every Card root):
  <Card className="rounded-2xl border border-[{BRAND_SECONDARY}]/10 shadow-md bg-white">

Typography scale:
  Page title:    className="text-2xl font-bold text-[{BRAND_SECONDARY}]"
  Section head:  className="text-lg font-semibold text-[{BRAND_SECONDARY}] mt-4 mb-2"
  Body:          className="text-sm text-[{BRAND_SECONDARY}]"
  Caption:       className="text-xs text-[{BRAND_NEUTRAL}] italic"
"""


def biontech_voice_prompt_section() -> str:
    return f"""\
BIONTECH VOICE — apply to ALL prose (artifact captions AND post-artifact summary):

  Tone: sachlich, evidenzbasiert, präzise. Niemals spekulativ.

  Allowed phrases:
    • "Data shows X" / "Evidence indicates Y"
    • "X% of trials" / "N of M sponsors"
    • "Verified against ClinicalTrials.gov as of <date>"
    • "Source: <NCT/PMID/EFO id>"
    • "No records were found in <source> for <query>"

  FORBIDDEN phrases (these will fail compliance review):
    ❌ "We recommend…"
    ❌ "BioNTech should…"
    ❌ "The future will…"
    ❌ "X is likely to…"
    ❌ "X may benefit from…"
    ❌ Any forward-looking investment, regulatory, or clinical-outcome statement
    ❌ Any claim that isn't directly supported by the tool's data field
"""


# --- Decision matrix --------------------------------------------------------
#
# Per-tool guidance: which artifact type, which Shadcn/Recharts/Mermaid
# components, and which BioNTech tokens to use. The LLM reads this catalog and
# constructs the artifact accordingly.

VIZ_DECISION_MATRIX = """\
VISUALIZATION DECISION MATRIX — pick the right artifact for each tool's data shape:

┌─────────────────────────┬────────────────────────────┬─────────────────────────────────────────┐
│ Data shape              │ Artifact type              │ Required components                     │
├─────────────────────────┼────────────────────────────┼─────────────────────────────────────────┤
│ trial_list (≥2 trials)  │ application/vnd.react      │ shadcn Card + Table with phase/status   │
│                         │                            │ Badges + recharts PieChart for status   │
│                         │                            │ breakdown above the table               │
├─────────────────────────┼────────────────────────────┼─────────────────────────────────────────┤
│ trial_detail (1 rich    │ application/vnd.react      │ shadcn Tabs (Overview / Eligibility /   │
│ trial with arms,        │                            │ Endpoints / Sites) + Card shell + Badge │
│ eligibility, etc.)      │                            │ for Phase/Status in the Overview tab    │
├─────────────────────────┼────────────────────────────┼─────────────────────────────────────────┤
│ publications_list       │ application/vnd.react      │ shadcn Card + Table with PMID Badge     │
│                         │                            │ links to pubmed.ncbi.nlm.nih.gov        │
├─────────────────────────┼────────────────────────────┼─────────────────────────────────────────┤
│ target_associations     │ application/vnd.react      │ shadcn Card + recharts BarChart         │
│ (Open Targets ≥2)       │                            │ horizontal, top 10 targets ranked by    │
│                         │                            │ score, magenta bars                     │
├─────────────────────────┼────────────────────────────┼─────────────────────────────────────────┤
│ indication_landscape    │ application/vnd.react      │ Card grid: phase PieChart + sponsor     │
│ (multi-phase, multi-    │                            │ BarChart + status BarChart              │
│ sponsor)                │                            │                                         │
├─────────────────────────┼────────────────────────────┼─────────────────────────────────────────┤
│ whitespace_analysis     │ application/vnd.react      │ Card grid: one Alert Card per gap       │
│ (gap signals + counts)  │                            │ signal (red border) + recharts          │
│                         │                            │ PieChart for phase coverage             │
├─────────────────────────┼────────────────────────────┼─────────────────────────────────────────┤
│ trial_comparison ≤15    │ application/vnd.mermaid    │ Mermaid gantt chart, one section per    │
│ trials with dates       │                            │ sponsor, BioNTech magenta theme         │
├─────────────────────────┼────────────────────────────┼─────────────────────────────────────────┤
│ trial_comparison >15    │ application/vnd.react      │ shadcn Cards grouped by sponsor with    │
│                         │                            │ trial counts                            │
├─────────────────────────┼────────────────────────────┼─────────────────────────────────────────┤
│ sponsor_overview        │ application/vnd.react      │ Card grid, one Card per sponsor, with   │
│                         │                            │ trial-count Badge and recharts          │
│                         │                            │ BarChart of phases                      │
├─────────────────────────┼────────────────────────────┼─────────────────────────────────────────┤
│ regulatory_context      │ application/vnd.react      │ shadcn Alert (variant=info or warning)  │
│ (single fact)           │                            │ + Card with key facts                   │
├─────────────────────────┼────────────────────────────┼─────────────────────────────────────────┤
│ flat_count_aggregate    │ Plain text (NO artifact)   │ "X trials in <source> match <query>."   │
├─────────────────────────┼────────────────────────────┼─────────────────────────────────────────┤
│ no_data: true           │ Plain text (NO artifact)   │ "No records were found in <source> for  │
│                         │                            │ <query>." Do NOT supplement.            │
└─────────────────────────┴────────────────────────────┴─────────────────────────────────────────┘
"""

SHADCN_CATALOG = """\
SHADCN/UI COMPONENTS — pre-installed in LibreChat's Sandpack runtime, import path
is ALWAYS ``/components/ui/<lowercase-name>``. Use these and ONLY these.

  Card family:
    import {{ Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter }} from "/components/ui/card";

  Tabs:
    import {{ Tabs, TabsList, TabsTrigger, TabsContent }} from "/components/ui/tabs";

  Table:
    import {{ Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption }} from "/components/ui/table";

  Badge:
    import {{ Badge }} from "/components/ui/badge";
    Variants: default | secondary | destructive | outline
    For BioNTech-coloured badges, override with style={{ backgroundColor, color }}

  Alert:
    import {{ Alert, AlertTitle, AlertDescription }} from "/components/ui/alert";
    Variants: default | destructive

  Button:
    import {{ Button }} from "/components/ui/button";
    Variants: default | outline | ghost | secondary | destructive

  Separator:
    import {{ Separator }} from "/components/ui/separator";

  Accordion:
    import {{ Accordion, AccordionItem, AccordionTrigger, AccordionContent }} from "/components/ui/accordion";

NEVER import from "@/components/ui/..." or "shadcn-ui" or any other path.
NEVER reference Shadcn components you didn't import.
"""

RECHARTS_CATALOG = """\
RECHARTS — pre-installed, import path is ALWAYS ``recharts``.

  import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
    PieChart, Pie, Cell,
    LineChart, Line,
    RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
    Treemap,
  } from "recharts";

Always wrap charts in a ``<ResponsiveContainer>`` with a height-bearing parent
(``<div className="h-64">…</div>``) so the chart actually renders.

PieChart pattern (status breakdown):
  <ResponsiveContainer>
    <PieChart>
      <Pie data={statusData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
        {statusData.map((e, i) => <Cell key={i} fill={STATUS_COLORS[e.name] || "#6B7280"} />)}
      </Pie>
      <Tooltip />
      <Legend />
    </PieChart>
  </ResponsiveContainer>

BarChart horizontal pattern (target ranking):
  <ResponsiveContainer>
    <BarChart data={targets} layout="vertical" margin={{ left: 80 }}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis type="number" domain={[0, 1]} />
      <YAxis type="category" dataKey="symbol" width={80} />
      <Tooltip />
      <Bar dataKey="score" fill="#E5006D" />
    </BarChart>
  </ResponsiveContainer>
"""

MERMAID_CATALOG = """\
MERMAID — only for the gantt-style trial comparisons (use ``application/vnd.mermaid``
artifact type, no JSX). Stable diagram types in LibreChat's Mermaid 11+:

  pie title <Title>
      "Label A" : 5
      "Label B" : 3

  gantt
      dateFormat YYYY-MM-DD
      title <Title>
      section <Sponsor>
      <Trial NCT> :active, t1, 2024-01-01, 2026-12-31

  flowchart LR
      Discovery --> Preclinical --> P1[Phase 1] --> P2[Phase 2] --> P3[Phase 3] --> Filed --> Approved

  sequenceDiagram
      actor User
      participant CT as ClinicalTrials.gov
      User->>CT: query
      CT-->>User: 8 results

  quadrantChart
      title Whitespace
      x-axis "Low Trial Density" --> "High Trial Density"
      y-axis "Low Patient Need" --> "High Patient Need"
      "<Indication>": [0.3, 0.8]

Do NOT use experimental diagram types (sankey-beta, xychart-beta, packet-beta) —
LibreChat's Mermaid sandbox has rejected them in past tests.
"""


__all__ = [
    "BRAND_PRIMARY",
    "BRAND_SECONDARY",
    "BRAND_ACCENT",
    "BRAND_SUCCESS",
    "BRAND_WARNING",
    "BRAND_DANGER",
    "BRAND_NEUTRAL",
    "BRAND_BG",
    "BRAND_BG_SOFT",
    "PHASE_COLORS",
    "STATUS_COLORS",
    "biontech_brand_prompt_section",
    "biontech_voice_prompt_section",
    "VIZ_DECISION_MATRIX",
    "SHADCN_CATALOG",
    "RECHARTS_CATALOG",
    "MERMAID_CATALOG",
]

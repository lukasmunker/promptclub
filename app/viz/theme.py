"""Visual theme for the Pharmafuse MCP artifact recipes.

Centralizes the Tailwind class vocabulary + hex palette every HTML recipe
uses, so brand tweaks happen in one place instead of being scattered across
seven files.

Current palette (April 2026): Pharmafuse / [Company] look-and-feel
derived from the project architecture diagram.

  Primary accent   : teal gradient (#134e4a → #a5e5d9)
  Secondary accent : rose / soft red (#e11d48) — used for phase pills,
                     whitespace-signal cards, and other "pay attention"
                     surfaces. Mirrors the red underlines on the diagram.
  Neutral          : white background with slate-900 text
  Muted            : gray-100 / gray-500 for empty states

All class strings here reference Tailwind utilities from the preloaded
Play CDN — no custom config needed.
"""

from __future__ import annotations

# --- Identifier badges (NCT / PMID) ----------------------------------------


BADGE_NCT = (
    "font-mono text-xs px-2 py-0.5 rounded "
    "bg-teal-50 text-teal-800 border border-teal-200 "
    "hover:bg-teal-100"
)
"""ClinicalTrials.gov NCT identifier — teal medium."""

BADGE_PMID = (
    "font-mono text-xs px-2 py-0.5 rounded "
    "bg-teal-100 text-teal-900 border border-teal-300 "
    "hover:bg-teal-200"
)
"""PubMed PMID identifier — teal darker so it's distinguishable from NCT."""

BADGE_TARGET = (
    "font-mono text-xs px-2 py-0.5 rounded "
    "bg-teal-50 text-teal-800 border border-teal-200 "
    "hover:bg-teal-100"
)
"""Open Targets gene/target symbol — same treatment as NCT."""

BADGE_MUTED = (
    "font-mono text-xs px-2 py-0.5 rounded "
    "bg-gray-100 text-gray-600"
)
"""Placeholder badge for '(no id)' entries."""


# --- Status / phase pills --------------------------------------------------


PILL_STATUS = (
    "inline-flex items-center text-xs px-2 py-0.5 rounded "
    "bg-teal-50 text-teal-800 border border-teal-200"
)
"""Trial status (Recruiting, Completed, …) — teal, mirrors the NCT badge
so status feels connected to the identifier it annotates."""

PILL_PHASE = (
    "inline-flex items-center text-xs px-2 py-0.5 rounded "
    "bg-rose-50 text-rose-700 border border-rose-200"
)
"""Clinical phase (Phase 3, Phase 1/2, …) — rose accent so the phase
stands out next to the teal status pill."""


# --- Stat tiles (whitespace_card, indication_dashboard) --------------------


TILE_TEAL = "bg-teal-50 text-teal-800 border-teal-200"
"""Primary metric tile — teal light, for trial / recruiting counts."""

TILE_TEAL_DARK = "bg-teal-100 text-teal-900 border-teal-300"
"""Secondary metric tile — slightly darker for hierarchy."""

TILE_ROSE = "bg-rose-50 text-rose-700 border-rose-200"
"""Alert tile — for whitespace / gap counts that should draw attention."""

TILE_MUTED = "bg-gray-50 text-gray-700 border-gray-200"
"""Neutral tile fallback for unclassified metrics."""


# --- Bars (progress / score / ranking) ------------------------------------


BAR_TRACK = "bg-gray-100"
"""Background rail for any inline progress bar."""

BAR_FILL_PRIMARY = "bg-teal-600"
"""Filled portion of a progress bar — primary accent."""

BAR_FILL_SECONDARY = "bg-teal-400"
"""Filled portion for secondary bars (e.g. sponsor rankings next to a
table of NCT bars)."""


# --- Signal / warning cards (whitespace_card signals) ---------------------


SIGNAL_CARD = (
    "flex items-start gap-2 rounded-md border "
    "border-rose-200 bg-rose-50 p-3 text-sm text-rose-900"
)
"""Warning-styled card for identified whitespace signals."""

SIGNAL_ICON_COLOR = "text-rose-600"
"""Color class for the warning triangle icon inside a signal card."""


# --- Links -----------------------------------------------------------------


LINK_SUBTLE = "text-xs text-teal-700 hover:underline"
"""External link in a header, e.g. 'View on Open Targets →'."""


# --- Headers / borders ----------------------------------------------------


HEADER_BORDER = "border-b border-teal-100"
"""Bottom border under a recipe's <header> element, teal instead of gray
so it echoes the theme subtly even at a glance."""


# --- SVG donut palette (inline <svg> in indication_dashboard) -------------


DONUT_PALETTE = (
    "#134e4a",  # teal-900 — darkest slice
    "#0f766e",  # teal-700
    "#14b8a6",  # teal-500
    "#5eead4",  # teal-300
    "#ccfbf1",  # teal-100 — lightest slice
    "#e11d48",  # rose-600 — accent overflow slice
    "#1b5f55",  # custom dark teal from the diagram
    "#a5e5d9",  # custom mint from the diagram
)
"""5 teal shades from darkest to lightest + rose accent + 2 diagram-sampled
teal values. Wraps after 8 slices — pie charts with that many distinct
categories should be rare (indication_dashboard caps at 5 phases / 3
statuses), so wrap-around is mostly defensive."""


# --- Mermaid gantt theme variables ----------------------------------------


MERMAID_THEME_DIRECTIVE = (
    "%%{init: {'theme':'base','themeVariables':{"
    "'primaryColor':'#ccfbf1',"
    "'primaryTextColor':'#134e4a',"
    "'primaryBorderColor':'#0f766e',"
    "'lineColor':'#5eead4',"
    "'secondaryColor':'#a5e5d9',"
    "'tertiaryColor':'#f0fdfa',"
    "'tertiaryBorderColor':'#14b8a6',"
    "'sectionBkgColor':'#f0fdfa',"
    "'altSectionBkgColor':'#ccfbf1',"
    "'taskBkgColor':'#14b8a6',"
    "'taskTextColor':'#ffffff',"
    "'taskTextDarkColor':'#134e4a',"
    "'taskTextLightColor':'#ffffff',"
    "'taskTextOutsideColor':'#134e4a',"
    "'activeTaskBkgColor':'#0f766e',"
    "'activeTaskBorderColor':'#134e4a',"
    "'gridColor':'#ccfbf1'"
    "}}}%%"
)
"""Mermaid init directive that rebrands the gantt chart with the teal
palette. Prepended as the first line of every mermaid ``raw`` string so
the chart matches the HTML recipes visually."""


__all__ = [
    # Badges
    "BADGE_NCT",
    "BADGE_PMID",
    "BADGE_TARGET",
    "BADGE_MUTED",
    # Pills
    "PILL_STATUS",
    "PILL_PHASE",
    # Tiles
    "TILE_TEAL",
    "TILE_TEAL_DARK",
    "TILE_ROSE",
    "TILE_MUTED",
    # Bars
    "BAR_TRACK",
    "BAR_FILL_PRIMARY",
    "BAR_FILL_SECONDARY",
    # Signals
    "SIGNAL_CARD",
    "SIGNAL_ICON_COLOR",
    # Links & misc
    "LINK_SUBTLE",
    "HEADER_BORDER",
    # Charts
    "DONUT_PALETTE",
    "MERMAID_THEME_DIRECTIVE",
]

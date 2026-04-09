"""Visual theme for the Pharmafuse MCP artifact recipes.

Centralizes the Tailwind class vocabulary + hex palette every HTML recipe
uses, so brand tweaks happen in one place instead of being scattered across
seven files.

Current palette (April 2026): **BioNtech brand colors**.

  Primary  : ``#179E75``  dark teal-green — main text, solid bar fills,
                         NCT badges, status pills, primary borders
  Secondary: ``#99D11E``  bright lime — accent tiles, highlight bars,
                         secondary badges / pills, donut slices
  Alert    : ``#e11d48``  rose — only for true warnings (whitespace
                         signals). Kept from the previous iteration
                         because neither brand color reads as "alert"
                         on its own.
  Neutral  : white background with ``text-gray-900`` for body text

Color usage strategy
- Primary green is used for any element that should read as
  "identifier" / "primary action" (NCT, status, scores).
- Lime is used sparingly as a secondary accent (phase pill, one stat
  tile, donut slices). Too much lime gets noisy.
- Rose is reserved for alert surfaces only.

Tailwind integration
The Tailwind Play CDN preloaded in LibreChat's HTML artifact sandbox
supports arbitrary-value syntax ``bg-[#179E75]``, ``text-[#179E75]``,
``border-[#179E75]/30``, etc. We use arbitrary values here to hit the
exact brand hex codes rather than approximating with built-in teal/
emerald shades.
"""

from __future__ import annotations

# --- Raw hex values (shared between HTML classes and inline SVG/mermaid) ---


PRIMARY_HEX = "#179E75"
"""BioNtech brand primary: dark teal-green."""

PRIMARY_DARK_HEX = "#0d7a5a"
"""Darker shade of primary, for hover states / donut slices."""

PRIMARY_DARKER_HEX = "#064d36"
"""Deepest green for contrast text on light backgrounds."""

SECONDARY_HEX = "#99D11E"
"""BioNtech brand secondary: bright lime."""

SECONDARY_DARK_HEX = "#6fa312"
"""Darker lime for hover / secondary text (still readable on white)."""

SECONDARY_LIGHT_HEX = "#d1eb6e"
"""Lighter lime for donut slices / muted fills."""

ALERT_HEX = "#e11d48"
"""Rose-600 — only for whitespace signals / true alerts."""


# --- Outer card wrapper ---------------------------------------------------


CARD_WRAPPER = (
    "bg-white text-gray-900 rounded-lg ring-1 ring-[#179E75]/20 "
    "p-4 font-sans"
)
"""Outer ``<div>`` class for every HTML recipe. The explicit ``bg-white``
is critical: LibreChat's artifact side pane honors the user's light/dark
preference, so without a forced background our ``text-gray-900`` title
would sit on a dark surface and become unreadable. The ring uses the
BioNtech primary with 20% alpha for a subtle branded border.

Every HTML recipe's outermost div should use this class — append
``space-y-4`` / ``space-y-6`` / layout utilities after."""


# --- Identifier badges (NCT / PMID / gene targets) ------------------------


BADGE_NCT = (
    "font-mono text-xs px-2 py-0.5 rounded "
    "bg-[#179E75]/10 text-[#064d36] border border-[#179E75]/30 "
    "hover:bg-[#179E75]/20"
)
"""ClinicalTrials.gov NCT identifier — primary brand green."""

BADGE_PMID = (
    "font-mono text-xs px-2 py-0.5 rounded "
    "bg-[#99D11E]/15 text-[#3d5a0a] border border-[#99D11E]/40 "
    "hover:bg-[#99D11E]/25"
)
"""PubMed PMID identifier — lime accent, distinguishable from NCT."""

BADGE_TARGET = BADGE_NCT
"""Open Targets gene/target symbol — same treatment as NCT."""

BADGE_MUTED = (
    "font-mono text-xs px-2 py-0.5 rounded "
    "bg-gray-100 text-gray-600"
)
"""Placeholder badge for '(no id)' entries."""


# --- Status / phase pills --------------------------------------------------


PILL_STATUS = (
    "inline-flex items-center text-xs px-2 py-0.5 rounded "
    "bg-[#179E75]/10 text-[#064d36] border border-[#179E75]/30"
)
"""Trial status (Recruiting, Completed, …) — primary green."""

PILL_PHASE = (
    "inline-flex items-center text-xs px-2 py-0.5 rounded "
    "bg-[#99D11E]/20 text-[#3d5a0a] border border-[#99D11E]/50"
)
"""Clinical phase (Phase 3, Phase 1/2, …) — lime accent."""


# --- Stat tiles (whitespace_card, indication_dashboard) --------------------


TILE_PRIMARY = (
    "bg-[#179E75]/10 text-[#064d36] border-[#179E75]/30"
)
"""Primary metric tile — primary green at 10% alpha."""

TILE_PRIMARY_SOLID = (
    "bg-[#179E75]/20 text-[#064d36] border-[#179E75]/40"
)
"""Darker primary tile for hierarchy / important metrics."""

TILE_SECONDARY = (
    "bg-[#99D11E]/15 text-[#3d5a0a] border-[#99D11E]/40"
)
"""Secondary metric tile — lime accent for "different kind of data"."""

TILE_ROSE = (
    "bg-rose-50 text-rose-700 border-rose-200"
)
"""Alert tile — only for whitespace / gap counts that should draw
attention. Kept rose because brand colors don't read as "alert"."""

TILE_MUTED = (
    "bg-gray-50 text-gray-700 border-gray-200"
)
"""Neutral tile fallback."""

# Aliases kept for backwards compat with existing recipe imports —
# both names point at the same classes.
TILE_TEAL = TILE_PRIMARY
TILE_TEAL_DARK = TILE_PRIMARY_SOLID


# --- Bars (progress / score / ranking) ------------------------------------


BAR_TRACK = "bg-gray-100"
"""Background rail for any inline progress bar."""

BAR_FILL_PRIMARY = "bg-[#179E75]"
"""Filled portion of a progress bar — primary brand green."""

BAR_FILL_SECONDARY = "bg-[#99D11E]"
"""Filled portion for secondary bars — lime accent."""


# --- Signal / warning cards (whitespace_card signals) ---------------------


SIGNAL_CARD = (
    "flex items-start gap-2 rounded-md border "
    "border-rose-200 bg-rose-50 p-3 text-sm text-rose-900"
)
"""Warning-styled card for identified whitespace signals."""

SIGNAL_ICON_COLOR = "text-rose-600"
"""Color class for the warning triangle icon inside a signal card."""


# --- Links -----------------------------------------------------------------


LINK_SUBTLE = "text-xs text-[#179E75] hover:underline"
"""External link in a header, e.g. 'View on Open Targets →'."""


# --- Headers / borders ----------------------------------------------------


HEADER_BORDER = "border-b border-[#179E75]/20"
"""Bottom border under a recipe's <header> element, BioNtech primary at
20% alpha — subtle but on-brand."""


# --- SVG donut palette (inline <svg> in indication_dashboard) -------------


DONUT_PALETTE = (
    PRIMARY_DARKER_HEX,   # #064d36 — darkest green
    PRIMARY_HEX,          # #179E75 — primary
    PRIMARY_DARK_HEX,     # #0d7a5a — deep green
    SECONDARY_DARK_HEX,   # #6fa312 — dark lime
    SECONDARY_HEX,        # #99D11E — secondary lime
    SECONDARY_LIGHT_HEX,  # #d1eb6e — light lime
    ALERT_HEX,            # #e11d48 — rose accent
    "#a5e5d9",            # mint fallback for overflow slices
)
"""Brand-aligned donut palette. Order is chosen so the first N slices
pick distinguishable values (dark green → primary → deep green → dark
lime → lime → light lime) before wrapping around to rose + mint."""


# --- Mermaid gantt theme variables ----------------------------------------


MERMAID_THEME_DIRECTIVE = (
    "%%{init: {'theme':'base','themeVariables':{"
    f"'primaryColor':'{SECONDARY_HEX}',"
    f"'primaryTextColor':'{PRIMARY_DARKER_HEX}',"
    f"'primaryBorderColor':'{PRIMARY_HEX}',"
    f"'lineColor':'{PRIMARY_HEX}',"
    f"'secondaryColor':'{SECONDARY_LIGHT_HEX}',"
    "'tertiaryColor':'#f6fce6',"
    f"'tertiaryBorderColor':'{SECONDARY_DARK_HEX}',"
    "'sectionBkgColor':'#f6fce6',"
    f"'altSectionBkgColor':'{SECONDARY_LIGHT_HEX}',"
    f"'taskBkgColor':'{PRIMARY_HEX}',"
    "'taskTextColor':'#ffffff',"
    f"'taskTextDarkColor':'{PRIMARY_DARKER_HEX}',"
    "'taskTextLightColor':'#ffffff',"
    f"'taskTextOutsideColor':'{PRIMARY_DARKER_HEX}',"
    f"'activeTaskBkgColor':'{PRIMARY_DARK_HEX}',"
    f"'activeTaskBorderColor':'{PRIMARY_DARKER_HEX}',"
    f"'gridColor':'{SECONDARY_LIGHT_HEX}'"
    "}}}%%"
)
"""Mermaid init directive that rebrands the gantt chart with the BioNtech
palette. Prepended as the first line of every mermaid ``raw`` string so
the chart matches the HTML recipes visually."""


__all__ = [
    # Raw hex for callers that need the color literally
    "PRIMARY_HEX",
    "PRIMARY_DARK_HEX",
    "PRIMARY_DARKER_HEX",
    "SECONDARY_HEX",
    "SECONDARY_DARK_HEX",
    "SECONDARY_LIGHT_HEX",
    "ALERT_HEX",
    # Wrapper
    "CARD_WRAPPER",
    # Badges
    "BADGE_NCT",
    "BADGE_PMID",
    "BADGE_TARGET",
    "BADGE_MUTED",
    # Pills
    "PILL_STATUS",
    "PILL_PHASE",
    # Tiles
    "TILE_PRIMARY",
    "TILE_PRIMARY_SOLID",
    "TILE_SECONDARY",
    "TILE_ROSE",
    "TILE_MUTED",
    "TILE_TEAL",        # alias
    "TILE_TEAL_DARK",   # alias
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

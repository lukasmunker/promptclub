"""HTML sanitization helpers for app.viz HTML recipes.

The Tailwind Play CDN preloaded in LibreChat's `text/html` artifact sandbox
accepts arbitrary utility classes, so we build HTML as plain strings. All
user-interpolated values MUST pass through `escape_html()` to prevent XSS —
the artifact runs in a sandbox but we don't rely on the sandbox for safety.

``svg_donut()`` emits a standalone inline SVG donut chart for categorical
distributions — used by ``indication_dashboard`` for phase/status pies
without requiring a charting library in the sandbox.
"""

from __future__ import annotations

import html as _html
import math
import re

__all__ = ["escape_html", "strip_dangerous_html", "assert_safe_html", "svg_donut"]


def escape_html(value: object) -> str:
    """HTML-escape any value. Accepts non-str inputs for convenience (numbers,
    dates, etc.) and coerces them to ``str()`` first."""
    if value is None:
        return ""
    return _html.escape(str(value), quote=True)


# Patterns we actively strip from any raw HTML that leaks through. These are
# defensive — recipes should never generate these in the first place.
_DANGEROUS_PATTERNS = [
    # Inline scripts
    re.compile(r"<\s*script\b[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<\s*script\b[^>]*/?>", re.IGNORECASE),
    # Iframes, objects, embeds
    re.compile(r"<\s*iframe\b[^>]*>.*?<\s*/\s*iframe\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<\s*(object|embed|applet)\b[^>]*>", re.IGNORECASE),
    # Inline event handlers (onclick=, onload=, etc.)
    re.compile(r"\s+on[a-z]+\s*=\s*\"[^\"]*\"", re.IGNORECASE),
    re.compile(r"\s+on[a-z]+\s*=\s*'[^']*'", re.IGNORECASE),
    # javascript: URLs
    re.compile(r"(href|src)\s*=\s*\"\s*javascript:[^\"]*\"", re.IGNORECASE),
    re.compile(r"(href|src)\s*=\s*'\s*javascript:[^']*'", re.IGNORECASE),
]


def strip_dangerous_html(body: str) -> str:
    """Strip known-dangerous constructs from an HTML string. Defensive last
    resort — recipes should never emit these."""
    for pattern in _DANGEROUS_PATTERNS:
        body = pattern.sub("", body)
    return body


def assert_safe_html(body: str) -> None:
    """Raise ValueError if `body` contains constructs that are forbidden in
    our text/html artifacts. Used by tests and the build pipeline as a final
    compliance check."""
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(body):
            raise ValueError(
                f"HTML body contains forbidden pattern: {pattern.pattern!r}"
            )


# Default donut palette — BioNtech brand colors (matching app/viz/theme
# .DONUT_PALETTE). Re-declared here to avoid a circular import back into
# app.viz.theme; keep in sync when the brand palette changes. Order puts
# distinguishable shades first so the common 2-5 slice pies read clearly.
_DONUT_COLORS = (
    "#064d36",  # darkest green
    "#179E75",  # primary BioNtech green
    "#0d7a5a",  # deep green
    "#6fa312",  # dark lime
    "#99D11E",  # secondary BioNtech lime
    "#d1eb6e",  # light lime
    "#e11d48",  # rose accent
    "#a5e5d9",  # mint fallback
)


def svg_donut(
    segments: list[tuple[str, float]],
    size: int = 180,
    stroke: int = 28,
) -> str:
    """Render a categorical distribution as an inline SVG donut chart + legend.

    Args:
        segments: List of (label, value) tuples. Zero and negative values are
            dropped. If the resulting list is empty or has fewer than 2
            segments, returns an empty string so the caller can decide what
            to do (skip the panel, show a placeholder, etc).
        size: Outer diameter of the donut, in pixels.
        stroke: Stroke width of the donut ring, in pixels. ``size - 2 *
            stroke`` is the inner hole diameter.

    Returns:
        An HTML snippet containing the SVG and a stacked legend below it, or
        the empty string when there isn't enough data to render a meaningful
        donut. The caller is responsible for wrapping the result in any
        layout container.
    """
    clean: list[tuple[str, float]] = [
        (str(label), float(value))
        for label, value in segments
        if isinstance(value, (int, float)) and value > 0
    ]
    if len(clean) < 2:
        return ""

    total = sum(value for _, value in clean)
    if total <= 0:
        return ""

    # SVG coordinate system: center of the circle at (cx, cy), radius = half
    # of the outer diameter minus half the stroke (so the stroke stays inside
    # the viewBox).
    radius = (size - stroke) / 2
    cx = cy = size / 2
    circumference = 2 * math.pi * radius

    # We draw each slice as a single <circle> with dasharray = (arc_length,
    # rest) + a dashoffset that rotates the slice into position. This renders
    # reliably in every HTML renderer without needing <path d="A …"> arc
    # math.
    slices: list[str] = []
    legend_rows: list[str] = []
    cumulative = 0.0
    for idx, (label, value) in enumerate(clean):
        fraction = value / total
        arc = fraction * circumference
        # Negative dashoffset rotates the slice to start at the cumulative
        # position; SVG dashoffsets shift the pattern backwards along the path.
        offset = -cumulative * circumference
        color = _DONUT_COLORS[idx % len(_DONUT_COLORS)]
        slices.append(
            f'<circle cx="{cx}" cy="{cy}" r="{radius}" '
            f'fill="transparent" stroke="{color}" stroke-width="{stroke}" '
            f'stroke-dasharray="{arc:.3f} {circumference - arc:.3f}" '
            f'stroke-dashoffset="{offset:.3f}" />'
        )
        pct = round(fraction * 100)
        legend_rows.append(
            f'<li class="flex items-center gap-2 text-xs text-gray-700">'
            f'<span class="inline-block w-3 h-3 rounded-sm" '
            f'style="background-color: {color}"></span>'
            f'<span class="flex-1">{escape_html(label)}</span>'
            f'<span class="tabular-nums text-gray-500">{pct}%</span>'
            f"</li>"
        )
        cumulative += fraction

    # viewBox starts at (0, 0). The -90deg rotation makes slice 0 start at
    # 12 o'clock instead of 3 o'clock.
    svg = (
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
        f'class="flex-shrink-0" style="transform: rotate(-90deg);">'
        + "".join(slices)
        + "</svg>"
    )
    legend = (
        '<ul class="flex-1 space-y-1.5 min-w-0">' + "".join(legend_rows) + "</ul>"
    )
    return (
        '<div class="flex items-center gap-4">'
        + svg
        + legend
        + "</div>"
    )

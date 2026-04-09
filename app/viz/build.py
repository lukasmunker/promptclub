"""Top-level entrypoint: build_response()

The MCP Yallah server calls this at the end of each tool to turn raw tool
output into a LibreChat-ready envelope. Everything else in app.viz is an
implementation detail behind this single function.
"""

from __future__ import annotations

from typing import Any

from app.viz import render_hints
from app.viz.contract import Decision, DecisionKind, Envelope, PreferVisualization, Source
from app.viz.decision import should_visualize
from app.viz.recipes import REGISTRY

__all__ = ["build_response"]


def build_response(
    tool_name: str,
    data: dict[str, Any],
    sources: list[Source] | list[dict[str, Any]] | None = None,
    prefer_visualization: PreferVisualization = "auto",
) -> dict[str, Any]:
    """Wrap a tool's result into a LibreChat visualization envelope.

    Args:
        tool_name: The MCP tool name (drives decision + recipe selection).
        data: The tool's raw result payload (tool-specific shape).
        sources: List of public-data citations. ``Source`` objects or plain
            dicts that match the ``Source`` schema. May be omitted only for
            tools that genuinely have no sources (rare).
        prefer_visualization: LLM-set override. One of ``"auto"`` (default),
            ``"always"``, ``"never"``, or ``"cards"``.

    Returns:
        A plain dict suitable for ``json.dumps()`` and returning from a tool.
        Always contains ``render_hint``, ``data``, ``sources`` keys. Contains
        ``ui`` only when the decision logic picked a recipe.

    Example:
        >>> from app.viz import build_response
        >>> envelope = build_response(
        ...     "search_clinical_trials",
        ...     {"results": [...], "total": 8},
        ...     sources=[{"kind": "clinicaltrials.gov", "id": "NCT01",
        ...               "url": "https://clinicaltrials.gov/study/NCT01",
        ...               "retrieved_at": "2026-04-09T12:00:00Z"}],
        ... )
    """
    normalized_sources = _normalize_sources(sources)

    decision = should_visualize(tool_name, data, prefer_visualization)

    if decision.kind == DecisionKind.SKIP:
        envelope = Envelope(
            render_hint=render_hints.SKIP,
            ui=None,
            data=data,
            sources=normalized_sources,
        )
        return _serialize(envelope)

    recipe_name = decision.recipe
    if recipe_name is None or recipe_name not in REGISTRY:
        # Shouldn't happen — decision.use() requires a recipe name. Defensive.
        envelope = Envelope(
            render_hint=render_hints.SKIP,
            ui=None,
            data=data,
            sources=normalized_sources,
        )
        return _serialize(envelope)

    builder = REGISTRY[recipe_name]
    # Pass sources into the recipe so it can embed an in-visualization
    # citation footer ("Source: ClinicalTrials.gov (8) · Retrieved 2026-04-09")
    # alongside the envelope-level `sources` array.
    ui = builder(data, sources=normalized_sources)

    envelope = Envelope(
        render_hint=render_hints.for_artifact_type(ui.artifact.type),
        ui=ui,
        data=data,
        sources=normalized_sources,
    )
    return _serialize(envelope)


# --- Helpers ----------------------------------------------------------------


def _normalize_sources(
    sources: list[Source] | list[dict[str, Any]] | None,
) -> list[Source]:
    if sources is None:
        return []
    normalized: list[Source] = []
    for entry in sources:
        if isinstance(entry, Source):
            normalized.append(entry)
        elif isinstance(entry, dict):
            normalized.append(Source(**entry))
        else:
            raise TypeError(
                f"Source entries must be Source instances or dicts, got {type(entry).__name__}"
            )
    return normalized


def _serialize(envelope: Envelope) -> dict[str, Any]:
    """Dump a validated Envelope to a plain dict with the public field names.

    - Uses by_alias=True so ``from`` / ``import`` / ``bindData`` aliases are
      emitted instead of Python-safe ``from_``, ``imports``, ``bind_data``.
    - Uses exclude_none=True to keep the envelope tight — None fields like
      ``ui.components`` for HTML recipes stay out of the JSON.
    """
    return envelope.model_dump(by_alias=True, exclude_none=True, mode="json")

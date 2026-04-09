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
from app.viz.fallback import build_fallback_data, pick_fallback_recipe
from app.viz.recipes import REGISTRY

__all__ = ["build_response"]


def build_response(
    tool_name: str,
    data: dict[str, Any],
    sources: list[Source] | list[dict[str, Any]] | None = None,
    prefer_visualization: PreferVisualization = "auto",
    query_hint: str | None = None,
) -> dict[str, Any]:
    """Wrap a tool's result into a LibreChat visualization envelope.

    Coverage guarantee: this function ALWAYS returns an envelope with a
    populated ``ui`` field. If the primary decision logic skips, the
    fallback dispatcher routes the response through one of the three
    fallback recipes (info_card / concept_card / single_entity_card).

    Args:
        tool_name: The MCP tool name.
        data: The tool's raw result payload.
        sources: List of public-data citations.
        prefer_visualization: LLM-set override.
        query_hint: Optional original user query, used by the fallback
            dispatcher to pick concept_card vs info_card. Pass through
            from the MCP tool wrapper if available.
    """
    normalized_sources = _normalize_sources(sources)

    decision = should_visualize(tool_name, data, prefer_visualization)
    recipe_name: str
    recipe_data: dict[str, Any]
    fallback_used = False
    fallback_reason = ""

    if decision.kind == DecisionKind.USE and decision.recipe in REGISTRY:
        recipe_name = decision.recipe
        recipe_data = data
    else:
        # Fallback path — guaranteed to produce a recipe
        fallback_used = True
        fallback_reason = (
            decision.reason if decision.kind == DecisionKind.SKIP
            else f"primary recipe '{decision.recipe}' not in REGISTRY"
        )
        recipe_name = pick_fallback_recipe(tool_name, data, query_hint)
        recipe_data = build_fallback_data(
            recipe_name=recipe_name,
            tool_name=tool_name,
            original_data=data,
            query_hint=query_hint,
        )

    builder = REGISTRY[recipe_name]
    ui = builder(recipe_data, sources=normalized_sources)

    envelope = Envelope(
        render_hint=render_hints.for_artifact_type(ui.artifact.type),
        ui=ui,
        data=data,  # original data preserved for downstream consumers
        sources=normalized_sources,
    )
    serialized = _serialize(envelope)

    # Coverage log hook (Task 13 will add the actual write — for now we
    # just stash the metadata so the test can observe it).
    serialized["_coverage"] = {
        "tool": tool_name,
        "recipe": recipe_name,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
    }
    return serialized


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
    return envelope.model_dump(by_alias=True, exclude_none=True, mode="json")

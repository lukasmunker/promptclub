"""Top-level entrypoint: build_response()

The Pharmafuse MCP server calls this at the end of each tool to turn raw tool
output into a LibreChat-ready envelope. Everything else in app.viz is an
implementation detail behind this single function.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from app.knowledge.oncology.loader import load_lexicon
from app.knowledge.oncology.schema import Lexicon
from app.services.enrichment import enrich
from app.viz import coverage_log
from app.viz import render_hints
from app.viz.contract import Decision, DecisionKind, Envelope, PreferVisualization, Source
from app.viz.decision import should_visualize
from app.viz.fallback import build_fallback_data, pick_fallback_recipe
from app.viz.recipes import REGISTRY

__all__ = ["build_response"]


_logger = logging.getLogger(__name__)
# Sticky kill-switch: once enrichment fails (e.g. lexicon file missing or
# malformed at runtime), we disable it for the rest of the process so the
# WS1 artifact coverage guarantee is not broken by repeated exceptions. The
# flag is module-level and intentionally not reset at runtime — a restart
# is required to re-enable enrichment.
_enrichment_disabled = False


@lru_cache(maxsize=1)
def _lexicon() -> Lexicon:
    """Lazy singleton — loaded once on first build_response() call."""
    return load_lexicon()


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

    # Enrich the data dict with knowledge annotations BEFORE choosing
    # a recipe. The enriched dict carries a top-level
    # ``knowledge_annotations`` field that recipes can opt into.
    #
    # Failures in enrichment are NON-FATAL — if the lexicon is missing,
    # malformed, or the enricher itself blows up, we log once and
    # continue with unenriched data. This is critical: WS1's coverage
    # guarantee (every tool response emits an artifact) must not be
    # broken by a bad merge in the lexicon file. @lru_cache does not
    # cache exceptions, so without this try/except every subsequent
    # call would re-raise and take the whole MCP server offline.
    global _enrichment_disabled
    if _enrichment_disabled:
        enriched_data = dict(data)
        enriched_data["knowledge_annotations"] = []
    else:
        try:
            enriched_data = enrich(data, _lexicon())
        except Exception as e:  # noqa: BLE001 — we truly want to catch everything
            _logger.error(
                "Enrichment failed — disabling for the rest of this process. "
                "Error: %s",
                e,
                exc_info=True,
            )
            _enrichment_disabled = True
            enriched_data = dict(data)
            enriched_data["knowledge_annotations"] = []

    if decision.kind == DecisionKind.USE and decision.recipe in REGISTRY:
        recipe_name = decision.recipe
        recipe_data = enriched_data
    else:
        # Fallback path — guaranteed to produce a recipe
        fallback_used = True
        fallback_reason = (
            decision.reason if decision.kind == DecisionKind.SKIP
            else f"primary recipe '{decision.recipe}' not in REGISTRY"
        )
        recipe_name = pick_fallback_recipe(tool_name, enriched_data, query_hint)
        recipe_data = build_fallback_data(
            recipe_name=recipe_name,
            tool_name=tool_name,
            original_data=enriched_data,
            query_hint=query_hint,
        )

    builder = REGISTRY[recipe_name]
    ui = builder(recipe_data, sources=normalized_sources)

    envelope = Envelope(
        render_hint=render_hints.for_artifact_type(ui.artifact.type),
        ui=ui,
        data=enriched_data,  # carries knowledge_annotations
        sources=normalized_sources,
    )
    serialized = _serialize(envelope)

    coverage_log.log_entry(
        tool=tool_name,
        recipe=recipe_name,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
    )
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

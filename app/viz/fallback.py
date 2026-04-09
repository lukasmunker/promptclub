"""Fallback recipe selector and data shaper.

When the primary decision logic in app.viz.decision returns
``Decision.skip(...)``, this module steps in and picks one of the three
fallback recipes (``info_card``, ``concept_card``, ``single_entity_card``)
to guarantee that the envelope always contains a visualization.

The selector is intentionally simple — small heuristics on the query
hint and the data shape. It is NOT NLP. The point is determinism, not
sophistication. ``info_card`` is the universal default.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["pick_fallback_recipe", "build_fallback_data"]


# Phrases that strongly indicate a definition / "what is X" query
_DEFINITION_PATTERNS = [
    re.compile(r"\bwhat\s+is\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+are\b", re.IGNORECASE),
    re.compile(r"\bdefine\b", re.IGNORECASE),
    re.compile(r"\bdefinition\s+of\b", re.IGNORECASE),
    re.compile(r"\bexplain\b", re.IGNORECASE),
    re.compile(r"\bmeaning\s+of\b", re.IGNORECASE),
]

# Tools that return single-entity detail records when called
_SINGLE_ENTITY_TOOLS = {
    "get_trial_details",
    "get_target_context",
    "get_sponsor_overview",
}


def pick_fallback_recipe(
    tool_name: str,
    data: dict[str, Any],
    query_hint: str | None,
) -> str:
    """Pick which fallback recipe should render this response.

    Returns one of: ``"info_card"``, ``"concept_card"``,
    ``"single_entity_card"``. Never returns None — ``info_card`` is the
    universal default.
    """
    if query_hint and any(p.search(query_hint) for p in _DEFINITION_PATTERNS):
        return "concept_card"

    if tool_name in _SINGLE_ENTITY_TOOLS and data:
        # The tool returned a populated single-record response
        if data.get("nct_id") or data.get("id") or data.get("title"):
            return "single_entity_card"

    return "info_card"


def build_fallback_data(
    recipe_name: str,
    tool_name: str,
    original_data: dict[str, Any],
    query_hint: str | None,
) -> dict[str, Any]:
    """Shape the original data dict into the input format expected by
    the chosen fallback recipe."""
    if recipe_name == "concept_card":
        return _build_concept_data(tool_name, original_data, query_hint)
    if recipe_name == "single_entity_card":
        return _build_single_entity_data(tool_name, original_data)
    return _build_info_data(tool_name, original_data, query_hint)


def _build_info_data(
    tool_name: str,
    original_data: dict[str, Any],
    query_hint: str | None,
) -> dict[str, Any]:
    title = "Result"
    bullets: list[str] = []
    no_results_hint: str | None = None

    # Try to extract a sensible title from common shapes
    if original_data.get("title"):
        title = str(original_data["title"])
    elif tool_name:
        title = f"{tool_name.replace('_', ' ').title()} Result"

    # Pull bullets from common list-shaped fields
    for key in ("results", "trials", "publications", "associations", "items"):
        items = original_data.get(key)
        if isinstance(items, list) and items:
            bullets.append(f"{len(items)} {key} returned")
            break

    if not bullets:
        if query_hint:
            no_results_hint = f"No results for: {query_hint}"
        else:
            no_results_hint = f"Tool '{tool_name}' returned no displayable records"

    return {
        "title": title,
        "subtitle": query_hint,
        "bullets": bullets,
        "no_results_hint": no_results_hint,
    }


def _build_concept_data(
    tool_name: str,
    original_data: dict[str, Any],
    query_hint: str | None,
) -> dict[str, Any]:
    term = "Concept"
    if query_hint:
        # Strip the question scaffolding to leave the bare term
        cleaned = query_hint
        for p in _DEFINITION_PATTERNS:
            cleaned = p.sub("", cleaned)
        cleaned = cleaned.strip(" ?.!,")
        if cleaned:
            term = cleaned

    # Try to find a definition-like field in the data
    definition: str | None = None
    for key in ("definition", "summary", "abstract", "description"):
        value = original_data.get(key)
        if isinstance(value, str) and value.strip():
            definition = value.strip()
            break

    # Look one level deeper into the most common list shape
    if definition is None:
        results = original_data.get("results")
        if isinstance(results, list) and results:
            first = results[0]
            if isinstance(first, dict):
                for key in ("abstract", "summary", "snippet"):
                    if first.get(key):
                        definition = str(first[key])
                        break

    return {
        "term": term,
        "definition": definition,
        "category": tool_name.replace("_", "-"),
    }


def _build_single_entity_data(
    tool_name: str,
    original_data: dict[str, Any],
) -> dict[str, Any]:
    title = (
        original_data.get("nct_id")
        or original_data.get("id")
        or original_data.get("title")
        or "Entity"
    )
    subtitle = original_data.get("title") if original_data.get("nct_id") else None

    facts: list[tuple[str, str]] = []
    for key in (
        "phase",
        "status",
        "sponsor",
        "enrollment",
        "start_date",
        "primary_completion_date",
        "condition",
        "intervention",
    ):
        value = original_data.get(key)
        if value:
            facts.append((key.replace("_", " ").title(), str(value)))

    return {
        "kind": tool_name.replace("get_", "").replace("_", " ").rstrip("s"),
        "title": str(title),
        "subtitle": subtitle,
        "facts": facts,
    }

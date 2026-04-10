"""Tool-surface coverage guarantee.

Complements test_envelope_guarantee.py (which tests build_response directly)
by exercising the actual MCP tool function bodies in app/main.py. This is
the regression net for the 'manual envelope construction' bug class — every
tool MUST route every output through build_response, never construct an
envelope dict by hand.

The test mocks the Orchestrator so no real API calls are made, then awaits
each tool function and asserts the returned text starts with the
ACTION REQUIRED preamble and carries a non-empty body — either a side-pane
``:::artifact{…}:::`` directive (html/mermaid recipes) or an inline
Markdown snippet (info_card / concept_card / single_entity_card).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import app.main as appmain


def _empty_comparison_response():
    """Return a stand-in for ComparisonResponse with empty trials."""
    return SimpleNamespace(
        summary="",
        trials=[],
        publications=[],
        web_context=[],
        limitations=[],
        citations=[],
    )


@pytest.fixture
def mocked_orchestrator():
    """Patch app.main.orchestrator with a mock whose methods return empty
    results so the empty-data / minimal-data branches of every tool fire."""

    fake = SimpleNamespace()
    fake.search_trials_with_publications = AsyncMock(
        return_value=_empty_comparison_response()
    )
    fake.get_trial_details = AsyncMock(return_value=None)
    fake.search_publications = AsyncMock(return_value=[])
    fake.get_target_context = AsyncMock(return_value=[])
    fake.get_known_drugs_for_target = AsyncMock(return_value=[])
    fake.get_regulatory_context = AsyncMock(return_value=[])
    fake.resolve_disease = AsyncMock(return_value=[])
    fake.web_context = AsyncMock(return_value=[])
    fake.test_sources = AsyncMock(return_value=[])
    fake.build_trial_comparison = AsyncMock(
        return_value={"count": 0, "trials": []}
    )
    fake.analyze_indication_landscape = AsyncMock(
        return_value={"condition": "test", "counts": {}, "trials": []}
    )
    fake.analyze_whitespace = AsyncMock(
        return_value={"condition": "test", "stats": {}, "signals": []}
    )
    fake.get_sponsor_overview = AsyncMock(
        return_value={"condition": "test", "sponsors": []}
    )

    with patch.object(appmain, "orchestrator", fake):
        yield fake


# (tool_name, kwargs) — minimal safe defaults for every MCP tool in app.main.
TOOL_CALLS: list[tuple[str, dict]] = [
    ("search_trials", {"disease_query": "test"}),
    ("get_trial_details", {"nct_id": "NCT00000000"}),
    ("search_publications", {"query": "test"}),
    ("get_target_context", {"disease_id": "EFO_0000001"}),
    ("get_known_drugs_for_target", {"ensembl_id": "ENSG00000000000"}),
    ("get_regulatory_context", {"drug_name": "test"}),
    ("resolve_disease", {"query": "test"}),
    ("web_context_search", {"query": "test"}),
    ("test_data_sources", {}),
    ("build_trial_comparison", {"nct_ids": ["NCT00000000"]}),
    ("analyze_indication_landscape", {"condition": "test"}),
    ("analyze_whitespace", {"condition": "test"}),
    ("get_sponsor_overview", {"condition": "test"}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,kwargs", TOOL_CALLS)
async def test_every_tool_returns_artifact(
    mocked_orchestrator, tool_name, kwargs
):
    """Every tool must return a string starting with ACTION REQUIRED and
    either a ``:::artifact{`` directive (side-pane path) or an inline
    Markdown body — even for empty / minimal inputs. The three small
    fallback recipes (info_card / concept_card / single_entity_card) now
    emit inline Markdown instead of an artifact directive, so the
    presence check is over EITHER shape — never neither."""
    tool_func = getattr(appmain, tool_name, None)
    assert tool_func is not None, f"Tool '{tool_name}' not found in app.main"

    try:
        result = await tool_func(**kwargs)
    except Exception as e:
        pytest.fail(f"Tool '{tool_name}' raised {type(e).__name__}: {e}")

    assert isinstance(result, str), (
        f"Tool '{tool_name}' returned {type(result).__name__}, not str"
    )
    assert result.startswith("ACTION REQUIRED"), (
        f"Tool '{tool_name}' output does not start with ACTION REQUIRED: "
        f"{result[:200]!r}"
    )
    has_artifact_directive = ":::artifact{identifier=" in result
    has_inline_markdown_body = (
        "Copy the Markdown snippet" in result and "### " in result
    )
    assert has_artifact_directive or has_inline_markdown_body, (
        f"Tool '{tool_name}' output missing both an artifact directive "
        f"AND an inline Markdown body: {result[:300]!r}"
    )

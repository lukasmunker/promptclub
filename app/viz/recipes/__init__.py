"""Recipe builders — one per visualization kind.

Each recipe exposes a ``build(data)`` function that takes a tool result dict
and returns a ``UiPayload``. Recipes know nothing about MCP internals — they
just transform data shapes into envelope pieces.
"""

from app.viz.recipes import (
    indication_dashboard,
    sponsor_pipeline_cards,
    target_associations_table,
    trial_detail_tabs,
    trial_search_results,
    trial_timeline_gantt,
    whitespace_card,
)

# Registry: recipe name → build function. Used by build.py to dispatch.
REGISTRY = {
    "indication_dashboard": indication_dashboard.build,
    "trial_search_results": trial_search_results.build,
    "trial_detail_tabs": trial_detail_tabs.build,
    "trial_timeline_gantt": trial_timeline_gantt.build,
    "sponsor_pipeline_cards": sponsor_pipeline_cards.build,
    "target_associations_table": target_associations_table.build,
    "whitespace_card": whitespace_card.build,
}

__all__ = [
    "REGISTRY",
    "indication_dashboard",
    "sponsor_pipeline_cards",
    "target_associations_table",
    "trial_detail_tabs",
    "trial_search_results",
    "trial_timeline_gantt",
    "whitespace_card",
]

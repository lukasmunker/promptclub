"""app.viz — Visualization layer for Pharmafuse MCP.

Turns MCP tool outputs into LibreChat v0.8.4 artifact envelopes so answers
render as charts (recharts), card lists (HTML + Tailwind), tabbed detail
views (shadcn/ui), or timeline diagrams (Mermaid) instead of raw JSON.

Primary entrypoint:

    from app.viz import build_response

    envelope = build_response(
        tool_name="search_clinical_trials",
        data=result,
        sources=sources,
        prefer_visualization="auto",
    )
    return json.dumps(envelope, ensure_ascii=False, indent=2)
"""

from app.viz.build import build_response
from app.viz.contract import (
    ArtifactMeta,
    BlueprintNode,
    ComponentImport,
    Decision,
    Envelope,
    Source,
    UiPayload,
)

__all__ = [
    "build_response",
    "Envelope",
    "UiPayload",
    "ArtifactMeta",
    "ComponentImport",
    "BlueprintNode",
    "Source",
    "Decision",
]

__version__ = "0.1.0"

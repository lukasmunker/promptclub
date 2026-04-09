"""React recipe: indication landscape dashboard using recharts + Tailwind.

Renders as an ``application/vnd.react`` artifact. The LLM transcribes the
blueprint tree into JSX, importing ``Card`` from shadcn and charting
components from ``recharts``.

Four panels:
  1. Phase distribution — vertical BarChart
  2. Status breakdown — PieChart
  3. Top sponsors — horizontal BarChart (capped at 20, rest grouped as "Other")
  4. Enrollment pace over time — LineChart

Panels without usable data are omitted gracefully.
"""

from __future__ import annotations

from typing import Any

from app.viz.contract import ArtifactMeta, BlueprintNode, ComponentImport, UiPayload
from app.viz.utils.citations import format_source_footer_text
from app.viz.utils.identifiers import make_identifier

__all__ = ["build", "MAX_SPONSORS_IN_BAR"]

MAX_SPONSORS_IN_BAR = 20


def build(
    data: dict[str, Any],
    sources: list[Any] | None = None,
) -> UiPayload:
    indication = data.get("indication") or "Indication"
    title = data.get("title") or f"{indication} Landscape"

    phase_dist = data.get("phase_distribution") or []
    status_breakdown = data.get("status_breakdown") or []
    top_sponsors = _cap_sponsors(data.get("top_sponsors") or [])
    enrollment_series = data.get("enrollment_over_time") or []

    # Mirror the capped sponsor list back into data so the LLM binds against
    # the same list the blueprint expects.
    data = {
        **data,
        "top_sponsors": top_sponsors,
    }

    panels: list[BlueprintNode] = []
    if phase_dist:
        panels.append(_phase_panel())
    if status_breakdown:
        panels.append(_status_panel())
    if top_sponsors:
        panels.append(_sponsors_panel())
    if enrollment_series:
        panels.append(_enrollment_panel())

    if not panels:
        # Shouldn't happen — decision layer should skip in this case — but be defensive
        panels = [_empty_state_panel(indication)]

    # Wrap the grid in a vertical stack so we can append the citation footer
    # paragraph beneath it.
    grid = BlueprintNode(
        component="div",
        props={"className": "grid md:grid-cols-2 gap-4"},
        children=panels,
    )

    root_children: list[BlueprintNode] = [grid]
    footer_text = format_source_footer_text(sources)
    if footer_text:
        root_children.append(
            BlueprintNode(
                component="p",
                props={
                    "className": "mt-4 text-xs text-gray-500 italic text-center"
                },
                text=footer_text,
            )
        )

    components = _components()
    blueprint: list[BlueprintNode] = [
        BlueprintNode(
            component="div",
            props={"className": "p-4"},
            children=root_children,
        )
    ]

    return UiPayload(
        recipe="indication_dashboard",
        artifact=ArtifactMeta(
            identifier=make_identifier("indication_dashboard", indication),
            type="application/vnd.react",
            title=title,
        ),
        components=components,
        layout="grid md:grid-cols-2 gap-4",
        blueprint=blueprint,
        raw=None,
    )


# --- Panel builders ---------------------------------------------------------


def _phase_panel() -> BlueprintNode:
    return _card(
        "Phase Distribution",
        _responsive_container(
            BlueprintNode(
                component="BarChart",
                bind_data="phase_distribution",
                children=[
                    BlueprintNode(
                        component="XAxis", props={"dataKey": "phase"}
                    ),
                    BlueprintNode(component="YAxis"),
                    BlueprintNode(component="Tooltip"),
                    BlueprintNode(
                        component="Bar",
                        props={"dataKey": "count", "fill": "#2563eb"},
                    ),
                ],
            )
        ),
    )


def _status_panel() -> BlueprintNode:
    return _card(
        "Status Breakdown",
        _responsive_container(
            BlueprintNode(
                component="PieChart",
                children=[
                    BlueprintNode(
                        component="Pie",
                        bind_data="status_breakdown",
                        props={
                            "dataKey": "count",
                            "nameKey": "status",
                            "outerRadius": 90,
                            "label": True,
                        },
                    ),
                    BlueprintNode(component="Tooltip"),
                    BlueprintNode(component="Legend"),
                ],
            )
        ),
    )


def _sponsors_panel() -> BlueprintNode:
    return _card(
        "Top Sponsors",
        _responsive_container(
            BlueprintNode(
                component="BarChart",
                bind_data="top_sponsors",
                props={"layout": "vertical"},
                children=[
                    BlueprintNode(component="XAxis", props={"type": "number"}),
                    BlueprintNode(
                        component="YAxis",
                        props={
                            "type": "category",
                            "dataKey": "name",
                            "width": 140,
                        },
                    ),
                    BlueprintNode(component="Tooltip"),
                    BlueprintNode(
                        component="Bar",
                        props={"dataKey": "trials", "fill": "#0ea5e9"},
                    ),
                ],
            )
        ),
    )


def _enrollment_panel() -> BlueprintNode:
    return _card(
        "Enrollment Pace",
        _responsive_container(
            BlueprintNode(
                component="LineChart",
                bind_data="enrollment_over_time",
                children=[
                    BlueprintNode(
                        component="XAxis", props={"dataKey": "month"}
                    ),
                    BlueprintNode(component="YAxis"),
                    BlueprintNode(component="Tooltip"),
                    BlueprintNode(
                        component="Line",
                        props={
                            "type": "monotone",
                            "dataKey": "enrolled",
                            "stroke": "#10b981",
                            "strokeWidth": 2,
                            "dot": False,
                        },
                    ),
                ],
            )
        ),
    )


def _empty_state_panel(indication: str) -> BlueprintNode:
    return _card(
        "No Aggregate Data",
        BlueprintNode(
            component="p",
            props={"className": "text-sm text-gray-600"},
            text=f"No aggregate data available for {indication}.",
        ),
    )


# --- Composition helpers ----------------------------------------------------


def _card(title: str, content: BlueprintNode) -> BlueprintNode:
    return BlueprintNode(
        component="Card",
        children=[
            BlueprintNode(
                component="CardHeader",
                children=[BlueprintNode(component="CardTitle", text=title)],
            ),
            BlueprintNode(
                component="CardContent",
                children=[content],
            ),
        ],
    )


def _responsive_container(chart: BlueprintNode) -> BlueprintNode:
    return BlueprintNode(
        component="ResponsiveContainer",
        props={"width": "100%", "height": 260},
        children=[chart],
    )


def _components() -> list[ComponentImport]:
    return [
        ComponentImport(
            **{
                "from": "/components/ui/card",
                "import": ["Card", "CardHeader", "CardTitle", "CardContent"],
            }
        ),
        ComponentImport(
            **{"from": "/components/ui/badge", "import": ["Badge"]}
        ),
        ComponentImport(
            **{
                "from": "recharts",
                "import": [
                    "BarChart",
                    "Bar",
                    "PieChart",
                    "Pie",
                    "LineChart",
                    "Line",
                    "XAxis",
                    "YAxis",
                    "Tooltip",
                    "Legend",
                    "ResponsiveContainer",
                ],
            }
        ),
        ComponentImport(
            **{"from": "lucide-react", "import": ["Activity", "Users", "Globe"]}
        ),
    ]


def _cap_sponsors(
    sponsors: list[dict[str, Any]], cap: int = MAX_SPONSORS_IN_BAR
) -> list[dict[str, Any]]:
    """Keep the top `cap` sponsors, bucket the rest as 'Other'."""
    if len(sponsors) <= cap:
        return list(sponsors)
    top = list(sponsors[:cap])
    rest = sponsors[cap:]
    other_trials = sum(s.get("trials", 0) for s in rest)
    if other_trials > 0:
        top.append({"name": "Other", "trials": other_trials})
    return top

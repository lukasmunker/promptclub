"""React recipe: single-trial deep dive with shadcn Tabs + Table.

Renders as an ``application/vnd.react`` artifact. Requires LibreChat's
``SHADCNUI`` mode (toggle "Anweisungen für shadcn/ui-Komponenten einschließen")
because ``Tabs`` and ``Table`` are not in ``essentialShadcnComponents``.

Six tabs:
  1. Overview — Card with phase, status, sponsor, enrollment, dates
  2. Design & Endpoints — primary/secondary outcome measures
  3. Eligibility — inclusion/exclusion criteria
  4. Arms — arms & interventions as a Table
  5. Sites — study locations as a Table
  6. Publications — linked PubMed publications as a Table

Tabs without data are omitted gracefully (rather than showing empty tabs).
"""

from __future__ import annotations

from typing import Any

from app.viz.contract import ArtifactMeta, BlueprintNode, ComponentImport, UiPayload
from app.viz.utils.identifiers import make_identifier

from app.viz.utils.citations import format_source_footer_text

__all__ = ["build"]

# Tab configuration: (tab_value, label, data_key_check)
_TABS = [
    ("overview", "Overview", None),  # Always shown
    ("design", "Design & Endpoints", "primary_outcome_measures"),
    ("eligibility", "Eligibility", "eligibility"),
    ("arms", "Arms", "arms"),
    ("sites", "Sites", "sites"),
    ("publications", "Publications", "linked_publications"),
]


def build(
    data: dict[str, Any],
    sources: list[Any] | None = None,
) -> UiPayload:
    nct_id = data.get("nct_id") or "trial"
    title_text = data.get("title") or nct_id

    # Determine which tabs to render based on data availability
    active_tabs = [
        (value, label)
        for value, label, check in _TABS
        if check is None or data.get(check)
    ]

    # Fallback: if only overview is available, still render it
    if not active_tabs:
        active_tabs = [("overview", "Overview")]

    components = _components()
    root = _build_root(title_text, nct_id, active_tabs, data)

    # Append a small citation footer paragraph beneath the root container so
    # the source attribution is always visible in the artifact pane.
    footer_text = format_source_footer_text(sources)
    if footer_text:
        footer_node = BlueprintNode(
            component="p",
            props={
                "className": "mt-4 text-xs text-gray-500 italic text-center"
            },
            text=footer_text,
        )
        # root is a `div` with className "space-y-4 p-4" containing [header, tabs]
        # — append the footer as another child so it sits at the bottom.
        if root.children is None:
            root.children = []
        root.children.append(footer_node)

    blueprint = [root]

    return UiPayload(
        recipe="trial_detail_tabs",
        artifact=ArtifactMeta(
            identifier=make_identifier("trial_detail_tabs", nct_id),
            type="application/vnd.react",
            title=f"Trial {nct_id}",
        ),
        components=components,
        layout=None,
        blueprint=blueprint,
        raw=None,
    )


# --- Root layout ------------------------------------------------------------


def _build_root(
    title: str,
    nct_id: str,
    active_tabs: list[tuple[str, str]],
    data: dict[str, Any],
) -> BlueprintNode:
    # Header card — title, NCT badge, status, phase
    header = BlueprintNode(
        component="Card",
        children=[
            BlueprintNode(
                component="CardHeader",
                children=[
                    BlueprintNode(
                        component="div",
                        props={"className": "flex items-start justify-between gap-3"},
                        children=[
                            BlueprintNode(component="CardTitle", text=title),
                            BlueprintNode(
                                component="Badge",
                                props={"variant": "outline"},
                                text=nct_id,
                            ),
                        ],
                    ),
                ],
            ),
            BlueprintNode(
                component="CardContent",
                children=[
                    BlueprintNode(
                        component="div",
                        props={"className": "flex flex-wrap gap-2"},
                        children=_summary_badges(data),
                    )
                ],
            ),
        ],
    )

    first_tab = active_tabs[0][0]
    tabs = BlueprintNode(
        component="Tabs",
        props={"defaultValue": first_tab, "className": "w-full"},
        children=[
            BlueprintNode(
                component="TabsList",
                children=[
                    BlueprintNode(
                        component="TabsTrigger",
                        props={"value": value},
                        text=label,
                    )
                    for value, label in active_tabs
                ],
            ),
            *[_tab_content(value, data) for value, _ in active_tabs],
        ],
    )

    return BlueprintNode(
        component="div",
        props={"className": "space-y-4 p-4"},
        children=[header, tabs],
    )


def _summary_badges(data: dict[str, Any]) -> list[BlueprintNode]:
    badges: list[BlueprintNode] = []
    for key, label in (
        ("phase", "Phase"),
        ("status", "Status"),
        ("sponsor", "Sponsor"),
        ("enrollment", "Enrollment"),
        ("start_date", "Start"),
        ("primary_completion_date", "Primary completion"),
    ):
        value = data.get(key)
        if value is None or value == "":
            continue
        badges.append(
            BlueprintNode(
                component="Badge",
                props={"variant": "secondary"},
                text=f"{label}: {value}",
            )
        )
    return badges


# --- Tab content builders ---------------------------------------------------


def _tab_content(value: str, data: dict[str, Any]) -> BlueprintNode:
    builders = {
        "overview": _tab_overview,
        "design": _tab_design,
        "eligibility": _tab_eligibility,
        "arms": _tab_arms,
        "sites": _tab_sites,
        "publications": _tab_publications,
    }
    inner = builders[value](data)
    return BlueprintNode(
        component="TabsContent",
        props={"value": value, "className": "mt-4"},
        children=[inner],
    )


def _tab_overview(data: dict[str, Any]) -> BlueprintNode:
    summary = data.get("brief_summary") or data.get("description") or ""
    return BlueprintNode(
        component="Card",
        children=[
            BlueprintNode(
                component="CardContent",
                props={"className": "pt-6"},
                children=[
                    BlueprintNode(
                        component="p",
                        props={"className": "text-sm text-gray-700 leading-relaxed"},
                        text=summary or "(no summary available)",
                    )
                ],
            )
        ],
    )


def _tab_design(data: dict[str, Any]) -> BlueprintNode:
    primary = data.get("primary_outcome_measures") or []
    secondary = data.get("secondary_outcome_measures") or []

    sections: list[BlueprintNode] = []
    if primary:
        sections.append(_outcome_section("Primary Outcome Measures", primary))
    if secondary:
        sections.append(_outcome_section("Secondary Outcome Measures", secondary))

    if not sections:
        sections = [
            BlueprintNode(
                component="p",
                props={"className": "text-sm text-gray-500"},
                text="No endpoint data available.",
            )
        ]

    return BlueprintNode(
        component="div",
        props={"className": "space-y-4"},
        children=sections,
    )


def _outcome_section(title: str, outcomes: list[dict[str, Any]]) -> BlueprintNode:
    return BlueprintNode(
        component="Card",
        children=[
            BlueprintNode(
                component="CardHeader",
                children=[BlueprintNode(component="CardTitle", text=title)],
            ),
            BlueprintNode(
                component="CardContent",
                children=[
                    BlueprintNode(
                        component="ul",
                        props={"className": "space-y-2 text-sm"},
                        children=[
                            BlueprintNode(
                                component="li",
                                props={"className": "border-l-2 border-blue-200 pl-3"},
                                children=[
                                    BlueprintNode(
                                        component="p",
                                        props={"className": "font-medium"},
                                        text=str(o.get("measure", "")),
                                    ),
                                    BlueprintNode(
                                        component="p",
                                        props={"className": "text-gray-600"},
                                        text=str(o.get("time_frame", "")),
                                    ),
                                ],
                            )
                            for o in outcomes
                        ],
                    )
                ],
            ),
        ],
    )


def _tab_eligibility(data: dict[str, Any]) -> BlueprintNode:
    elig = data.get("eligibility") or {}
    criteria = elig.get("criteria") or ""
    gender = elig.get("gender")
    min_age = elig.get("minimum_age")
    max_age = elig.get("maximum_age")

    meta_parts = []
    if gender:
        meta_parts.append(f"Gender: {gender}")
    if min_age:
        meta_parts.append(f"Min age: {min_age}")
    if max_age:
        meta_parts.append(f"Max age: {max_age}")
    meta = " · ".join(meta_parts)

    return BlueprintNode(
        component="Card",
        children=[
            BlueprintNode(
                component="CardHeader",
                children=[
                    BlueprintNode(component="CardTitle", text="Eligibility Criteria")
                ],
            ),
            BlueprintNode(
                component="CardContent",
                props={"className": "space-y-3"},
                children=[
                    BlueprintNode(
                        component="p",
                        props={"className": "text-xs text-gray-500"},
                        text=meta,
                    ),
                    BlueprintNode(
                        component="pre",
                        props={
                            "className": "whitespace-pre-wrap text-xs bg-gray-50 "
                            "p-3 rounded border border-gray-200 font-sans"
                        },
                        text=str(criteria),
                    ),
                ],
            ),
        ],
    )


def _tab_arms(data: dict[str, Any]) -> BlueprintNode:
    arms = data.get("arms") or []
    return _simple_table(
        "Arms & Interventions",
        ["Arm", "Type", "Description", "Interventions"],
        [
            [
                str(a.get("label", "")),
                str(a.get("type", "")),
                str(a.get("description", "")),
                ", ".join(a.get("interventions") or []),
            ]
            for a in arms
        ],
    )


def _tab_sites(data: dict[str, Any]) -> BlueprintNode:
    sites = data.get("sites") or data.get("locations") or []
    return _simple_table(
        "Study Sites",
        ["Facility", "City", "Country", "Status"],
        [
            [
                str(s.get("facility", "")),
                str(s.get("city", "")),
                str(s.get("country", "")),
                str(s.get("status", "")),
            ]
            for s in sites
        ],
    )


def _tab_publications(data: dict[str, Any]) -> BlueprintNode:
    pubs = data.get("linked_publications") or data.get("publications") or []
    return _simple_table(
        "Linked Publications",
        ["PMID", "Title", "Journal", "Year"],
        [
            [
                str(p.get("pmid", "")),
                str(p.get("title", "")),
                str(p.get("journal", "")),
                str(p.get("year", "")),
            ]
            for p in pubs
        ],
    )


# --- Table helper -----------------------------------------------------------


def _simple_table(
    title: str, headers: list[str], rows: list[list[str]]
) -> BlueprintNode:
    if not rows:
        return BlueprintNode(
            component="p",
            props={"className": "text-sm text-gray-500"},
            text=f"No {title.lower()} data available.",
        )

    header_cells = [
        BlueprintNode(component="TableHead", text=h) for h in headers
    ]

    body_rows = [
        BlueprintNode(
            component="TableRow",
            children=[
                BlueprintNode(component="TableCell", text=cell)
                for cell in row
            ],
        )
        for row in rows
    ]

    return BlueprintNode(
        component="Card",
        children=[
            BlueprintNode(
                component="CardHeader",
                children=[BlueprintNode(component="CardTitle", text=title)],
            ),
            BlueprintNode(
                component="CardContent",
                children=[
                    BlueprintNode(
                        component="Table",
                        children=[
                            BlueprintNode(
                                component="TableHeader",
                                children=[
                                    BlueprintNode(
                                        component="TableRow", children=header_cells
                                    )
                                ],
                            ),
                            BlueprintNode(
                                component="TableBody", children=body_rows
                            ),
                        ],
                    )
                ],
            ),
        ],
    )


def _components() -> list[ComponentImport]:
    return [
        ComponentImport(
            **{
                "from": "/components/ui/card",
                "import": [
                    "Card",
                    "CardHeader",
                    "CardTitle",
                    "CardContent",
                    "CardDescription",
                ],
            }
        ),
        ComponentImport(
            **{
                "from": "/components/ui/tabs",
                "import": [
                    "Tabs",
                    "TabsList",
                    "TabsTrigger",
                    "TabsContent",
                ],
            }
        ),
        ComponentImport(
            **{
                "from": "/components/ui/table",
                "import": [
                    "Table",
                    "TableHeader",
                    "TableRow",
                    "TableHead",
                    "TableBody",
                    "TableCell",
                ],
            }
        ),
        ComponentImport(
            **{"from": "/components/ui/badge", "import": ["Badge"]}
        ),
        ComponentImport(
            **{"from": "/components/ui/separator", "import": ["Separator"]}
        ),
    ]

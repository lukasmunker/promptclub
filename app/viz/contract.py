"""Pydantic models defining the MCP Yallah → LibreChat envelope contract.

These are the types every MCP tool response must conform to when it uses
app.viz. See docs/envelope-contract.md for the full spec.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# --- Literal types used across the contract ---------------------------------

ArtifactType = Literal[
    "text/html",
    "application/vnd.mermaid",
]

SourceKind = Literal[
    "clinicaltrials.gov",
    "pubmed",
    "openfda",
    "opentargets",
    "web",
]

PreferVisualization = Literal["auto", "always", "never", "cards"]

RecipeName = Literal[
    "indication_dashboard",
    "trial_search_results",
    "trial_detail_tabs",
    "trial_timeline_gantt",
    "sponsor_pipeline_cards",
    "target_associations_table",
    "whitespace_card",
]


# --- Decision (internal, not part of the envelope) --------------------------


class DecisionKind(str, Enum):
    USE = "use"
    SKIP = "skip"


class Decision(BaseModel):
    """Output of the should_visualize() heuristic."""

    kind: DecisionKind
    recipe: RecipeName | None = None
    reason: str = ""

    @classmethod
    def use(cls, recipe: RecipeName, reason: str = "") -> Decision:
        return cls(kind=DecisionKind.USE, recipe=recipe, reason=reason)

    @classmethod
    def skip(cls, reason: str) -> Decision:
        return cls(kind=DecisionKind.SKIP, recipe=None, reason=reason)


# --- Envelope components ----------------------------------------------------


class Source(BaseModel):
    """A single public data source citation."""

    kind: SourceKind
    id: str = Field(..., description="NCT01234567, PMID 12345678, etc.")
    url: str
    retrieved_at: datetime

    model_config = ConfigDict(extra="forbid")


class ArtifactMeta(BaseModel):
    """The attributes that fill the :::artifact{…}::: opening tag."""

    identifier: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Kebab-case identifier unique per response.",
    )
    type: ArtifactType
    title: str = Field(..., min_length=1, max_length=150)

    model_config = ConfigDict(extra="forbid")


class ComponentImport(BaseModel):
    """A single import statement for a React artifact.

    `from_` must be either ``/components/ui/<name>`` (shadcn), ``recharts``,
    or ``lucide-react``. Anything else will fail validation.
    """

    from_: str = Field(..., alias="from")
    imports: list[str] = Field(..., alias="import", min_length=1)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("from_")
    @classmethod
    def _check_import_path(cls, v: str) -> str:
        allowed_prefixes = ("/components/ui/", "recharts", "lucide-react")
        if not any(v == p or v.startswith(p) for p in allowed_prefixes):
            raise ValueError(
                f"Invalid import source '{v}'. Must be '/components/ui/<name>', "
                "'recharts', or 'lucide-react'."
            )
        return v


class BlueprintNode(BaseModel):
    """A node in a React component blueprint tree.

    The LLM transcribes the tree into JSX by following parent/child relationships
    and binding data via `bind_data` (dotted path into the envelope's `data`).
    """

    component: str = Field(..., min_length=1)
    props: dict[str, Any] | None = None
    text: str | None = None
    bind_data: str | None = Field(default=None, alias="bindData")
    children: list[BlueprintNode] | None = None

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class UiPayload(BaseModel):
    """The visualization payload attached to an envelope.

    Exactly one of `blueprint` (React) or `raw` (HTML / Mermaid) is populated,
    depending on the artifact type. This is enforced by a model validator.
    """

    recipe: RecipeName
    artifact: ArtifactMeta
    components: list[ComponentImport] | None = None
    layout: str | None = None
    blueprint: list[BlueprintNode] | None = None
    raw: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _check_shape_matches_type(self) -> UiPayload:
        # Every supported artifact type (text/html, application/vnd.mermaid)
        # carries its body in `raw`. `blueprint` / `components` are reserved
        # for the legacy React path and must not be populated.
        artifact_type = self.artifact.type
        if self.raw is None or not self.raw.strip():
            raise ValueError(
                f"{artifact_type} artifacts require a non-empty `raw` string."
            )
        if self.blueprint is not None:
            raise ValueError(
                f"{artifact_type} artifacts must not populate `blueprint`."
            )
        if self.components is not None:
            raise ValueError(
                f"{artifact_type} artifacts must not populate `components`."
            )
        return self


class Envelope(BaseModel):
    """The top-level object an MCP tool returns (json-serialized).

    When `ui` is None the LLM answers in plain text from `data`.
    When `ui` is present the LLM emits a :::artifact{…}::: block following
    `render_hint` + `ui`.
    """

    render_hint: str = Field(..., min_length=1)
    ui: UiPayload | None = None
    data: dict[str, Any]
    sources: list[Source] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("render_hint")
    @classmethod
    def _check_compliance_tokens(cls, v: str) -> str:
        # Every render_hint must mention source citation AND no forward-looking
        # statements. This is the compliance hook that every tool response hits.
        lower = v.lower()
        if "cite sources" not in lower and "cite sources" not in v:
            raise ValueError(
                "render_hint must instruct the LLM to cite sources "
                "(contain the phrase 'Cite sources')."
            )
        if "no forward-looking" not in lower:
            raise ValueError(
                "render_hint must contain 'No forward-looking' to enforce the "
                "BioNTech challenge's no-speculation rule."
            )
        return v

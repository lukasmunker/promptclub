"""Pydantic schema for the oncology lexicon.

Hard quality gates enforced here:

  - Every LexiconEntry MUST have at least one Source (Pydantic min_length).
  - Every Source URL (when present) MUST come from the authoritative
    domain allowlist (field validator).
  - Categories are bounded by a Literal type — no free-form sprawl.
  - Review status is a three-stage lifecycle: llm-generated → reviewed
    → expert-approved.

These gates prevent unverified or fabricated content from reaching
production. The curation pipeline relies on them.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = ["LexiconEntry", "Source", "Lexicon", "Annotation", "ALLOWED_SOURCE_DOMAINS"]


# Authoritative source domains. Source URLs must come from one of these.
# ``www.accessdata.fda.gov`` is the FDA subdomain that hosts official drug
# label PDFs (e.g. Drugs@FDA), so it is included alongside the main FDA
# domain.
ALLOWED_SOURCE_DOMAINS = frozenset({
    "ncit.nci.nih.gov",
    "fda.gov",
    "www.fda.gov",
    "www.accessdata.fda.gov",
    "ema.europa.eu",
    "www.ema.europa.eu",
    "recist.eortc.org",
    "pubmed.ncbi.nlm.nih.gov",
    "ctep.cancer.gov",
})


SourceKind = Literal[
    "nci-thesaurus",
    "fda-label",
    "publication",
    "guideline",
    "definition",
]


CategoryName = Literal[
    "trial-phase",
    "trial-status",
    "endpoint",
    "study-design",
    "tumor-type",
    "biomarker",
    "drug-class",
    "response-criterion",
    "treatment-line",
    "resistance-mechanism",
]


ReviewStatus = Literal["llm-generated", "reviewed", "expert-approved"]


class Source(BaseModel):
    """A single citation backing a lexicon entry."""

    kind: SourceKind
    url: str | None = None
    citation: str = Field(..., min_length=1)

    model_config = ConfigDict(extra="forbid")

    @field_validator("url")
    @classmethod
    def _check_domain_allowlist(cls, v: str | None) -> str | None:
        if v is None:
            return v
        domain = urlparse(v).netloc.lower()
        if domain not in ALLOWED_SOURCE_DOMAINS:
            raise ValueError(
                f"Source URL domain '{domain}' is not in the authoritative source allowlist. "
                f"Allowed: {sorted(ALLOWED_SOURCE_DOMAINS)}"
            )
        return v


class LexiconEntry(BaseModel):
    """A single curated oncology term entry."""

    id: str = Field(..., min_length=1, pattern=r"^[a-z0-9-]+$")
    term: str = Field(..., min_length=1)
    aliases: list[str] = Field(default_factory=list)
    category: CategoryName
    short_definition: str = Field(..., min_length=1)
    clinical_context: str = Field(..., min_length=1)
    typical_values: dict[str, str] | None = None
    related_terms: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    review_status: ReviewStatus
    last_reviewed: date | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _sources_not_empty(self) -> "LexiconEntry":
        if len(self.sources) < 1:
            raise ValueError("at least 1 source required")
        return self


class Annotation(BaseModel):
    """A single knowledge annotation attached to a tool response.

    Produced by app.services.enrichment.enrich() and surfaced as the
    ``data["knowledge_annotations"]`` list on the envelope dict.
    """

    field_path: str = Field(..., description="Dotted path to the matched field")
    matched_term: str
    lexicon_id: str
    short_definition: str
    clinical_context: str
    review_status: ReviewStatus

    model_config = ConfigDict(extra="forbid")


class Lexicon(BaseModel):
    """In-memory lexicon with prebuilt indices for fast term lookup."""

    entries: list[LexiconEntry]
    term_index: dict[str, LexiconEntry] = Field(default_factory=dict)
    # Pre-compiled alternation regex covering every term + alias, sorted
    # longest-first so re.finditer naturally prefers longer matches. Built
    # by the loader (see ``_build_lexicon`` in
    # ``app.knowledge.oncology.loader``). Optional so empty-lexicon
    # fixtures remain valid, but in production this should always be set.
    matcher_re: re.Pattern | None = None

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

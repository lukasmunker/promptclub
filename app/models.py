from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Citation(BaseModel):
    source: str
    id: str | None = None
    url: str | None = None
    title: str | None = None


class DiseaseResolutionRecord(BaseModel):
    source: str = "Open Targets"
    query: str
    disease_id: str
    disease_name: str
    entity: str | None = None
    description: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


class TrialRecord(BaseModel):
    source: str
    source_id: str
    nct_id: str | None = None
    title: str | None = None
    official_title: str | None = None
    disease: list[str] = Field(default_factory=list)
    sponsor: str | None = None
    collaborators: list[str] = Field(default_factory=list)
    phase: list[str] = Field(default_factory=list)
    status: str | None = None
    study_type: str | None = None
    enrollment: int | None = None
    interventions: list[str] = Field(default_factory=list)
    primary_endpoints: list[str] = Field(default_factory=list)
    inclusion_criteria: str | None = None
    exclusion_criteria: str | None = None
    locations: list[str] = Field(default_factory=list)
    start_date: str | None = None
    completion_date: str | None = None
    keywords: list[str] = Field(default_factory=list)
    linked_pmids: list[str] = Field(default_factory=list)
    retrieved_at: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


class PublicationRecord(BaseModel):
    source: str = "PubMed"
    pmid: str
    title: str | None = None
    journal: str | None = None
    pub_date: str | None = None
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    linked_trial_ids: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


class TargetAssociationRecord(BaseModel):
    source: str = "Open Targets"
    disease_id: str | None = None
    disease_name: str | None = None
    target_id: str | None = None
    target_symbol: str | None = None
    target_name: str | None = None
    score: float | None = None
    citations: list[Citation] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


class RegulatoryRecord(BaseModel):
    source: str = "openFDA"
    product_name: str | None = None
    sponsor_name: str | None = None
    application_number: str | None = None
    marketing_status: str | None = None
    indications_and_usage: str | None = None
    route: list[str] = Field(default_factory=list)
    active_ingredients: list[str] = Field(default_factory=list)
    warnings: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


class WebContextRecord(BaseModel):
    source: str = "Vertex Google Search"
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


class SourceTestResult(BaseModel):
    source: str
    ok: bool
    latency_ms: int
    records_found: int | None = None
    sample_ids: list[str] = Field(default_factory=list)
    error: str | None = None


class ComparisonResponse(BaseModel):
    summary: str
    trials: list[TrialRecord] = Field(default_factory=list)
    publications: list[PublicationRecord] = Field(default_factory=list)
    targets: list[TargetAssociationRecord] = Field(default_factory=list)
    regulatory: list[RegulatoryRecord] = Field(default_factory=list)
    web_context: list[WebContextRecord] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
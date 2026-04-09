from __future__ import annotations

from typing import Any

import pytest

from app.models import Citation, ComparisonResponse, DiseaseResolutionRecord, TargetAssociationRecord, TrialRecord
from app.services.llm_orchestration import LLMToolOrchestrator
from app.settings import settings


class FakeOrchestrator:
    def dedupe_citations(self, citations):
        seen = set()
        output = []
        for citation in citations:
            key = (citation.source, citation.id, citation.url, citation.title)
            if key not in seen:
                seen.add(key)
                output.append(citation)
        return output

    async def search_trials_with_publications(self, disease_query: str, **_: Any) -> ComparisonResponse:
        citation = Citation(
            source="ClinicalTrials.gov",
            id="NCT00000001",
            url="https://clinicaltrials.gov/study/NCT00000001",
            title="Melanoma Trial",
        )
        return ComparisonResponse(
            summary=f"Found 1 ClinicalTrials.gov record for '{disease_query}' and 0 linked PubMed records.",
            trials=[
                TrialRecord(
                    source="ClinicalTrials.gov",
                    source_id="NCT00000001",
                    nct_id="NCT00000001",
                    title="Melanoma Trial",
                    sponsor="Example Bio",
                    status="RECRUITING",
                    phase=["PHASE2"],
                    citations=[citation],
                )
            ],
            citations=[citation],
        )

    async def resolve_disease(self, query: str, page_size: int = 5):
        citation = Citation(
            source="Open Targets",
            id="EFO_0000756",
            url="https://platform.opentargets.org/disease/EFO_0000756",
            title="melanoma",
        )
        return [
            DiseaseResolutionRecord(
                query=query,
                disease_id="EFO_0000756",
                disease_name="melanoma",
                citations=[citation],
            )
        ][:page_size]

    async def get_target_context(self, disease_id: str):
        citation = Citation(
            source="Open Targets",
            id="ENSG000001",
            url=f"https://platform.opentargets.org/disease/{disease_id}",
            title="melanoma target associations",
        )
        return [
            TargetAssociationRecord(
                disease_id=disease_id,
                disease_name="melanoma",
                target_id="ENSG000001",
                target_symbol="BRAF",
                target_name="B-Raf proto-oncogene",
                score=0.92,
                citations=[citation],
            )
        ]


class StubLLMToolOrchestrator(LLMToolOrchestrator):
    def __init__(self, orchestrator):
        super().__init__(orchestrator)
        self.calls = 0

    async def _create_response(self, input_items, previous_response_id=None):
        self.calls += 1
        if self.calls == 1:
            return {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "name": "search_trials",
                        "call_id": "call_1",
                        "arguments": '{"disease_query":"melanoma","page_size":3}',
                    }
                ],
            }
        return {
            "id": "resp_2",
            "output_text": "Found 1 melanoma trial from ClinicalTrials.gov.",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "Found 1 melanoma trial from ClinicalTrials.gov."}
                    ],
                }
            ],
        }


class EmptyResultLLMToolOrchestrator(LLMToolOrchestrator):
    def __init__(self, orchestrator):
        super().__init__(orchestrator)
        self.calls = 0

    async def _create_response(self, input_items, previous_response_id=None):
        self.calls += 1
        if self.calls == 1:
            return {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "name": "search_trials",
                        "call_id": "call_1",
                        "arguments": '{"disease_query":"melanoma","page_size":3}',
                    }
                ],
            }
        return {
            "id": "resp_2",
            "output_text": "No evidence found.",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "No evidence found."}],
                }
            ],
        }


@pytest.mark.asyncio
async def test_llm_orchestrator_falls_back_when_openai_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "enable_llm_tool_orchestration", True)
    monkeypatch.setattr(settings, "openai_api_key", None)

    orchestrator = LLMToolOrchestrator(FakeOrchestrator())
    result = await orchestrator.answer_question("Find trials for melanoma")

    assert result["mode"] == "deterministic_fallback"
    assert result["selected_tool"] == "search_trials"
    assert "Found 1 ClinicalTrials.gov record" in result["answer"]
    assert len(result["_citations"]) == 1


@pytest.mark.asyncio
async def test_llm_orchestrator_executes_tool_calls(monkeypatch):
    monkeypatch.setattr(settings, "enable_llm_tool_orchestration", True)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_orchestrator_model", "gpt-5.4")

    orchestrator = StubLLMToolOrchestrator(FakeOrchestrator())
    result = await orchestrator.answer_question("Find trials for melanoma")

    assert result["mode"] == "llm_orchestrated"
    assert result["answer"] == "Found 1 melanoma trial from ClinicalTrials.gov."
    assert result["tool_trace"][0]["tool"] == "search_trials"
    assert result["tool_outputs"][0]["result"]["count"] == 1
    assert len(result["_citations"]) == 1


@pytest.mark.asyncio
async def test_llm_orchestrator_falls_back_when_llm_returns_no_evidence(monkeypatch):
    monkeypatch.setattr(settings, "enable_llm_tool_orchestration", True)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_orchestrator_model", "gpt-5.4")

    class EmptyTrialsOrchestrator(FakeOrchestrator):
        async def search_trials_with_publications(self, disease_query: str, **_: Any) -> ComparisonResponse:
            return ComparisonResponse(
                summary=f"Found 0 ClinicalTrials.gov records for '{disease_query}' and 0 linked PubMed records.",
                trials=[],
                citations=[],
            )

    orchestrator = EmptyResultLLMToolOrchestrator(EmptyTrialsOrchestrator())
    result = await orchestrator.answer_question("Find trials for melanoma")

    assert result["mode"] == "deterministic_fallback"
    assert result["fallback_reason"].startswith("LLM tool orchestration returned insufficient evidence")

from __future__ import annotations

from app.adapters.clinicaltrials_v2 import ClinicalTrialsV2Adapter
from app.adapters.openfda import OpenFDAAdapter
from app.adapters.opentargets import OpenTargetsAdapter
from app.adapters.pubmed import PubMedAdapter
from app.adapters.vertex_google_search import VertexGoogleSearchAdapter
from app.models import ComparisonResponse, Citation


class Orchestrator:
    def __init__(self) -> None:
        self.ct = ClinicalTrialsV2Adapter()
        self.pubmed = PubMedAdapter()
        self.ot = OpenTargetsAdapter()
        self.fda = OpenFDAAdapter()
        self.web = VertexGoogleSearchAdapter()

    @staticmethod
    def dedupe_citations(citations: list[Citation]) -> list[Citation]:
        seen = set()
        out: list[Citation] = []
        for c in citations:
            key = (c.source, c.id, c.url, c.title)
            if key not in seen:
                seen.add(key)
                out.append(c)
        return out

    async def search_trials_with_publications(
        self,
        disease_query: str,
        page_size: int = 10,
        phase: str | None = None,
        sponsor: str | None = None,
        status: str | None = None,
        include_web_context: bool = False,
    ) -> ComparisonResponse:
        trials = await self.ct.search_trials(
            disease_query=disease_query,
            page_size=page_size,
            phase=phase,
            sponsor=sponsor,
            status=status,
        )

        publications = []
        citations: list[Citation] = []

        for trial in trials[:5]:
            citations.extend(trial.citations)
            if trial.nct_id:
                pubs = await self.pubmed.get_publications_for_trial(trial.nct_id, page_size=3)
                publications.extend(pubs)

        for pub in publications:
            citations.extend(pub.citations)

        web_context = []
        if include_web_context:
            web_context = await self.web.search_context(
                f"{disease_query} oncology clinical trial landscape"
            )
            for row in web_context:
                citations.extend(row.citations)

        return ComparisonResponse(
            summary=(
                f"Found {len(trials)} ClinicalTrials.gov records for '{disease_query}' "
                f"and {len(publications)} linked PubMed records."
            ),
            trials=trials,
            publications=publications,
            web_context=web_context,
            limitations=[
                "PubMed linkage is strongest when the abstract or metadata explicitly includes an NCT ID.",
                "Open Targets disease resolution is best-effort and may return multiple ontology candidates.",
                "Web grounding is descriptive context only and should not override official structured sources.",
                "No speculative recommendations or forward-looking strategic claims should be made from these tools.",
            ],
            citations=self.dedupe_citations(citations),
        )

    async def resolve_disease(self, query: str, page_size: int = 5):
        return await self.ot.resolve_disease(query=query, page_size=page_size)

    async def get_trial_details(self, nct_id: str):
        return await self.ct.get_trial(nct_id)

    async def search_publications(self, query: str, page_size: int = 10):
        return await self.pubmed.search_publications(query=query, page_size=page_size)

    async def get_target_context(self, disease_id: str):
        return await self.ot.get_target_context(disease_id=disease_id, page_size=10)

    async def get_regulatory_context(self, drug_name: str):
        return await self.fda.search_regulatory_context(drug_name=drug_name, limit=5)

    async def web_context(self, query: str):
        return await self.web.search_context(query)

    async def test_sources(self, sample_query: str = "melanoma"):
        return [
            await self.ct.healthcheck(sample_query=sample_query),
            await self.pubmed.healthcheck(sample_query=f"{sample_query} phase 3 trial"),
            await self.ot.healthcheck(),
            await self.fda.healthcheck(sample_query="Keytruda"),
            await self.web.healthcheck(sample_query=f"latest {sample_query} oncology developments"),
        ]
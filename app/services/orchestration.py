from __future__ import annotations

import asyncio

from app.adapters.clinicaltrials_v2 import ClinicalTrialsV2Adapter
from app.adapters.openfda import OpenFDAAdapter
from app.adapters.opentargets import OpenTargetsAdapter
from app.adapters.pubmed import PubMedAdapter
from app.adapters.vertex_google_search import VertexGoogleSearchAdapter
from app.models import ComparisonResponse, Citation
from app.services.llm_orchestration import LLMToolOrchestrator
from app.settings import settings


class Orchestrator:
    def __init__(self) -> None:
        self.ct = ClinicalTrialsV2Adapter()
        self.pubmed = PubMedAdapter()
        self.ot = OpenTargetsAdapter()
        self.fda = OpenFDAAdapter()
        self.web = VertexGoogleSearchAdapter()
        self.llm = LLMToolOrchestrator(self)

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
        trials: list = []
        citations: list[Citation] = []
        limitations = [
            "PubMed linkage is strongest when the abstract or metadata explicitly includes an NCT ID.",
            "Open Targets disease resolution is best-effort and may return multiple ontology candidates.",
            "Web grounding is descriptive context only and should not override official structured sources.",
            "No speculative recommendations or forward-looking strategic claims should be made from these tools.",
        ]
        warnings: list[str] = []

        try:
            trials = await asyncio.wait_for(
                self.ct.search_trials(
                    disease_query=disease_query,
                    page_size=page_size,
                    phase=phase,
                    sponsor=sponsor,
                    status=status,
                ),
                timeout=settings.clinical_trials_search_timeout_seconds,
            )
        except Exception as exc:
            warnings.append(f"ClinicalTrials.gov search unavailable: {str(exc)}")

        publications = []
        publication_tasks = []

        for trial in trials[: settings.max_trials_to_enrich_with_publications]:
            citations.extend(trial.citations)
            if trial.nct_id:
                publication_tasks.append(
                    self._get_trial_publications_with_timeout(trial.nct_id, page_size=3)
                )

        if publication_tasks:
            publication_batches = await asyncio.gather(*publication_tasks, return_exceptions=True)
            for batch in publication_batches:
                if isinstance(batch, Exception):
                    continue
                publications.extend(batch)

        for pub in publications:
            citations.extend(pub.citations)

        web_context = []
        if include_web_context:
            web_context = await self.web_context(
                f"{disease_query} oncology clinical trial landscape"
            )
            for row in web_context:
                citations.extend(row.citations)

        summary = (
            f"Found {len(trials)} ClinicalTrials.gov records for '{disease_query}' "
            f"and {len(publications)} linked PubMed records."
        )
        if warnings:
            summary = f"{summary} Warnings: {' | '.join(warnings)}"

        return ComparisonResponse(
            summary=summary,
            trials=trials,
            publications=publications,
            web_context=web_context,
            limitations=limitations + warnings,
            citations=self.dedupe_citations(citations),
        )

    async def _get_trial_publications_with_timeout(
        self,
        nct_id: str,
        page_size: int = 3,
    ):
        try:
            return await asyncio.wait_for(
                self.pubmed.get_publications_for_trial(nct_id, page_size=page_size),
                timeout=settings.per_trial_publication_lookup_timeout_seconds,
            )
        except Exception:
            return []

    async def resolve_disease(self, query: str, page_size: int = 5):
        return await self.ot.resolve_disease(query=query, page_size=page_size)

    async def get_trial_details(self, nct_id: str):
        try:
            return await asyncio.wait_for(
                self.ct.get_trial(nct_id),
                timeout=settings.clinical_trial_details_timeout_seconds,
            )
        except Exception:
            return None

    async def search_publications(self, query: str, page_size: int = 10):
        return await self.pubmed.search_publications(query=query, page_size=page_size)

    async def get_target_context(self, disease_id: str):
        return await self.ot.get_target_context(disease_id=disease_id, page_size=10)

    async def get_regulatory_context(self, drug_name: str):
        return await self.fda.search_regulatory_context(drug_name=drug_name, limit=5)

    async def web_context(self, query: str):
        try:
            return await asyncio.wait_for(
                self.web.search_context(query),
                timeout=settings.web_context_timeout_seconds,
            )
        except Exception:
            return []

    async def test_sources(self, sample_query: str = "melanoma"):
        return [
            await self.ct.healthcheck(sample_query=sample_query),
            await self.pubmed.healthcheck(sample_query=f"{sample_query} phase 3 trial"),
            await self.ot.healthcheck(),
            await self.fda.healthcheck(sample_query="Keytruda"),
            await self.web.healthcheck(sample_query=f"latest {sample_query} oncology developments"),
        ]

    async def build_trial_comparison(self, nct_ids: list[str]) -> dict:
        """Fetch multiple trials in parallel and return them side-by-side for comparison."""
        tasks = [self.ct.get_trial(nct_id) for nct_id in nct_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        trials = []
        errors = []
        for nct_id, result in zip(nct_ids, results):
            if isinstance(result, Exception):
                errors.append({"nct_id": nct_id, "error": str(result)})
            elif result is None:
                errors.append({"nct_id": nct_id, "error": "not found"})
            else:
                trials.append(result)
        return {
            "count": len(trials),
            "trials": [t.model_dump() for t in trials],
            "errors": errors,
        }

    async def analyze_indication_landscape(
        self, condition: str, phase: str | None = None
    ) -> dict:
        """Return trial, publication, and FDA approval counts for a condition."""
        trial_count, pub_count, fda_count, diseases = await asyncio.gather(
            self.ct.count_trials(condition=condition, phase=phase),
            self.pubmed.count_publications(condition=condition),
            self.fda.count_approved(condition=condition),
            self.ot.resolve_disease(query=condition, page_size=3),
            return_exceptions=True,
        )
        return {
            "condition": condition,
            "phase_filter": phase,
            "clinical_trials_count": trial_count if not isinstance(trial_count, Exception) else 0,
            "pubmed_publications_3yr": pub_count if not isinstance(pub_count, Exception) else 0,
            "fda_label_records": fda_count if not isinstance(fda_count, Exception) else 0,
            "disease_ontology": (
                [d.model_dump() for d in diseases]
                if not isinstance(diseases, Exception)
                else []
            ),
        }

    async def analyze_whitespace(self, condition: str) -> dict:
        """Identify underserved segments by comparing phase/status counts and approvals."""
        phases = ["1", "2", "3"]
        statuses = ["recruiting", "completed"]

        results = await asyncio.gather(
            *[self.ct.count_trials(condition=condition, phase=p) for p in phases],
            *[self.ct.count_trials(condition=condition, status=s) for s in statuses],
            self.pubmed.count_publications(condition=condition),
            self.fda.count_approved(condition=condition),
            return_exceptions=True,
        )

        phase_counts = {
            f"phase_{p}": (results[i] if not isinstance(results[i], Exception) else 0)
            for i, p in enumerate(phases)
        }
        status_counts = {
            s: (results[3 + i] if not isinstance(results[3 + i], Exception) else 0)
            for i, s in enumerate(statuses)
        }
        pub_count = results[6] if not isinstance(results[6], Exception) else 0
        fda_count = results[7] if not isinstance(results[7], Exception) else 0

        gaps: list[str] = []
        if phase_counts.get("phase_1", 0) < 5:
            gaps.append(
                f"Very few Phase 1 trials ({phase_counts['phase_1']}) — early-stage research may be limited."
            )
        if phase_counts.get("phase_3", 0) < 3:
            gaps.append(
                f"Few Phase 3 trials ({phase_counts['phase_3']}) — late-stage evidence may be lacking."
            )
        if fda_count == 0:
            gaps.append("No FDA label records found — potential whitespace for first-in-class approval.")
        elif fda_count < 3:
            gaps.append(f"Only {fda_count} FDA label records — limited approved options currently available.")
        if pub_count < 50:
            gaps.append(
                f"Low publication volume ({pub_count} in last 3 years) — under-researched area."
            )
        if status_counts.get("recruiting", 0) < 3:
            gaps.append(
                f"Few actively recruiting trials ({status_counts['recruiting']}) — limited enrollment opportunities."
            )

        return {
            "condition": condition,
            "trial_counts_by_phase": phase_counts,
            "trial_counts_by_status": status_counts,
            "pubmed_publications_3yr": pub_count,
            "fda_label_records": fda_count,
            "identified_whitespace": gaps,
        }

    async def get_sponsor_overview(self, condition: str, page_size: int = 25) -> dict:
        """Return trial counts grouped by sponsor for a condition."""
        trials = await self.ct.search_trials(disease_query=condition, page_size=page_size)
        sponsor_map: dict[str, int] = {}
        for trial in trials:
            sponsor = trial.sponsor or "Unknown"
            sponsor_map[sponsor] = sponsor_map.get(sponsor, 0) + 1

        sorted_sponsors = sorted(sponsor_map.items(), key=lambda x: x[1], reverse=True)
        return {
            "condition": condition,
            "total_trials_sampled": len(trials),
            "unique_sponsors": len(sponsor_map),
            "sponsor_trial_counts": [
                {"sponsor": s, "trial_count": c} for s, c in sorted_sponsors
            ],
        }

    async def answer_clinical_question(self, question: str) -> dict:
        return await self.llm.answer_question(question)

from __future__ import annotations

import time

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models import Citation, SourceTestResult, TrialRecord
from app.settings import settings
from app.utils import (
    compact_whitespace,
    dig,
    matches_any_text,
    split_inclusion_exclusion,
    unique_preserve_order,
)


class ClinicalTrialsV2Adapter:
    BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

    def __init__(self) -> None:
        self.timeout = settings.request_timeout_seconds
        self.headers = {
            "User-Agent": settings.user_agent,
            "Accept": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def search_trials(
        self,
        disease_query: str,
        page_size: int = 10,
        phase: str | None = None,
        sponsor: str | None = None,
        status: str | None = None,
    ) -> list[TrialRecord]:
        params: dict[str, str | int] = {
            "pageSize": page_size,
            "query.cond": disease_query,
            "query.term": disease_query,
        }

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.get(self.BASE_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()

        studies = payload.get("studies", [])
        rows = [self.normalize_study(study) for study in studies]

        if phase:
            rows = [r for r in rows if matches_any_text(r.phase, phase)]
        if sponsor:
            rows = [r for r in rows if sponsor.lower() in (r.sponsor or "").lower()]
        if status:
            rows = [r for r in rows if status.lower() in (r.status or "").lower()]

        return rows

    async def get_trial(self, nct_id: str) -> TrialRecord | None:
        url = f"{self.BASE_URL}/{nct_id}"
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            payload = resp.json()

        return self.normalize_study(payload)

    def normalize_study(self, study: dict) -> TrialRecord:
        identification = dig(study, ["protocolSection", "identificationModule"], {})
        status_module = dig(study, ["protocolSection", "statusModule"], {})
        design_module = dig(study, ["protocolSection", "designModule"], {})
        conditions_module = dig(study, ["protocolSection", "conditionsModule"], {})
        sponsor_module = dig(study, ["protocolSection", "sponsorCollaboratorsModule"], {})
        arms_module = dig(study, ["protocolSection", "armsInterventionsModule"], {})
        contacts_module = dig(study, ["protocolSection", "contactsLocationsModule"], {})
        eligibility_module = dig(study, ["protocolSection", "eligibilityModule"], {})
        outcomes_module = dig(study, ["protocolSection", "outcomesModule"], {})

        nct_id = identification.get("nctId")
        brief_title = identification.get("briefTitle")
        official_title = identification.get("officialTitle")

        conditions = unique_preserve_order(conditions_module.get("conditions", []) or [])
        keywords = unique_preserve_order(conditions_module.get("keywords", []) or [])
        phases = design_module.get("phases", []) or []
        enrollment_info = design_module.get("enrollmentInfo", {}) or {}

        interventions = []
        for item in arms_module.get("interventions", []) or []:
            name = item.get("name")
            if name:
                interventions.append(name)

        primary_outcomes = []
        for item in outcomes_module.get("primaryOutcomes", []) or []:
            measure = item.get("measure")
            if measure:
                primary_outcomes.append(measure)

        countries = []
        for loc in contacts_module.get("locations", []) or []:
            country = loc.get("country")
            if country:
                countries.append(country)

        criteria = compact_whitespace(eligibility_module.get("eligibilityCriteria"))
        inclusion, exclusion = split_inclusion_exclusion(criteria)

        return TrialRecord(
            source="ClinicalTrials.gov",
            source_id=nct_id or brief_title or "unknown",
            nct_id=nct_id,
            title=compact_whitespace(brief_title),
            official_title=compact_whitespace(official_title),
            disease=conditions,
            sponsor=compact_whitespace(dig(sponsor_module, ["leadSponsor", "name"])),
            collaborators=[
                c.get("name")
                for c in sponsor_module.get("collaborators", []) or []
                if c.get("name")
            ],
            phase=phases,
            status=compact_whitespace(status_module.get("overallStatus")),
            study_type=compact_whitespace(design_module.get("studyType")),
            enrollment=enrollment_info.get("count"),
            interventions=unique_preserve_order(interventions),
            primary_endpoints=unique_preserve_order(primary_outcomes),
            inclusion_criteria=inclusion,
            exclusion_criteria=exclusion,
            locations=unique_preserve_order(countries),
            start_date=dig(status_module, ["startDateStruct", "date"]),
            completion_date=dig(status_module, ["completionDateStruct", "date"]),
            keywords=keywords,
            citations=[
                Citation(
                    source="ClinicalTrials.gov",
                    id=nct_id,
                    url=f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else None,
                    title=brief_title,
                )
            ],
            raw=study,
        )

    async def healthcheck(self, sample_query: str = "melanoma") -> SourceTestResult:
        started = time.perf_counter()
        try:
            results = await self.search_trials(disease_query=sample_query, page_size=2)
            latency_ms = int((time.perf_counter() - started) * 1000)
            return SourceTestResult(
                source="clinicaltrials_v2",
                ok=True,
                latency_ms=latency_ms,
                records_found=len(results),
                sample_ids=[r.nct_id or r.source_id for r in results[:2]],
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return SourceTestResult(
                source="clinicaltrials_v2",
                ok=False,
                latency_ms=latency_ms,
                error=str(exc),
            )
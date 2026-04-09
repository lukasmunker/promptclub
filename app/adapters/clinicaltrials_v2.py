from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models import Citation, SourceTestResult, TrialRecord
from app.settings import settings
from app.utils import (
    compact_whitespace,
    dig,
    normalize_condition,
    split_inclusion_exclusion,
    unique_preserve_order,
)

# Valid filter.overallStatus values accepted by ClinicalTrials.gov v2
_STATUS_MAP: dict[str, str] = {
    "recruiting": "RECRUITING",
    "active": "ACTIVE_NOT_RECRUITING",
    "active_not_recruiting": "ACTIVE_NOT_RECRUITING",
    "completed": "COMPLETED",
    "not_yet_recruiting": "NOT_YET_RECRUITING",
    "not yet recruiting": "NOT_YET_RECRUITING",
    "terminated": "TERMINATED",
    "withdrawn": "WITHDRAWN",
    "suspended": "SUSPENDED",
    "enrolling_by_invitation": "ENROLLING_BY_INVITATION",
}


def _normalize_phase_term(phase: str) -> str:
    """Convert various phase inputs to ClinicalTrials query.term format (e.g. PHASE3)."""
    p = phase.strip().upper().replace(" ", "").replace("-", "")
    if p.startswith("PHASE"):
        return p
    if p.isdigit():
        return f"PHASE{p}"
    return p


def _normalize_status(status: str) -> str:
    return _STATUS_MAP.get(status.lower().strip(), status.upper())


def _strip_adverse_events(study: dict) -> dict:
    """Remove adverseEventsModule (~28k tokens) before storing in raw field."""
    results = study.get("resultsSection")
    if results and "adverseEventsModule" in results:
        cleaned = {k: v for k, v in results.items() if k != "adverseEventsModule"}
        return {**study, "resultsSection": cleaned}
    return study


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
        condition = normalize_condition(disease_query)

        params: dict[str, str | int] = {
            "query.cond": condition,
            "pageSize": page_size,
            "format": "json",
        }

        # Phase filter: use query.term which accepts PHASE1/PHASE2/PHASE3
        if phase:
            params["query.term"] = _normalize_phase_term(phase)

        # Sponsor filter: dedicated query.spons parameter
        if sponsor:
            params["query.spons"] = sponsor

        # Status filter: API-level filter (much more efficient than post-filter)
        if status:
            params["filter.overallStatus"] = _normalize_status(status)

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.get(self.BASE_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()

        studies = payload.get("studies", [])
        return [self.normalize_study(study) for study in studies]

    async def count_trials(
        self,
        condition: str,
        phase: str | None = None,
        status: str | None = None,
    ) -> int:
        """Return total trial count for a condition without fetching records."""
        normalized = normalize_condition(condition)
        params: dict[str, str | int] = {
            "query.cond": normalized,
            "countTotal": "true",
            "pageSize": 1,
            "format": "json",
        }
        if phase:
            params["query.term"] = _normalize_phase_term(phase)
        if status:
            params["filter.overallStatus"] = _normalize_status(status)

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
                resp = await client.get(self.BASE_URL, params=params)
                if resp.status_code == 200:
                    return resp.json().get("totalCount", 0)
        except Exception:
            pass
        return 0

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
        references_module = dig(study, ["protocolSection", "referencesModule"], {})

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

        # Extract PMIDs from referencesModule for NCT→Publication cross-referencing
        linked_pmids = unique_preserve_order([
            ref["pmid"]
            for ref in (references_module.get("references", []) or [])
            if ref.get("pmid")
        ])

        evidence: list[str] = []
        if nct_id:
            evidence.append(f"ctgov:{nct_id}")
        if linked_pmids:
            evidence.append(f"ctgov.referencesModule.pmids:{','.join(linked_pmids[:5])}")

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
            linked_pmids=linked_pmids,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            evidence_path=evidence,
            citations=[
                Citation(
                    source="ClinicalTrials.gov",
                    id=nct_id,
                    url=f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else None,
                    title=brief_title,
                )
            ],
            raw=_strip_adverse_events(study),
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

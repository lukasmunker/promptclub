from __future__ import annotations

import time
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models import Citation, SourceTestResult, TrialRecord
from app.settings import settings
from app.utils import compact_whitespace, unique_preserve_order


class ClinicalTrialsAdapter:
    BASE_URL = "https://clinicaltrials.gov/api/query/studies"

    def __init__(self) -> None:
        self.timeout = settings.request_timeout_seconds
        self.headers = {"User-Agent": settings.user_agent}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def search_trials(
        self,
        query: str,
        page_size: int = 10,
        phase: str | None = None,
        sponsor: str | None = None,
        status: str | None = None,
    ) -> list[TrialRecord]:
        params: dict[str, Any] = {
            "expr": query,
            "min_rnk": 1,
            "max_rnk": page_size,
            "fmt": "json",
        }

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.get(self.BASE_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()

        studies = payload.get("StudyFieldsResponse", {}).get("StudyFields", [])
        normalized = [self.normalize_study(study) for study in studies]

        if phase:
            normalized = [t for t in normalized if (t.phase or "").lower().find(phase.lower()) >= 0]
        if sponsor:
            normalized = [t for t in normalized if (t.sponsor or "").lower().find(sponsor.lower()) >= 0]
        if status:
            normalized = [t for t in normalized if (t.status or "").lower().find(status.lower()) >= 0]

        return normalized

    async def get_trial(self, nct_id: str) -> TrialRecord | None:
        records = await self.search_trials(query=nct_id, page_size=1)
        for record in records:
            if record.nct_id == nct_id or record.source_id == nct_id:
                return record
        return records[0] if records else None

    def normalize_study(self, study: dict[str, Any]) -> TrialRecord:
        nct_id = self._first(study.get("NCTId"))
        title = self._first(study.get("BriefTitle"))
        conditions = study.get("Condition", []) or []
        sponsor = self._first(study.get("LeadSponsorName"))
        phase = self._first(study.get("Phase"))
        status = self._first(study.get("OverallStatus"))
        study_type = self._first(study.get("StudyType"))
        interventions = study.get("InterventionName", []) or []
        enrollment = self._safe_int(self._first(study.get("EnrollmentCount")))
        locations = unique_preserve_order(study.get("LocationCountry", []) or [])
        start_date = self._first(study.get("StartDate"))
        completion_date = self._first(study.get("CompletionDate"))
        primary_outcomes = study.get("PrimaryOutcomeMeasure", []) or []
        eligibility = self._first(study.get("EligibilityCriteria"))

        return TrialRecord(
            source="ClinicalTrials.gov",
            source_id=nct_id or title or "unknown",
            nct_id=nct_id,
            title=compact_whitespace(title),
            disease=unique_preserve_order(conditions),
            sponsor=compact_whitespace(sponsor),
            phase=compact_whitespace(phase),
            status=compact_whitespace(status),
            study_type=compact_whitespace(study_type),
            enrollment=enrollment,
            interventions=unique_preserve_order(interventions),
            primary_endpoints=unique_preserve_order(primary_outcomes),
            inclusion_criteria=compact_whitespace(eligibility),
            exclusion_criteria=None,
            locations=locations,
            start_date=start_date,
            completion_date=completion_date,
            citations=[
                Citation(
                    source="ClinicalTrials.gov",
                    id=nct_id,
                    url=f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else None,
                    title=title,
                )
            ],
            raw=study,
        )

    async def healthcheck(self, sample_query: str = "melanoma") -> SourceTestResult:
        started = time.perf_counter()
        try:
            results = await self.search_trials(sample_query, page_size=2)
            latency_ms = int((time.perf_counter() - started) * 1000)
            return SourceTestResult(
                source="clinicaltrials",
                ok=True,
                latency_ms=latency_ms,
                records_found=len(results),
                sample_ids=[r.nct_id or r.source_id for r in results[:2]],
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return SourceTestResult(
                source="clinicaltrials",
                ok=False,
                latency_ms=latency_ms,
                error=str(exc),
            )

    @staticmethod
    def _first(values: list[str] | None) -> str | None:
        if not values:
            return None
        return values[0]

    @staticmethod
    def _safe_int(value: str | None) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
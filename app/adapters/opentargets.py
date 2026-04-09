from __future__ import annotations

import time

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models import (
    Citation,
    DiseaseResolutionRecord,
    KnownDrugRecord,
    SourceTestResult,
    TargetAssociationRecord,
)
from app.settings import settings


class OpenTargetsAdapter:
    BASE_URL = "https://api.platform.opentargets.org/api/v4/graphql"

    def __init__(self) -> None:
        self.timeout = settings.request_timeout_seconds
        self.headers = {
            "User-Agent": settings.user_agent,
            "Content-Type": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def resolve_disease(self, query: str, page_size: int = 5) -> list[DiseaseResolutionRecord]:
        gql = """
        query DiseaseSearch($queryString: String!, $index: Int!, $size: Int!) {
          search(
            queryString: $queryString
            entityNames: ["disease"]
            page: { index: $index, size: $size }
          ) {
            hits {
              id
              entity
              object {
                ... on Disease {
                  id
                  name
                  description
                }
              }
            }
          }
        }
        """
        variables = {"queryString": query, "index": 0, "size": page_size}

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.post(self.BASE_URL, json={"query": gql, "variables": variables})
            resp.raise_for_status()
            payload = resp.json()

        hits = payload.get("data", {}).get("search", {}).get("hits", []) or []
        out: list[DiseaseResolutionRecord] = []
        for hit in hits:
            obj = hit.get("object") or {}
            disease_id = obj.get("id") or hit.get("id")
            disease_name = obj.get("name")
            if disease_id and disease_name:
                out.append(
                    DiseaseResolutionRecord(
                        query=query,
                        disease_id=disease_id,
                        disease_name=disease_name,
                        entity=hit.get("entity"),
                        description=obj.get("description"),
                        citations=[
                            Citation(
                                source="Open Targets",
                                id=disease_id,
                                url=f"https://platform.opentargets.org/disease/{disease_id}",
                                title=disease_name,
                            )
                        ],
                        raw=hit,
                    )
                )
        return out

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_target_context(self, disease_id: str, page_size: int = 10) -> list[TargetAssociationRecord]:
        gql = """
        query DiseaseAssociations($efoId: String!, $size: Int!) {
          disease(efoId: $efoId) {
            id
            name
            associatedTargets(page: { index: 0, size: $size }) {
              rows {
                score
                target {
                  id
                  approvedSymbol
                  approvedName
                }
              }
            }
          }
        }
        """
        variables = {"efoId": disease_id, "size": page_size}

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.post(self.BASE_URL, json={"query": gql, "variables": variables})
            resp.raise_for_status()
            payload = resp.json()

        disease = payload.get("data", {}).get("disease")
        if not disease:
            return []

        rows = disease.get("associatedTargets", {}).get("rows", []) or []
        out: list[TargetAssociationRecord] = []
        for row in rows:
            target = row.get("target") or {}
            out.append(
                TargetAssociationRecord(
                    disease_id=disease.get("id"),
                    disease_name=disease.get("name"),
                    target_id=target.get("id"),
                    target_symbol=target.get("approvedSymbol"),
                    target_name=target.get("approvedName"),
                    score=row.get("score"),
                    citations=[
                        Citation(
                            source="Open Targets",
                            id=target.get("id"),
                            url=f"https://platform.opentargets.org/disease/{disease.get('id')}",
                            title=f"{disease.get('name')} target associations",
                        )
                    ],
                    raw=row,
                )
            )
        return out

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_known_drugs_for_target(
        self, ensembl_id: str, page_size: int = 25
    ) -> list[KnownDrugRecord]:
        """Return drugs developed against a target, with the diseases they treat
        and the trial identifiers from Open Targets ``drugAndClinicalCandidates``.

        This is the deterministic Drug↔Target↔Trial join: each row carries an
        evidence_path so the LLM never has to guess whether a drug from openFDA
        and an intervention name from CT.gov refer to the same molecule.

        ``page_size`` is applied client-side; Open Targets does not paginate this
        field at the GraphQL level for v4 (verified via schema introspection).
        """
        gql = """
        query KnownDrugsForTarget($ensemblId: String!) {
          target(ensemblId: $ensemblId) {
            id
            approvedSymbol
            drugAndClinicalCandidates {
              count
              rows {
                id
                maxClinicalStage
                drug {
                  id
                  name
                  drugType
                  maximumClinicalStage
                  tradeNames
                }
                diseases {
                  disease {
                    id
                    name
                  }
                }
                clinicalReports {
                  id
                  source
                  trialPhase
                  trialOverallStatus
                  url
                }
              }
            }
          }
        }
        """
        variables = {"ensemblId": ensembl_id}

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.post(self.BASE_URL, json={"query": gql, "variables": variables})
            resp.raise_for_status()
            payload = resp.json()

        target = (payload.get("data") or {}).get("target")
        if not target:
            return []

        target_id = target.get("id")
        target_symbol = target.get("approvedSymbol")
        all_candidates = (target.get("drugAndClinicalCandidates") or {}).get("rows", []) or []
        # Server returns the full list; clip client-side per page_size.
        candidates = all_candidates[:page_size]

        out: list[KnownDrugRecord] = []
        for row in candidates:
            drug = row.get("drug") or {}
            drug_id = drug.get("id")
            drug_name = drug.get("name")

            indications: list[str] = []
            indication_ids: list[str] = []
            for d in row.get("diseases", []) or []:
                d_obj = (d or {}).get("disease") or {}
                if d_obj.get("name"):
                    indications.append(d_obj["name"])
                if d_obj.get("id"):
                    indication_ids.append(d_obj["id"])

            trial_ids: list[str] = []
            trial_phases: list[str] = []
            for rep in row.get("clinicalReports", []) or []:
                rep_id = rep.get("id")
                if rep_id:
                    trial_ids.append(rep_id)
                phase = rep.get("trialPhase")
                if phase:
                    trial_phases.append(phase)

            evidence: list[str] = [f"opentargets:target/{target_id}"]
            if drug_id:
                evidence.append(f"opentargets:drug/{drug_id}")
            evidence.append("opentargets:drugAndClinicalCandidates")

            out.append(
                KnownDrugRecord(
                    target_id=target_id,
                    target_symbol=target_symbol,
                    drug_id=drug_id,
                    drug_name=drug_name,
                    drug_type=drug.get("drugType"),
                    max_clinical_stage=row.get("maxClinicalStage") or drug.get("maximumClinicalStage"),
                    trade_names=drug.get("tradeNames") or [],
                    indications=indications,
                    indication_ids=indication_ids,
                    trial_ids=trial_ids,
                    trial_phases=trial_phases,
                    evidence_path=evidence,
                    citations=[
                        Citation(
                            source="Open Targets",
                            id=drug_id,
                            url=(
                                f"https://platform.opentargets.org/drug/{drug_id}"
                                if drug_id
                                else f"https://platform.opentargets.org/target/{target_id}"
                            ),
                            title=drug_name or target_symbol,
                        )
                    ],
                    raw=row,
                )
            )
        return out

    async def healthcheck(self) -> SourceTestResult:
        started = time.perf_counter()
        try:
            resolved = await self.resolve_disease("melanoma", page_size=2)
            latency_ms = int((time.perf_counter() - started) * 1000)
            return SourceTestResult(
                source="opentargets",
                ok=True,
                latency_ms=latency_ms,
                records_found=len(resolved),
                sample_ids=[r.disease_id for r in resolved[:2]],
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return SourceTestResult(
                source="opentargets",
                ok=False,
                latency_ms=latency_ms,
                error=str(exc),
            )
from __future__ import annotations

import time
from urllib.parse import quote_plus

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models import Citation, RegulatoryRecord, SourceTestResult
from app.settings import settings
from app.utils import compact_whitespace, ensure_list, unique_preserve_order


class OpenFDAAdapter:
    BASE_URL = "https://api.fda.gov/drug/label.json"

    def __init__(self) -> None:
        self.timeout = settings.request_timeout_seconds
        self.headers = {"User-Agent": settings.user_agent}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def search_regulatory_context(self, drug_name: str, limit: int = 5) -> list[RegulatoryRecord]:
        search = quote_plus(f'openfda.brand_name:"{drug_name}"')
        url = f"{self.BASE_URL}?search={search}&limit={limit}"

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            payload = resp.json()

        results = payload.get("results", [])
        output: list[RegulatoryRecord] = []

        for item in results:
            openfda = item.get("openfda", {}) or {}
            brand_names = unique_preserve_order(ensure_list(openfda.get("brand_name")))
            sponsor_names = unique_preserve_order(ensure_list(openfda.get("manufacturer_name")))
            routes = unique_preserve_order(ensure_list(openfda.get("route")))
            substances = unique_preserve_order(ensure_list(openfda.get("substance_name")))
            application_numbers = unique_preserve_order(ensure_list(openfda.get("application_number")))

            output.append(
                RegulatoryRecord(
                    product_name=", ".join(brand_names) or None,
                    sponsor_name=", ".join(sponsor_names) or None,
                    application_number=", ".join(application_numbers) or None,
                    marketing_status=None,
                    indications_and_usage=compact_whitespace(
                        " ".join(ensure_list(item.get("indications_and_usage")))
                    ),
                    route=routes,
                    active_ingredients=substances,
                    warnings=compact_whitespace(" ".join(ensure_list(item.get("warnings")))),
                    citations=[
                        Citation(
                            source="openFDA",
                            id=", ".join(application_numbers) or None,
                            url="https://open.fda.gov/apis/drug/label/",
                            title=", ".join(brand_names) or drug_name,
                        )
                    ],
                    raw=item,
                )
            )

        return output

    async def count_approved(self, condition: str) -> int:
        """Return total number of FDA label records mentioning a condition."""
        search = quote_plus(f"indications_and_usage:{condition}")
        url = f"{self.BASE_URL}?search={search}&limit=1"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.json().get("meta", {}).get("results", {}).get("total", 0)
        except Exception:
            pass
        return 0

    async def healthcheck(self, sample_query: str = "Keytruda") -> SourceTestResult:
        started = time.perf_counter()
        try:
            results = await self.search_regulatory_context(sample_query, limit=2)
            latency_ms = int((time.perf_counter() - started) * 1000)
            return SourceTestResult(
                source="openfda",
                ok=True,
                latency_ms=latency_ms,
                records_found=len(results),
                sample_ids=[r.application_number or "unknown" for r in results[:2]],
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return SourceTestResult(
                source="openfda",
                ok=False,
                latency_ms=latency_ms,
                error=str(exc),
            )
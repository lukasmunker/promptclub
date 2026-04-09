from __future__ import annotations

import time

from app.models import Citation, SourceTestResult
from app.settings import settings


class WebContextAdapter:
    """
    Stub adapter.

    Wire this to Serper, Tavily, Brave Search, or a corporate search proxy.
    Keep it optional so the core system still works with official data sources only.
    """

    async def search_context(self, query: str, limit: int = 5) -> list[dict]:
        provider = (settings.web_search_provider or "").lower()
        if not settings.web_search_api_key:
            return []

        # Implement provider-specific logic here.
        # Returned schema suggestion:
        # [{"title": ..., "url": ..., "snippet": ..., "source": ...}]
        return [
            {
                "title": f"Stub result for {query}",
                "url": "https://example.com",
                "snippet": "Replace this stub with a real web-search provider.",
                "source": provider or "unknown",
                "citation": Citation(
                    source="Web search",
                    url="https://example.com",
                    title=f"Stub result for {query}",
                ).model_dump(),
            }
        ][:limit]

    async def healthcheck(self) -> SourceTestResult:
        started = time.perf_counter()
        results = await self.search_context("melanoma", limit=1)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return SourceTestResult(
            source="web_context",
            ok=bool(settings.web_search_api_key),
            latency_ms=latency_ms,
            records_found=len(results),
            sample_ids=[r["url"] for r in results[:1]],
            error=None if settings.web_search_api_key else "WEB_SEARCH_API_KEY not configured",
        )
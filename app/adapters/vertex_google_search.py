from __future__ import annotations

import json
import time
from typing import Any

from google import genai
from google.genai import types

from app.models import Citation, SourceTestResult, WebContextRecord
from app.settings import settings


class VertexGoogleSearchAdapter:
    def __init__(self) -> None:
        self.enabled = bool(
            settings.enable_vertex_web_search
            and settings.google_cloud_project
            and settings.google_genai_use_vertexai
        )

    def _build_client(self):
        return genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
            http_options=types.HttpOptions(api_version="v1"),
        )

    def _extract_citations(self, response: Any) -> list[Citation]:
        citations: list[Citation] = []
        try:
            data = json.loads(response.model_dump_json(exclude_none=True))
        except Exception:
            return citations

        candidates = data.get("candidates", []) or []
        for cand in candidates:
            grounding_metadata = cand.get("groundingMetadata", {}) or cand.get("grounding_metadata", {})
            chunks = grounding_metadata.get("groundingChunks", []) or grounding_metadata.get("grounding_chunks", [])
            for chunk in chunks:
                web = chunk.get("web", {}) or {}
                uri = web.get("uri")
                title = web.get("title")
                if uri or title:
                    citations.append(
                        Citation(
                            source="Vertex Google Search",
                            url=uri,
                            title=title,
                        )
                    )

        seen = set()
        deduped = []
        for c in citations:
            key = (c.url, c.title)
            if key not in seen:
                seen.add(key)
                deduped.append(c)
        return deduped

    async def search_context(self, query: str) -> list[WebContextRecord]:
        if not self.enabled:
            return []

        client = self._build_client()
        response = client.models.generate_content(
            model=settings.vertex_gemini_model,
            contents=(
                "Use Google Search grounding. Summarize only publicly available, non-speculative, "
                "oncology-relevant information and include grounded citations.\n\n"
                f"Query: {query}"
            ),
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            ),
        )

        citations = self._extract_citations(response)
        try:
            raw = json.loads(response.model_dump_json(exclude_none=True))
        except Exception:
            raw = {"text": getattr(response, "text", "")}

        return [
            WebContextRecord(
                answer=getattr(response, "text", "") or "",
                citations=citations,
                raw=raw,
            )
        ]

    async def healthcheck(self, sample_query: str = "latest melanoma immunotherapy developments") -> SourceTestResult:
        started = time.perf_counter()
        try:
            if not self.enabled:
                return SourceTestResult(
                    source="vertex_google_search",
                    ok=False,
                    latency_ms=0,
                    error="Vertex Google Search disabled or GCP project not configured",
                )

            rows = await self.search_context(sample_query)
            latency_ms = int((time.perf_counter() - started) * 1000)
            sample_ids = [c.url for r in rows for c in r.citations[:2] if c.url]
            return SourceTestResult(
                source="vertex_google_search",
                ok=True,
                latency_ms=latency_ms,
                records_found=len(rows),
                sample_ids=sample_ids[:2],
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return SourceTestResult(
                source="vertex_google_search",
                ok=False,
                latency_ms=latency_ms,
                error=str(exc),
            )
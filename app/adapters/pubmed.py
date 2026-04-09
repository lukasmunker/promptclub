from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models import Citation, PublicationRecord, SourceTestResult
from app.settings import settings
from app.utils import compact_whitespace, unique_preserve_order


class PubMedAdapter:
    ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    def __init__(self) -> None:
        self.timeout = settings.request_timeout_seconds
        self.headers = {"User-Agent": settings.user_agent}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def search_publications(self, query: str, page_size: int = 10) -> list[PublicationRecord]:
        pmids = await self._search_pmids(query=query, page_size=page_size)
        if not pmids:
            return []
        return await self._fetch_pmids(pmids)

    async def count_publications(self, condition: str, years: int = 3) -> int:
        """Return approximate PubMed article count for a condition over the last N years."""
        from datetime import datetime
        current_year = datetime.now().year
        params = {
            "db": "pubmed",
            "term": f"{condition}[MeSH Terms] OR {condition}[Title/Abstract]",
            "mindate": str(current_year - years),
            "maxdate": str(current_year),
            "retmax": "0",
            "retmode": "json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
                resp = await client.get(self.ESEARCH_URL, params=params)
                if resp.status_code == 200:
                    return int(resp.json().get("esearchresult", {}).get("count", 0))
        except Exception:
            pass
        return 0

    async def get_publications_for_trial(self, nct_id: str, page_size: int = 10) -> list[PublicationRecord]:
        return await self.search_publications(query=f'"{nct_id}"', page_size=page_size)

    async def _search_pmids(self, query: str, page_size: int) -> list[str]:
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": page_size,
            "retmode": "json",
        }
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.get(self.ESEARCH_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()

        return payload.get("esearchresult", {}).get("idlist", [])

    async def _fetch_pmids(self, pmids: list[str]) -> list[PublicationRecord]:
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
        }
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.get(self.EFETCH_URL, params=params)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)

        publications: list[PublicationRecord] = []

        for article in root.findall(".//PubmedArticle"):
            pmid = self._find_text(article, ".//PMID")
            title = self._find_text(article, ".//ArticleTitle")
            journal = self._find_text(article, ".//Journal/Title")
            year = self._find_text(article, ".//PubDate/Year")

            abstract_nodes = article.findall(".//Abstract/AbstractText")
            abstract_parts = []
            for node in abstract_nodes:
                txt = "".join(node.itertext()).strip()
                if txt:
                    abstract_parts.append(txt)

            authors = []
            for author in article.findall(".//Author"):
                fore = self._find_text(author, "./ForeName")
                last = self._find_text(author, "./LastName")
                full = " ".join(x for x in [fore, last] if x)
                if full:
                    authors.append(full)

            joined_text = " ".join([title or "", *abstract_parts])
            linked_trial_ids = unique_preserve_order(re.findall(r"\bNCT\d{8}\b", joined_text))

            publications.append(
                PublicationRecord(
                    pmid=pmid or "unknown",
                    title=compact_whitespace(title),
                    journal=compact_whitespace(journal),
                    pub_date=year,
                    abstract=compact_whitespace(" ".join(abstract_parts)),
                    authors=authors,
                    linked_trial_ids=linked_trial_ids,
                    citations=[
                        Citation(
                            source="PubMed",
                            id=pmid,
                            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
                            title=title,
                        )
                    ],
                    raw={"xml": ET.tostring(article, encoding="unicode")},
                )
            )

        return publications

    async def healthcheck(self, sample_query: str = "melanoma phase 3 trial") -> SourceTestResult:
        started = time.perf_counter()
        try:
            results = await self.search_publications(sample_query, page_size=2)
            latency_ms = int((time.perf_counter() - started) * 1000)
            return SourceTestResult(
                source="pubmed",
                ok=True,
                latency_ms=latency_ms,
                records_found=len(results),
                sample_ids=[r.pmid for r in results[:2]],
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return SourceTestResult(
                source="pubmed",
                ok=False,
                latency_ms=latency_ms,
                error=str(exc),
            )

    @staticmethod
    def _find_text(node, xpath: str) -> str | None:
        found = node.find(xpath)
        return found.text.strip() if found is not None and found.text else None
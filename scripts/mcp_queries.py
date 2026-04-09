"""Run a fixed set of natural-language oncology questions against the
clinical-intel MCP server.

The MCP server exposes structured tools, not an NL endpoint. This script
translates each question into a sequence of tool calls, collects the
structured results, and emits a machine- and human-readable report including
per-call latency, errors, and Vertex Gemini token usage.

Usage:
    .venv/bin/python scripts/mcp_queries.py [--url http://127.0.0.1:8080/mcp/]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


# Token-bucket keys we care about (Gemini 2.5 Flash reports several)
TOKEN_KEYS = [
    ("prompt", "promptTokenCount", "prompt_token_count"),
    ("candidates", "candidatesTokenCount", "candidates_token_count"),
    ("thoughts", "thoughtsTokenCount", "thoughts_token_count"),
    ("tool_use_prompt", "toolUsePromptTokenCount", "tool_use_prompt_token_count"),
    ("total", "totalTokenCount", "total_token_count"),
]


def _extract_json(content_list: Any) -> dict | None:
    for c in content_list or []:
        text = getattr(c, "text", None)
        if not text:
            continue
        try:
            return json.loads(text)
        except Exception:
            continue
    return None


def _extract_token_usage(parsed: dict | None) -> dict | None:
    if not parsed:
        return None
    for r in parsed.get("results") or []:
        raw = (r or {}).get("raw") or {}
        usage = raw.get("usageMetadata") or raw.get("usage_metadata")
        if usage:
            return usage
    return None


def _extract_trials(parsed: dict | None) -> list[dict]:
    """Extract trial records from either the legacy promptclub shape
    ({trials: [...]}) or the new viz-envelope shape from
    build_response_from_promptclub ({data: {results: [...]}, ui, sources, render_hint})."""
    if not parsed:
        return []
    if isinstance(parsed.get("data"), dict):
        return parsed["data"].get("results") or []
    if "trials" in parsed:
        return parsed.get("trials") or []
    return []


def _trial_phase(t: dict) -> list[str]:
    """Phase is list[str] in the legacy shape and a single string after viz normalization."""
    p = t.get("phase")
    if isinstance(p, list):
        return p
    if isinstance(p, str) and p:
        return [p]
    return []


def _trial_completion_date(t: dict) -> str | None:
    return t.get("completion_date") or t.get("primary_completion_date")


def _zero_tokens() -> dict[str, int]:
    return {k: 0 for k, *_ in TOKEN_KEYS}


def _add_tokens(acc: dict[str, int], usage: dict | None) -> None:
    if not usage:
        return
    for label, *aliases in TOKEN_KEYS:
        for a in aliases:
            v = usage.get(a)
            if v:
                acc[label] += int(v)
                break


class MCPRunner:
    def __init__(self, session: ClientSession) -> None:
        self.session = session
        self.calls: list[dict[str, Any]] = []  # full call log

    async def call(self, name: str, args: dict[str, Any]) -> dict | None:
        t0 = time.perf_counter()
        rec: dict[str, Any] = {"tool": name, "args": args}
        try:
            res = await self.session.call_tool(name, args)
            rec["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            rec["ok"] = not res.isError
            parsed = _extract_json(res.content)
            usage = _extract_token_usage(parsed)
            if usage:
                rec["token_usage"] = usage
            self.calls.append(rec)
            return parsed
        except Exception as exc:  # noqa: BLE001
            rec["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            rec["ok"] = False
            rec["error"] = f"{type(exc).__name__}: {exc}"
            self.calls.append(rec)
            return None


# ---------- Query handlers ----------

async def q1_phase3_melanoma(r: MCPRunner) -> dict[str, Any]:
    parsed = await r.call(
        "search_trials",
        {"disease_query": "melanoma", "phase": "PHASE3", "page_size": 25},
    )
    trials = _extract_trials(parsed)
    sponsors = Counter((t.get("sponsor") or "Unknown") for t in trials)
    return {
        "trial_count": len(trials),
        "sponsor_distribution": sponsors.most_common(),
        "trials": [
            {
                "nct_id": t.get("nct_id"),
                "title": t.get("title"),
                "sponsor": t.get("sponsor"),
                "phase": _trial_phase(t),
                "status": t.get("status"),
                "enrollment": t.get("enrollment"),
            }
            for t in trials
        ],
    }


async def q2_lung_2030(r: MCPRunner) -> dict[str, Any]:
    # Filter to RECRUITING + ACTIVE Phase-3 NSCLC trials only — these are the
    # ones whose readouts could plausibly inform a 2030 approval window.
    # The CT.gov API default sort isn't time-based, so we re-sort client-side
    # by start_date DESC to prioritize the most recently started trials.
    trials_p = await r.call(
        "search_trials",
        {
            "disease_query": "non-small cell lung cancer",
            "phase": "PHASE3",
            "status": "RECRUITING",
            "page_size": 25,
        },
    )
    web = await r.call(
        "web_context_search",
        {
            "query": (
                "non-small cell lung cancer therapies phase 3 clinical development "
                "FDA EMA approval pipeline 2025 2026 2027 sponsor pipeline"
            )
        },
    )
    trials = _extract_trials(trials_p)
    # Re-sort: most recently started Phase-3 trials first.
    trials = sorted(
        trials,
        key=lambda t: (t.get("start_date") or "0000"),
        reverse=True,
    )
    # web_context_search may also return the viz envelope; web results live in
    # data.results[] in the new shape, results[] in the old.
    web_results = (
        ((web or {}).get("data") or {}).get("results")
        or (web or {}).get("results")
        or []
    )
    return {
        "trial_count": len(trials),
        "trials": [
            {
                "nct_id": t.get("nct_id"),
                "title": t.get("title"),
                "sponsor": t.get("sponsor"),
                "phase": _trial_phase(t),
                "status": t.get("status"),
                "completion_date": _trial_completion_date(t),
                "snippet": t.get("snippet"),
            }
            for t in trials
        ],
        "web_context": [
            {
                "answer_excerpt": (w.get("answer") or "")[:1500],
                "citation_count": len(w.get("citations") or []),
            }
            for w in web_results
        ],
        "limitation": (
            "Tools return descriptive structured data only. Predicting market "
            "authorization is forward-looking; the orchestrator explicitly "
            "forbids speculative claims. Use sponsor pipeline + completion "
            "date as evidence, not a forecast."
        ),
    }


async def q3_breast_compare(r: MCPRunner) -> dict[str, Any]:
    # Filter to Phase 3 only — academic Phase 1/2 trials dominate the unfiltered
    # sample and obscure the sponsor-design comparison the question is asking for.
    parsed = await r.call(
        "search_trials",
        {"disease_query": "breast cancer", "phase": "PHASE3", "page_size": 30},
    )
    trials = _extract_trials(parsed)

    by_sponsor: dict[str, list[dict]] = defaultdict(list)
    for t in trials:
        by_sponsor[t.get("sponsor") or "Unknown"].append(t)

    comparison: list[dict[str, Any]] = []
    for sponsor, items in sorted(by_sponsor.items(), key=lambda kv: -len(kv[1])):
        phases: Counter = Counter()
        for it in items:
            phs = _trial_phase(it) or ["UNKNOWN"]
            for p in phs:
                phases[p] += 1
        # The viz layer collapses the original primary_endpoints[] into a
        # short prose `snippet`. Use that as the endpoint sample.
        endpoint_samples: list[str] = []
        for it in items:
            snip = it.get("snippet")
            if snip:
                endpoint_samples.append(snip)
        enrollments = [it.get("enrollment") for it in items if it.get("enrollment")]
        comparison.append(
            {
                "sponsor": sponsor,
                "trial_count": len(items),
                "phases": dict(phases),
                "median_enrollment": (
                    sorted(enrollments)[len(enrollments) // 2] if enrollments else None
                ),
                "endpoint_examples": endpoint_samples[:3],
                "nct_ids": [it.get("nct_id") for it in items],
            }
        )

    return {"trial_count": len(trials), "sponsors": comparison}


async def q4_white_spaces(r: MCPRunner) -> dict[str, Any]:
    # Use analyze_whitespace (server-side count_trials + count_publications +
    # count_approved) instead of search_trials with page_size cap. The previous
    # search_trials path always returned 25 (the cap), making counts useless
    # as a whitespace signal. analyze_whitespace queries the totalCount API
    # which is uncapped and returns real population sizes.
    indications = [
        "pancreatic cancer",
        "glioblastoma",
        "mesothelioma",
        "small cell lung cancer",
        "anal cancer",
        "gastric cancer",
        "cholangiocarcinoma",
        "uveal melanoma",
        "ovarian cancer",
        "non-small cell lung cancer",
    ]
    rows: list[dict[str, Any]] = []
    for ind in indications:
        parsed = await r.call("analyze_whitespace", {"condition": ind})
        # analyze_whitespace returns the viz envelope; the data lives under
        # data.* in the new shape, or at top level in the legacy shape.
        body = (parsed or {}).get("data") if isinstance(parsed, dict) else None
        if not body and isinstance(parsed, dict) and "trial_counts_by_phase" in parsed:
            body = parsed
        body = body or {}
        phase_counts = body.get("trial_counts_by_phase") or {}
        status_counts = body.get("trial_counts_by_status") or {}
        rows.append(
            {
                "indication": ind,
                "phase_1_count": phase_counts.get("phase_1", 0),
                "phase_2_count": phase_counts.get("phase_2", 0),
                "phase_3_count": phase_counts.get("phase_3", 0),
                "recruiting": status_counts.get("recruiting", 0),
                "completed": status_counts.get("completed", 0),
                "pubmed_3yr": body.get("pubmed_publications_3yr", 0),
                "fda_labels": body.get("fda_label_records", 0),
                "identified_whitespace": body.get("identified_whitespace") or [],
            }
        )
    # Rank by Phase 3 trial count (low → high) — the canonical "underserved" axis
    rows.sort(key=lambda r: r["phase_3_count"])
    return {
        "indications_scanned": len(indications),
        "method": "analyze_whitespace (uncapped CT.gov totalCount + PubMed + openFDA counts)",
        "ranking_low_to_high": rows,
        "interpretation": (
            "Indications with the fewest Phase 3 trials, lowest publication "
            "volume, and fewest FDA label records are candidate white spaces. "
            "Counts come from CT.gov totalCount endpoint (uncapped), PubMed "
            "esearch count (last 3 years), and openFDA drug/label count."
        ),
    }


async def q5_recruitment_speed(r: MCPRunner) -> dict[str, Any]:
    # Sample across multiple indications instead of a single "oncology" query.
    # The CT.gov default sort is non-temporal, so a single 30-trial sample is
    # heavily skewed; iterating across distinct disease queries gives a wider
    # cross-indication view of recruitment velocity.
    indications_to_sample = [
        "melanoma",
        "non-small cell lung cancer",
        "breast cancer",
        "pancreatic cancer",
    ]
    trials: list[dict] = []
    for ind in indications_to_sample:
        parsed = await r.call(
            "search_trials",
            {"disease_query": ind, "phase": "PHASE3", "page_size": 25},
        )
        ind_trials = _extract_trials(parsed)
        for t in ind_trials:
            t.setdefault("_indication", ind)
        trials.extend(ind_trials)

    def parse_year(s: str | None) -> int | None:
        if not s:
            return None
        try:
            return int(s[:4])
        except Exception:
            return None

    rows: list[dict[str, Any]] = []
    for t in trials:
        start = parse_year(t.get("start_date"))
        end = parse_year(_trial_completion_date(t))
        enrollment = t.get("enrollment")
        duration_y = (end - start) if (start and end) else None
        rate = (enrollment / duration_y) if (enrollment and duration_y and duration_y > 0) else None
        rows.append(
            {
                "nct_id": t.get("nct_id"),
                "indication": t.get("_indication"),
                "sponsor": t.get("sponsor"),
                "status": t.get("status"),
                "enrollment": enrollment,
                "start": start,
                "completion": end,
                "duration_years": duration_y,
                "patients_per_year": round(rate, 1) if rate else None,
            }
        )

    rates = [r["patients_per_year"] for r in rows if r["patients_per_year"]]
    rates_sorted = sorted(rates)
    median = rates_sorted[len(rates_sorted) // 2] if rates_sorted else None

    return {
        "trial_count": len(trials),
        "median_patients_per_year": median,
        "fastest": sorted(
            (r for r in rows if r["patients_per_year"]),
            key=lambda r: -r["patients_per_year"],
        )[:5],
        "slowest": sorted(
            (r for r in rows if r["patients_per_year"]),
            key=lambda r: r["patients_per_year"],
        )[:5],
        "caveats": [
            "Recruitment speed = enrollment / (completion_year - start_year). Coarse — uses years not days.",
            "completion_date may be projected, not actual; status field clarifies.",
            "Sample = up to 25 PHASE3 trials per indication × 4 indications. The CT.gov default sort is non-temporal so the sample is biased toward registry order, not chronology.",
        ],
    }


QUERIES = [
    ("Q1: Phase 3 melanoma trials and sponsors", q1_phase3_melanoma),
    ("Q2: Lung cancer therapies likely to reach approval by 2030", q2_lung_2030),
    ("Q3: Breast cancer trial design comparison across sponsors", q3_breast_compare),
    ("Q4: White spaces in cancer indications", q4_white_spaces),
    ("Q5: Patient recruitment speed in oncology", q5_recruitment_speed),
]


async def http_health(base_url: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=60) as client:
        for path in ("/health", "/health/sources"):
            t0 = time.perf_counter()
            try:
                r = await client.get(base_url.rstrip("/") + path)
                out[path] = {
                    "status": r.status_code,
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                }
            except Exception as exc:  # noqa: BLE001
                out[path] = {"error": f"{type(exc).__name__}: {exc}"}
    return out


async def main(mcp_url: str) -> int:
    base_http = mcp_url.replace("/mcp/", "").replace("/mcp", "").rstrip("/") or "http://127.0.0.1:8080"
    started_at = datetime.now(timezone.utc)
    report: dict[str, Any] = {
        "started_at": started_at.isoformat(),
        "mcp_url": mcp_url,
        "http_health_pre": await http_health(base_http),
        "queries": [],
    }

    print(f"[mcp-queries] Connecting to {mcp_url}")
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"[mcp-queries] {len(tools.tools)} tools available")

            grand_tokens = _zero_tokens()
            for label, handler in QUERIES:
                print(f"\n[mcp-queries] {label}")
                runner = MCPRunner(session)
                t0 = time.perf_counter()
                try:
                    answer = await handler(runner)
                    err = None
                except Exception as exc:  # noqa: BLE001
                    answer = None
                    err = f"{type(exc).__name__}: {exc}"
                elapsed = round((time.perf_counter() - t0) * 1000, 1)

                q_tokens = _zero_tokens()
                for c in runner.calls:
                    _add_tokens(q_tokens, c.get("token_usage"))
                for k in q_tokens:
                    grand_tokens[k] += q_tokens[k]

                ok = sum(1 for c in runner.calls if c.get("ok"))
                print(
                    f"  -> {len(runner.calls)} tool calls ({ok} ok)  "
                    f"{elapsed} ms  tokens(total)={q_tokens['total']}"
                )
                for c in runner.calls:
                    marker = "OK" if c.get("ok") else "FAIL"
                    print(f"     {marker:4s} {c['tool']:22s} {c['latency_ms']:>8.1f} ms")

                report["queries"].append(
                    {
                        "label": label,
                        "elapsed_ms": elapsed,
                        "calls": runner.calls,
                        "answer": answer,
                        "error": err,
                        "token_usage": q_tokens,
                    }
                )

    report["http_health_post"] = await http_health(base_http)
    finished_at = datetime.now(timezone.utc)
    report["finished_at"] = finished_at.isoformat()
    report["duration_s"] = round((finished_at - started_at).total_seconds(), 2)
    report["token_usage_total"] = grand_tokens

    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    out_path = log_dir / f"mcp_queries_{started_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))

    print()
    print("=" * 60)
    print("MCP QUERIES SUMMARY")
    print("=" * 60)
    for q in report["queries"]:
        ok = sum(1 for c in q["calls"] if c.get("ok"))
        print(
            f"  {q['label'][:55]:55s} "
            f"{ok}/{len(q['calls'])} ok  {q['elapsed_ms']:>8.1f} ms  "
            f"tok={q['token_usage']['total']}"
        )
    print(f"\nTotal token usage: {grand_tokens}")
    print(f"HTTP health pre  : {report['http_health_pre']}")
    print(f"HTTP health post : {report['http_health_post']}")
    print(f"Report file      : {out_path}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080/mcp/")
    ns = parser.parse_args()
    sys.exit(asyncio.run(main(ns.url)))

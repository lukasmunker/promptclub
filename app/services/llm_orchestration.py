from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

from app.citations import citations_from_rows
from app.models import Citation
from app.settings import settings
from app.utils import compact_whitespace, unique_preserve_order


if TYPE_CHECKING:
    from app.services.orchestration import Orchestrator


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _drop_none(item)
            for key, item in value.items()
            if item is not None and item != [] and item != {}
        }
    if isinstance(value, list):
        return [_drop_none(item) for item in value if item is not None]
    return value


def _truncate(text: str | None, max_chars: int = 320) -> str | None:
    text = compact_whitespace(text)
    if not text or len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3]}..."


@dataclass
class ToolExecutionResult:
    payload: dict[str, Any]
    citations: list[Citation]


class LLMToolOrchestrator:
    def __init__(self, orchestrator: Orchestrator) -> None:
        self.orchestrator = orchestrator

    def is_enabled(self) -> bool:
        return bool(
            settings.enable_llm_tool_orchestration
            and settings.openai_api_key
            and settings.openai_orchestrator_model
        )

    async def answer_question(self, question: str) -> dict[str, Any]:
        if not self.is_enabled():
            return await self._deterministic_fallback(
                question,
                reason="OpenAI orchestration is disabled or OPENAI_API_KEY is not configured.",
            )

        try:
            return await self._run_llm_tool_loop(question)
        except Exception as exc:
            fallback = await self._deterministic_fallback(
                question,
                reason="OpenAI orchestration failed; used deterministic fallback instead.",
            )
            fallback["llm_error"] = compact_whitespace(str(exc))
            return fallback

    async def _run_llm_tool_loop(self, question: str) -> dict[str, Any]:
        response = await self._create_response(
            input_items=[
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": question}],
                }
            ]
        )

        citations: list[Citation] = []
        tool_trace: list[dict[str, Any]] = []
        tool_outputs: list[dict[str, Any]] = []
        previous_response_id = response.get("id")

        for _ in range(settings.openai_orchestrator_max_steps):
            function_calls = self._extract_function_calls(response)
            if not function_calls:
                break

            executed = await asyncio.gather(
                *(self._execute_function_call(call) for call in function_calls)
            )

            outputs_for_model: list[dict[str, Any]] = []
            for call, result in zip(function_calls, executed):
                citations.extend(result.citations)
                tool_outputs.append(
                    {
                        "tool": call["name"],
                        "arguments": self._load_arguments(call.get("arguments")),
                        "result": result.payload,
                    }
                )
                tool_trace.append(
                    {
                        "tool": call["name"],
                        "arguments": self._load_arguments(call.get("arguments")),
                        "status": "ok",
                        "citation_count": len(result.citations),
                    }
                )
                outputs_for_model.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps(result.payload),
                    }
                )

            response = await self._create_response(
                input_items=outputs_for_model,
                previous_response_id=previous_response_id,
            )
            previous_response_id = response.get("id")

        deduped_citations = self.orchestrator.dedupe_citations(citations)
        answer = self._extract_output_text(response)
        if not answer:
            answer = self._summarize_tool_outputs(tool_outputs, question)

        if self._should_fallback_to_deterministic(tool_outputs, deduped_citations):
            fallback = await self._deterministic_fallback(
                question,
                reason="LLM tool orchestration returned insufficient evidence; used deterministic fallback instead.",
            )
            fallback["llm_mode"] = "llm_orchestrated_fallback"
            return fallback

        return {
            "mode": "llm_orchestrated",
            "model": settings.openai_orchestrator_model,
            "reasoning_effort": settings.openai_orchestrator_reasoning_effort,
            "answer": answer,
            "tool_trace": tool_trace,
            "tool_outputs": tool_outputs,
            "_citations": deduped_citations,
        }

    def _should_fallback_to_deterministic(
        self,
        tool_outputs: list[dict[str, Any]],
        citations: list[Citation],
    ) -> bool:
        if citations:
            return False
        if not tool_outputs:
            return True

        for item in tool_outputs:
            payload = item.get("result") or {}
            if payload.get("error"):
                continue
            if payload.get("found") is True:
                return False
            count = payload.get("count")
            if isinstance(count, int) and count > 0:
                return False
            results = payload.get("results")
            if isinstance(results, list) and results:
                return False
            trials = payload.get("trials")
            if isinstance(trials, list) and trials:
                return False
            trial_results = payload.get("trial_results")
            if isinstance(trial_results, list) and trial_results:
                return False
        return True

    async def _execute_function_call(self, call: dict[str, Any]) -> ToolExecutionResult:
        name = call["name"]
        arguments = self._load_arguments(call.get("arguments"))
        try:
            return await self._execute_tool(name, arguments)
        except Exception as exc:
            return ToolExecutionResult(
                payload={
                    "ok": False,
                    "error": compact_whitespace(str(exc)) or "tool execution failed",
                },
                citations=[],
            )

    async def _create_response(
        self,
        input_items: list[dict[str, Any]],
        previous_response_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": settings.openai_orchestrator_model,
            "reasoning": {"effort": settings.openai_orchestrator_reasoning_effort},
            "instructions": self._instructions(),
            "input": input_items,
            "tools": self._tool_definitions(),
            "parallel_tool_calls": True,
            "max_output_tokens": settings.openai_orchestrator_max_output_tokens,
        }
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id

        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        timeout = settings.openai_orchestrator_timeout_seconds
        url = f"{settings.openai_base_url.rstrip('/')}/responses"

        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    def _instructions(self) -> str:
        return (
            "You are the internal tool orchestrator for a clinical intelligence MCP server.\n"
            "Use the available tools to answer oncology-focused questions with grounded evidence.\n"
            "Rules:\n"
            "- Prefer the smallest number of tools that can answer the question well.\n"
            "- Use parallel tool calls when multiple independent sources are useful.\n"
            "- Do not speculate about outcomes, approvals, or strategy.\n"
            "- Resolve disease names before requesting target context unless the user already provided an EFO ID.\n"
            "- Use web_context_search for recent developments or news-like requests.\n"
            "- Avoid repeating the same tool call with the same arguments.\n"
            "- Once you have enough evidence, answer clearly and briefly."
        )

    def _tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": "search_trials",
                "description": "Find oncology trials by disease, phase, sponsor, or status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "disease_query": {"type": "string"},
                        "phase": {"type": "string"},
                        "sponsor": {"type": "string"},
                        "status": {"type": "string"},
                        "page_size": {"type": "integer"},
                    },
                    "required": ["disease_query"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_trial_details",
                "description": "Fetch one ClinicalTrials.gov record by NCT ID.",
                "parameters": {
                    "type": "object",
                    "properties": {"nct_id": {"type": "string"}},
                    "required": ["nct_id"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "search_publications",
                "description": "Search PubMed for publications related to a disease, therapy, sponsor, or NCT ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "page_size": {"type": "integer"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "resolve_disease",
                "description": "Resolve a free-text disease name to Open Targets EFO IDs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "page_size": {"type": "integer"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_target_context",
                "description": "Get target-disease associations for an Open Targets disease ID.",
                "parameters": {
                    "type": "object",
                    "properties": {"disease_id": {"type": "string"}},
                    "required": ["disease_id"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_regulatory_context",
                "description": "Get openFDA label and regulatory context for a drug.",
                "parameters": {
                    "type": "object",
                    "properties": {"drug_name": {"type": "string"}},
                    "required": ["drug_name"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "web_context_search",
                "description": "Get recent public web context for time-sensitive oncology questions.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "build_trial_comparison",
                "description": "Compare two or more trials side by side using NCT IDs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "nct_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        }
                    },
                    "required": ["nct_ids"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "analyze_indication_landscape",
                "description": "Get high-level trial, publication, FDA, and ontology counts for a condition.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "condition": {"type": "string"},
                        "phase": {"type": "string"},
                    },
                    "required": ["condition"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "analyze_whitespace",
                "description": "Identify whitespace or underserved areas in an indication.",
                "parameters": {
                    "type": "object",
                    "properties": {"condition": {"type": "string"}},
                    "required": ["condition"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_sponsor_overview",
                "description": "Get the most active trial sponsors for a condition.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "condition": {"type": "string"},
                        "page_size": {"type": "integer"},
                    },
                    "required": ["condition"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        ]

    def _extract_function_calls(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        output = response.get("output", []) or []
        return [item for item in output if item.get("type") == "function_call"]

    def _extract_output_text(self, response: dict[str, Any]) -> str:
        top_level = compact_whitespace(response.get("output_text"))
        if top_level:
            return top_level

        text_parts: list[str] = []
        for item in response.get("output", []) or []:
            if item.get("type") != "message":
                continue
            for content in item.get("content", []) or []:
                text = compact_whitespace(content.get("text"))
                if content.get("type") in {"output_text", "text"} and text:
                    text_parts.append(text)
        return "\n\n".join(text_parts)

    def _load_arguments(self, raw_arguments: Any) -> dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if not raw_arguments:
            return {}
        if isinstance(raw_arguments, str):
            return json.loads(raw_arguments)
        raise ValueError("unsupported tool argument payload")

    async def _execute_tool(self, name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        if name == "search_trials":
            result = await self.orchestrator.search_trials_with_publications(
                disease_query=arguments["disease_query"],
                phase=arguments.get("phase"),
                sponsor=arguments.get("sponsor"),
                status=arguments.get("status"),
                page_size=arguments.get("page_size", 10),
            )
            return ToolExecutionResult(
                payload={
                    "summary": result.summary,
                    "count": len(result.trials),
                    "trial_results": [self._trial_summary(t) for t in result.trials],
                    "publication_results": [self._publication_summary(p) for p in result.publications],
                    "web_context": [self._web_summary(row) for row in result.web_context],
                    "limitations": result.limitations,
                },
                citations=result.citations,
            )

        if name == "get_trial_details":
            record = await self.orchestrator.get_trial_details(arguments["nct_id"])
            if not record:
                return ToolExecutionResult(
                    payload={"found": False, "nct_id": arguments["nct_id"]},
                    citations=[],
                )
            return ToolExecutionResult(
                payload={"found": True, "trial": self._trial_summary(record, detailed=True)},
                citations=record.citations,
            )

        if name == "search_publications":
            rows = await self.orchestrator.search_publications(
                query=arguments["query"],
                page_size=arguments.get("page_size", 10),
            )
            return ToolExecutionResult(
                payload={
                    "count": len(rows),
                    "results": [self._publication_summary(row, detailed=True) for row in rows],
                },
                citations=citations_from_rows(rows),
            )

        if name == "resolve_disease":
            rows = await self.orchestrator.resolve_disease(
                query=arguments["query"],
                page_size=arguments.get("page_size", 5),
            )
            return ToolExecutionResult(
                payload={
                    "count": len(rows),
                    "results": [self._disease_summary(row) for row in rows],
                },
                citations=citations_from_rows(rows),
            )

        if name == "get_target_context":
            rows = await self.orchestrator.get_target_context(arguments["disease_id"])
            return ToolExecutionResult(
                payload={
                    "count": len(rows),
                    "results": [self._target_summary(row) for row in rows],
                },
                citations=citations_from_rows(rows),
            )

        if name == "get_regulatory_context":
            rows = await self.orchestrator.get_regulatory_context(arguments["drug_name"])
            return ToolExecutionResult(
                payload={
                    "count": len(rows),
                    "results": [self._regulatory_summary(row) for row in rows],
                },
                citations=citations_from_rows(rows),
            )

        if name == "web_context_search":
            rows = await self.orchestrator.web_context(arguments["query"])
            return ToolExecutionResult(
                payload={
                    "count": len(rows),
                    "results": [self._web_summary(row, detailed=True) for row in rows],
                },
                citations=citations_from_rows(rows),
            )

        if name == "build_trial_comparison":
            nct_ids = arguments["nct_ids"]
            tasks = [self.orchestrator.ct.get_trial(nct_id) for nct_id in nct_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            trials = []
            citations: list[Citation] = []
            errors = []
            for nct_id, result in zip(nct_ids, results):
                if isinstance(result, Exception):
                    errors.append({"nct_id": nct_id, "error": compact_whitespace(str(result))})
                elif result is None:
                    errors.append({"nct_id": nct_id, "error": "not found"})
                else:
                    trials.append(self._trial_summary(result, detailed=True))
                    citations.extend(result.citations)
            return ToolExecutionResult(
                payload={"count": len(trials), "trials": trials, "errors": errors},
                citations=citations,
            )

        if name == "analyze_indication_landscape":
            payload = await self.orchestrator.analyze_indication_landscape(
                condition=arguments["condition"],
                phase=arguments.get("phase"),
            )
            citations = []
            if payload.get("disease_ontology"):
                citations.extend(
                    [
                        Citation(
                            source="Open Targets",
                            id=item.get("disease_id"),
                            title=item.get("disease_name"),
                            url=f"https://platform.opentargets.org/disease/{item.get('disease_id')}",
                        )
                        for item in payload["disease_ontology"]
                        if item.get("disease_id")
                    ]
                )
            return ToolExecutionResult(payload=payload, citations=citations)

        if name == "analyze_whitespace":
            payload = await self.orchestrator.analyze_whitespace(condition=arguments["condition"])
            return ToolExecutionResult(payload=payload, citations=[])

        if name == "get_sponsor_overview":
            payload = await self.orchestrator.get_sponsor_overview(
                condition=arguments["condition"],
                page_size=arguments.get("page_size", 25),
            )
            return ToolExecutionResult(payload=payload, citations=[])

        raise ValueError(f"unknown tool: {name}")

    async def _deterministic_fallback(self, question: str, reason: str) -> dict[str, Any]:
        plan = self._deterministic_plan(question)
        tool_trace: list[dict[str, Any]] = []
        tool_outputs: list[dict[str, Any]] = []
        citations: list[Citation] = []
        last_payload: dict[str, Any] | None = None
        memory: dict[str, Any] = {}

        for step in plan:
            name = step["tool"]
            arguments = dict(step.get("arguments", {}))
            if name == "get_target_context" and arguments.get("disease_id") == "__from_last_resolution__":
                resolution = memory.get("resolve_disease") or {}
                first_match = ((resolution.get("results") or [])[:1] or [None])[0]
                disease_id = first_match.get("disease_id") if isinstance(first_match, dict) else None
                if not disease_id:
                    continue
                arguments["disease_id"] = disease_id

            result = await self._execute_tool(name, arguments)
            citations.extend(result.citations)
            last_payload = result.payload
            memory[name] = result.payload
            tool_trace.append(
                {
                    "tool": name,
                    "arguments": arguments,
                    "status": "ok",
                    "citation_count": len(result.citations),
                }
            )
            tool_outputs.append({"tool": name, "arguments": arguments, "result": result.payload})

        deduped_citations = self.orchestrator.dedupe_citations(citations)
        return {
            "mode": "deterministic_fallback",
            "fallback_reason": reason,
            "answer": self._summarize_tool_outputs(tool_outputs, question),
            "tool_trace": tool_trace,
            "tool_outputs": tool_outputs,
            "_citations": deduped_citations,
            "selected_tool": tool_trace[0]["tool"] if tool_trace else None,
            "selected_result": last_payload,
        }

    def _deterministic_plan(self, question: str) -> list[dict[str, Any]]:
        lowered = question.lower()
        nct_ids = unique_preserve_order(re.findall(r"\bNCT\d{8}\b", question.upper()))

        if len(nct_ids) >= 2:
            return [{"tool": "build_trial_comparison", "arguments": {"nct_ids": nct_ids}}]
        if len(nct_ids) == 1:
            return [{"tool": "get_trial_details", "arguments": {"nct_id": nct_ids[0]}}]
        if re.search(r"\b(latest|recent|news|developments?|update|updates|asco|esmo|press)\b", lowered):
            return [{"tool": "web_context_search", "arguments": {"query": question}}]
        if re.search(r"\b(target|targets|gene|genes|mechanism|mechanisms|protein|proteins)\b", lowered):
            disease_id_match = re.search(r"\bEFO[_:]\d+\b", question.upper())
            if disease_id_match:
                return [
                    {
                        "tool": "get_target_context",
                        "arguments": {
                            "disease_id": disease_id_match.group(0).replace(":", "_"),
                        },
                    }
                ]
            subject = self._extract_subject(question)
            return [
                {"tool": "resolve_disease", "arguments": {"query": subject, "page_size": 3}},
                {
                    "tool": "get_target_context",
                    "arguments": {"disease_id": "__from_last_resolution__"},
                },
            ]
        if re.search(r"\b(whitespace|underserved|gap|gaps|unmet need|unmet needs)\b", lowered):
            return [{"tool": "analyze_whitespace", "arguments": {"condition": self._extract_subject(question)}}]
        if re.search(r"\b(sponsor|sponsors|player|players|company|companies|competitive landscape)\b", lowered):
            return [{"tool": "get_sponsor_overview", "arguments": {"condition": self._extract_subject(question)}}]
        if re.search(r"\b(how many|landscape|research activity|space)\b", lowered):
            return [
                {
                    "tool": "analyze_indication_landscape",
                    "arguments": {"condition": self._extract_subject(question)},
                }
            ]
        if re.search(r"\b(publication|publications|paper|papers|literature|pubmed)\b", lowered):
            return [{"tool": "search_publications", "arguments": {"query": question, "page_size": 8}}]
        if re.search(r"\b(fda|approved|approval|label|regulatory)\b", lowered):
            return [{"tool": "get_regulatory_context", "arguments": {"drug_name": self._extract_subject(question)}}]
        return [{"tool": "search_trials", "arguments": {"disease_query": self._extract_subject(question)}}]

    def _extract_subject(self, question: str) -> str:
        cleaned = compact_whitespace(question) or ""
        replacements = [
            r"(?i)^find trials for ",
            r"(?i)^find papers about ",
            r"(?i)^find publications about ",
            r"(?i)^tell me about ",
            r"(?i)^who are the key players in ",
            r"(?i)^who are the sponsors in ",
            r"(?i)^where are the gaps in ",
            r"(?i)^where is the whitespace in ",
            r"(?i)^what targets are associated with ",
            r"(?i)^what is the regulatory context for ",
            r"(?i)^is ",
            r"(?i)^how big is the ",
        ]
        subject = cleaned
        for pattern in replacements:
            subject = re.sub(pattern, "", subject)
        subject = re.sub(r"(?i)\b(fda approved|approval status|approved|regulatory context)\b", "", subject)
        subject = re.sub(r"(?i)\?$", "", subject).strip()
        if subject.lower().endswith(" space"):
            subject = subject[:-6].strip()
        if subject.lower().endswith(" landscape"):
            subject = subject[:-10].strip()
        return subject or cleaned

    def _summarize_tool_outputs(self, tool_outputs: list[dict[str, Any]], question: str) -> str:
        if not tool_outputs:
            return f"No tool results were produced for: {question}"

        last = tool_outputs[-1]
        name = last["tool"]
        payload = last["result"]

        if name == "search_trials":
            count = payload.get("count", 0)
            return payload.get("summary") or f"Found {count} relevant trials."

        if name == "get_trial_details":
            if not payload.get("found"):
                return f"No trial record was found for {payload.get('nct_id', 'the requested NCT ID')}."
            trial = payload.get("trial", {})
            return (
                f"{trial.get('nct_id')}: {trial.get('title')}. "
                f"Status: {trial.get('status', 'unknown')}. "
                f"Sponsor: {trial.get('sponsor', 'unknown')}."
            )

        if name == "build_trial_comparison":
            return (
                f"Compared {payload.get('count', 0)} trials"
                + (f" with {len(payload.get('errors', []))} unresolved IDs." if payload.get("errors") else ".")
            )

        if name == "search_publications":
            return f"Found {payload.get('count', 0)} relevant PubMed publications."

        if name == "get_target_context":
            top = ((payload.get("results") or [])[:1] or [None])[0]
            if top:
                return (
                    f"Found {payload.get('count', 0)} target associations. "
                    f"Top hit: {top.get('target_symbol') or top.get('target_name')}."
                )
            return "No target associations were found."

        if name == "resolve_disease":
            first = ((payload.get("results") or [])[:1] or [None])[0]
            if first:
                return f"Resolved the disease to {first.get('disease_name')} ({first.get('disease_id')})."
            return "No disease ontology match was found."

        if name == "get_regulatory_context":
            first = ((payload.get("results") or [])[:1] or [None])[0]
            if first:
                return (
                    f"Found {payload.get('count', 0)} regulatory records for "
                    f"{first.get('product_name') or 'the requested drug'}."
                )
            return "No regulatory records were found."

        if name == "web_context_search":
            first = ((payload.get("results") or [])[:1] or [None])[0]
            if first and first.get("answer"):
                return first["answer"]
            return "No recent web context was returned."

        if name == "analyze_indication_landscape":
            return (
                f"{payload.get('condition')}: {payload.get('clinical_trials_count', 0)} trials, "
                f"{payload.get('pubmed_publications_3yr', 0)} publications in the last 3 years, and "
                f"{payload.get('fda_label_records', 0)} FDA label records."
            )

        if name == "analyze_whitespace":
            gaps = payload.get("identified_whitespace") or []
            if gaps:
                return gaps[0]
            return f"No major whitespace signals were identified for {payload.get('condition')}."

        if name == "get_sponsor_overview":
            top = ((payload.get("sponsor_trial_counts") or [])[:1] or [None])[0]
            if top:
                return (
                    f"Found {payload.get('unique_sponsors', 0)} sponsors. "
                    f"Most active: {top.get('sponsor')} with {top.get('trial_count')} trials."
                )
            return "No sponsor activity was found."

        return f"Completed {name} for: {question}"

    def _trial_summary(self, trial: Any, detailed: bool = False) -> dict[str, Any]:
        payload = {
            "nct_id": trial.nct_id,
            "title": trial.title,
            "official_title": trial.official_title if detailed else None,
            "disease": trial.disease[:6],
            "sponsor": trial.sponsor,
            "collaborators": trial.collaborators[:5] if detailed else None,
            "phase": trial.phase,
            "status": trial.status,
            "study_type": trial.study_type,
            "enrollment": trial.enrollment,
            "interventions": trial.interventions[:8],
            "primary_endpoints": trial.primary_endpoints[:5],
            "linked_pmids": trial.linked_pmids[:6],
            "locations": trial.locations[:6],
            "start_date": trial.start_date,
            "completion_date": trial.completion_date,
            "inclusion_criteria": _truncate(trial.inclusion_criteria, 500) if detailed else None,
            "exclusion_criteria": _truncate(trial.exclusion_criteria, 500) if detailed else None,
        }
        return _drop_none(payload)

    def _publication_summary(self, row: Any, detailed: bool = False) -> dict[str, Any]:
        payload = {
            "pmid": row.pmid,
            "title": row.title,
            "journal": row.journal,
            "pub_date": row.pub_date,
            "authors": row.authors[:8],
            "linked_trial_ids": row.linked_trial_ids[:6],
            "abstract": _truncate(row.abstract, 700 if detailed else 280),
        }
        return _drop_none(payload)

    def _disease_summary(self, row: Any) -> dict[str, Any]:
        return _drop_none(
            {
                "disease_id": row.disease_id,
                "disease_name": row.disease_name,
                "description": _truncate(row.description, 280),
            }
        )

    def _target_summary(self, row: Any) -> dict[str, Any]:
        return _drop_none(
            {
                "disease_id": row.disease_id,
                "disease_name": row.disease_name,
                "target_id": row.target_id,
                "target_symbol": row.target_symbol,
                "target_name": row.target_name,
                "score": row.score,
            }
        )

    def _regulatory_summary(self, row: Any) -> dict[str, Any]:
        return _drop_none(
            {
                "product_name": row.product_name,
                "sponsor_name": row.sponsor_name,
                "application_number": row.application_number,
                "indications_and_usage": _truncate(row.indications_and_usage, 420),
                "route": row.route[:5],
                "active_ingredients": row.active_ingredients[:6],
                "warnings": _truncate(row.warnings, 320),
            }
        )

    def _web_summary(self, row: Any, detailed: bool = False) -> dict[str, Any]:
        return _drop_none(
            {
                "answer": _truncate(row.answer, 1200 if detailed else 500),
            }
        )

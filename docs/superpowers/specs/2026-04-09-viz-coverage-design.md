# Visualization Coverage Guarantee — Design Spec

**Date:** 2026-04-09
**Branch:** `feat/llm-synthesis-expert-knowledge`
**Workstream:** 1 of 2 (companion: `2026-04-09-onkologie-lexikon-design.md`)
**Status:** Approved for implementation planning

---

## 1. Problem Statement

Today, the promptclub MCP server returns visualizations inconsistently. Some
queries get a chart or card; many do not. When no recipe matches, the envelope
layer in [app/viz/mcp_output.py](../../../app/viz/mcp_output.py) emits a
`[NO VISUALIZATION]` marker, the LLM has nothing to paste, and the user sees a
text-only answer.

The user requirement is unambiguous: **every answer must contain at least one
visual artifact**. Multiple visuals are welcome; zero is never acceptable.

The breakage is not localized to one place. The current architecture allows any
of three layers to silently bow out:

1. [app/viz/decision.py](../../../app/viz/decision.py) may return `None`
2. The viz builder may produce nothing
3. The envelope may write the `[NO VISUALIZATION]` marker

There is no single guarantor. The current investigation state is "we don't know
exactly where it breaks most often" — instrumentation must precede full
confidence in the fix scope.

## 2. Goals & Non-Goals

### Goals

- **Guarantee** that every MCP tool response produces an `:::artifact:::` block
  in the envelope output. Zero exceptions.
- Provide a **generic info-card fallback** that works with any Pydantic
  response, including empty ones.
- Provide **2–3 specialized fallback recipes** for the most common
  data-poor cases (definitions, single-entity lookups).
- **Instrument** the viz layer with a lightweight coverage log so the
  guarantee can be validated against real traffic and the long tail of
  fallback cases can be prioritized over time.
- Add a **regression ratchet** (audit script + test) that prevents new
  unguarded NO_VIZ paths from entering the codebase.

### Non-Goals

- Visual quality / aesthetics improvements. We guarantee *existence*, not
  *beauty*. The user pain identified is missing visuals, not ugly ones.
- LLM-side behavior changes. We do not retrain the LLM or restructure the
  system prompt beyond a single sentence acknowledging the new guarantee.
- Multi-artifact composition logic. If the LLM calls multiple tools, each
  response gets its own guaranteed artifact; ordering across tool calls is
  the LLM's job.
- Frontend / LibreChat changes. All work is server-side.
- Performance optimization. No bottleneck is expected; current Python
  rendering is fast enough.

## 3. Architecture

### Today (the broken state)

```
MCP Tool (app/main.py)
   │
   ▼
Orchestrator (app/services/orchestration.py)
   │  Pydantic models with citations + evidence_path
   ▼
Viz Decision Layer (app/viz/decision.py)
   │  ► returns Recipe OR None      ◄── failure point #1
   ▼
Viz Builder (app/viz/build.py + adapters.py)
   │  ► renders artifact OR nothing ◄── failure point #2
   ▼
Envelope (app/viz/mcp_output.py)
   │  ► assembles `:::artifact:::` OR `[NO VISUALIZATION]` ◄── failure point #3
   ▼
LLM (LibreChat client)
```

### Target (the guaranteed state)

```
┌──────────────────────────────────────────────────┐
│  ENVELOPE GUARANTEE (mcp_output.py)              │
│                                                  │
│  Input:  ToolResponse + best-effort recipe-pick  │
│  Output: ALWAYS an :::artifact::: block          │
│                                                  │
│  Strategy:                                       │
│    1. If specialized recipe rendered → use it    │
│    2. Else → fallback.pick_fallback_recipe()    │
│    3. Hard assert: artifact_block is not None    │
│    4. Catch RecipeBuildError → info_card        │
└──────────────────────────────────────────────────┘
```

The guarantor lives in the envelope layer. All upstream layers become
*best-effort* contributors whose failure is tolerated and logged.

### New Recipe Family

| Recipe | Trigger | Purpose |
|---|---|---|
| `concept-card` | Definitions / "what is" queries | 1 card with term + definition + citations |
| `single-entity-card` | Single trial / drug / disease lookup | 1 detail-rich card |
| `info-card` | Universal catch-all fallback | 1 simple card with title + bullets + citations |

`info-card` is the guarantor. It works with **any** `BaseToolResponse`,
including empty ones. When data is missing, it shows "No data found" plus the
original query and the sources that were checked.

## 4. Components

### New files

| Path | Purpose |
|---|---|
| `app/viz/recipes/info_card.py` | Universal fallback recipe. Renders Shadcn card from any BaseToolResponse. |
| `app/viz/recipes/concept_card.py` | Definition recipe. Inputs: term string + definition text + optional source URL. |
| `app/viz/recipes/single_entity_card.py` | Detail card for one entity (trial, drug, disease). |
| `app/viz/fallback.py` | `pick_fallback_recipe(response, query_hint) -> Recipe`. Heuristic: 1 entity → single-entity, query contains "what is/define" → concept, else → info-card. |
| `app/viz/coverage_log.py` | Lightweight JSONL logger writing `{ts, tool, recipe_chosen, fallback_used, reason}` to `logs/viz_coverage.jsonl`. |
| `tests/viz/test_envelope_guarantee.py` | Parametrized test asserting every MCP tool response (populated, empty, single-item) emits an artifact block. |
| `tests/viz/test_fallback_selection.py` | Tests for fallback heuristic. |
| `tests/viz/test_coverage_log.py` | Logger writes correct fields per call. |
| `scripts/audit_viz_paths.py` | Static AST scanner. Reports every path in app/main.py / app/viz/ that can return None or NO_VIZ. Outputs `logs/viz_audit.md`. |

### Changed files

| Path | Change |
|---|---|
| [app/viz/decision.py](../../../app/viz/decision.py) | `should_visualize()` becomes `pick_recipe()`. Always returns a Recipe instance, never `None`. The previous None path now calls `pick_fallback_recipe()`. |
| [app/viz/mcp_output.py](../../../app/viz/mcp_output.py) | `envelope_to_llm_text()`: NO_VIZ branch removed. Hard assert after recipe rendering: if artifact block is empty/None, falls through to `info_card` and writes a `coverage_log` entry with `fallback_used=True`. |
| [app/viz/adapters.py](../../../app/viz/adapters.py) | Existing Pydantic→Recipe normalizers may no longer silently return None. On failure they raise `RecipeBuildError`, caught in the envelope layer and routed to `info_card` fallback (logged). |
| [app/main.py](../../../app/main.py) | The 125-line `instructions=` block gets one new sentence: "Every tool response contains an `:::artifact:::` block. You MUST paste it. There is no `[NO VISUALIZATION]` case anymore." |

### Untouched

- Existing recipes (`gantt`, `html_cards`, `mermaid`, etc.) — they are fine;
  their fallback wiring was the problem, not their rendering.
- The LibreChat client / frontend.
- The adapter layer ([app/adapters/](../../../app/adapters/)). Coverage is a
  viz-layer concern, not an adapter concern.

## 5. Data Flow

### Happy path — query: "List active Phase 3 trials for Pembrolizumab"

```
1. LLM calls search_trials_with_publications
2. Orchestrator fan-out → ComparisonResponse with 12 trials
3. decision.pick_recipe() → "gantt" (>1 trial, valid dates)
4. build.render() → Mermaid markup
5. envelope_to_llm_text() → assembles :::artifact{type=mermaid}::: block
6. coverage_log.write({tool: "search_trials_with_publications", recipe: "gantt", fallback: false})
7. LLM pastes the block + 2-5 sentences of commentary
```

### Fallback path A — query: "What is RECIST?"

```
1. LLM calls search_pubmed (or vertex_google_search)
2. Orchestrator → response with definition text + 2 citations
3. decision.pick_recipe() → no specialized recipe matches
4. fallback.pick_fallback_recipe() detects definition pattern → "concept-card"
5. concept_card renders → Shadcn card with term, definition, citations
6. envelope_to_llm_text() → :::artifact{type=html}:::
7. coverage_log.write({recipe: "concept-card", fallback: true, reason: "no specialized match"})
```

### Fallback path B — query: adverse-event lookup with 0 events found

```
1. LLM calls search_adverse_events
2. Orchestrator → empty AdverseEventResponse with 0 events, query echo
3. decision.pick_recipe() → no specialized recipe (empty data)
4. fallback.pick_fallback_recipe() → "info-card" (catch-all)
5. info_card renders → card with title="No adverse events found",
   bullets=["Drug: X", "Sources checked: openfda, ema-eudra"], citations
6. envelope_to_llm_text() → :::artifact{type=html}:::
7. coverage_log.write({recipe: "info-card", fallback: true, reason: "empty result"})
```

### Failure path — recipe build crashes unexpectedly

```
1. ... → adapters.normalize() raises RecipeBuildError
2. envelope_to_llm_text() catches → uses info_card with raw response data
3. coverage_log.write({recipe: "info-card", fallback: true, reason: "RecipeBuildError: <msg>"})
4. NO uncaught exception bubbles to MCP client. Guarantee holds.
```

## 6. Edge Cases

| Case | Behavior |
|---|---|
| Tool response is `None` | Envelope builds info-card with "Tool returned no response" + tool name |
| Pydantic model has 0 records | info-card shows "No results", echoes query, lists sources consulted |
| Recipe builder raises | info-card as catch fallback, error in coverage_log |
| Multiple parallel tool calls from LLM | Each response goes through the envelope independently. Guarantee is per-tool-call, not per-answer. |
| Ambiguous user query (one-word term) | info-card with the term as title and "Search performed" as bullet |

## 7. Testing Strategy

### Coverage guarantee test (the keystone)

`tests/viz/test_envelope_guarantee.py` is the most important new test.
Parametrized over **every** MCP tool in [app/main.py](../../../app/main.py):

```python
@pytest.mark.parametrize("tool_name,response_factory", ALL_TOOL_RESPONSES)
def test_envelope_always_emits_artifact(tool_name, response_factory):
    response = response_factory()  # may be empty
    text = envelope_to_llm_text(response, tool_name=tool_name)
    assert ":::artifact" in text
    assert "[NO VISUALIZATION]" not in text
    assert "[NO DATA AVAILABLE]" not in text
```

Three response factories per tool: `populated()`, `empty()`, `single_item()`.
At 12 tools × 3 factories = 36 guaranteed coverage assertions.

### Fallback selection test

`tests/viz/test_fallback_selection.py` covers the heuristic in `app/viz/fallback.py`:

| Input | Expected recipe |
|---|---|
| Query "What is RECIST?" + 1 result | concept-card |
| Query "Tell me about NCT01234567" + 1 trial | single-entity-card |
| Query "list trials" + 0 results | info-card |
| Empty response, no query hint | info-card |
| RecipeBuildError raised upstream | info-card (catch path) |

### Recipe smoke tests

One smoke test per new recipe (`info_card`, `concept_card`, `single_entity_card`):

- Render with minimal input (only required fields)
- Render with rich input (all optional fields)
- Snapshot assertion on rendered HTML/markup so visual regressions surface

### Coverage log test

`tests/viz/test_coverage_log.py` ensures every envelope call writes a log
entry with the right fields (`tool`, `recipe_chosen`, `fallback_used`,
`reason`). Uses an in-memory test logger, no filesystem mock.

### Audit ratchet test

`scripts/audit_viz_paths.py` writes `logs/viz_audit.md`. A test verifies that
post-implementation the audit finds **zero** remaining NO_VIZ paths:

```python
def test_no_dead_paths_remain():
    audit = run_audit()
    assert audit.no_viz_paths == [], (
        f"Found {len(audit.no_viz_paths)} unguarded NO_VIZ paths: "
        f"{audit.no_viz_paths}"
    )
```

This is the regression ratchet.

### TDD ordering

The implementation plan should follow this order:

1. Write `test_envelope_guarantee.py` — runs red (today's guarantees are missing)
2. Build `info_card` recipe + fallback wiring — test goes green
3. Add `concept_card`, `single_entity_card` — specializations
4. Add audit script + `test_no_dead_paths_remain` — ratchet
5. Add `coverage_log` + test

### Out of test scope

- Visual quality / aesthetics
- LLM behavior with the artifact
- Performance benchmarks

## 8. Phasing

| Phase | Content | Verification |
|---|---|---|
| 0 | Write `scripts/audit_viz_paths.py`, run it, produce gap list | `logs/viz_audit.md` initial |
| 1 | `info_card` recipe + fallback wiring + `test_envelope_guarantee` | 36 tests green |
| 2 | `concept_card` + `single_entity_card` + heuristic | Fallback selection tests green |
| 3 | `coverage_log` + logging wiring | Logs appear in `logs/viz_coverage.jsonl` |
| 4 | Activate audit ratchet test, finalize NO_VIZ removal | Audit test green |
| 5 | Real-traffic validation: collect 1–2 days of logs, review | Manual review of JSONL |

## 9. Risks

| Risk | Mitigation |
|---|---|
| info-card feels overengineered for trivial answers | Accepted (explicit design decision). Can later be conditionally hidden in the frontend if needed. |
| Audit script misses a NO_VIZ path | `test_envelope_guarantee` is the second line of defense — even if the audit is incomplete, the tool-parametrized test catches it. |
| Fallback heuristic picks wrong recipe (e.g., info-card instead of concept-card) | Accepted in v1. If the coverage log shows frequent mismatches, the heuristic can be extended in v2. The *existence* guarantee still holds. |
| Existing recipe builders raise unexpectedly | Catch wrapper in envelope layer. `RecipeBuildError` is a new dedicated exception — caught explicitly, not generic `except Exception`. |
| Audit script CI runtime | Static AST analysis, no tool calls. <1s expected. |

## 10. Success Criteria

1. `test_envelope_guarantee` passes for all 12 MCP tools with all 3 response factories.
2. `test_no_dead_paths_remain` passes (zero unguarded NO_VIZ paths in code).
3. Real-traffic coverage log shows 100% of envelope calls produce an artifact block.
4. Manual spot-check: send 10 ad-hoc queries (mix of data-rich and data-poor), each result contains at least one visible artifact in LibreChat.

## 11. Open Questions

None at design-approval time. Implementation may surface details (exact match
of Pydantic field structures across the 12 tool responses) that get resolved
during phase 0 of the implementation plan.

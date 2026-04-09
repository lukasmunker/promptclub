# Visualization Coverage Guarantee — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guarantee that every MCP tool response from `app.main` produces an `:::artifact:::` block in the LLM-facing text output. Eliminate the `[NO VISUALIZATION]` and `[NO DATA AVAILABLE]` paths in [app/viz/mcp_output.py](../../../app/viz/mcp_output.py) by routing them through new fallback recipes.

**Architecture:** Three new general-purpose HTML recipes (`info_card`, `concept_card`, `single_entity_card`) plus a fallback dispatcher in [app/viz/build.py](../../../app/viz/build.py). The dispatcher catches every `Decision.skip(...)` and every `_maybe_no_data` shortcircuit and routes it to one of the new recipes — `info_card` is the universal catch-all. A coverage log tracks which path each response took, and an audit script + ratchet test prevents regressions.

**Tech Stack:** Python 3.12, FastMCP, Pydantic, pytest, existing `app.viz` package conventions (snake_case recipe names, HTML/Tailwind output via `escape_html` + `assert_safe_html`).

**Spec:** [docs/superpowers/specs/2026-04-09-viz-coverage-design.md](../specs/2026-04-09-viz-coverage-design.md)

---

## Merge Notes (post-merge from main, 2026-04-09)

After this plan was authored, three commits landed on `main` and were merged into the feature branch. Two of them affect WS1 directly:

1. **`5001d95 fix(mcp): force auto-visualization via in-band ACTION REQUIRED preamble`** — `app/viz/mcp_output.py:_format_with_artifact` now prepends a multi-line `ACTION REQUIRED — copy the :::artifact{…}::: block...` preamble before the artifact directive. The tool text no longer starts with `:::artifact`, it starts with `ACTION REQUIRED`. **This preamble must be preserved by Task 15** — the full file rewrite in that task has been adapted.
2. **`dfd7dd5 rename: mcp-yallah → Pharmafuse MCP`** — module docstrings were rebranded. Task 15's file rewrite uses the new name.
3. **`5001d95` also added** a `## ZERO-EXCEPTION RULE` subsection to the `instructions=` block in `app/main.py`. The block describing the artifact paste mandate is **already in place** and is stronger than what was originally planned. **Task 17 has been adapted** — instead of "add a sentence", it now deletes the obsolete `(2) [NO VISUALIZATION]` and `(3) [NO DATA AVAILABLE]` shape descriptions and trims section (1) to acknowledge the ACTION REQUIRED preamble.

Task 14's guarantee test uses `":::artifact" in text` (not `startswith`), so the new preamble does not break it.

`_maybe_no_data` still exists at `app/main.py:170+` after the merge — Task 11 still applies as written.

---

## File Structure

**New files:**

| Path | Responsibility |
|---|---|
| `app/viz/recipes/info_card.py` | Universal catch-all recipe. Renders any tool response as a Tailwind card with title + bullets + sources. Works on empty data. |
| `app/viz/recipes/concept_card.py` | Definition recipe. Renders one concept with term + definition + citations. |
| `app/viz/recipes/single_entity_card.py` | Single-entity recipe. Renders one trial / drug / disease / target as a detail card. |
| `app/viz/fallback.py` | `pick_fallback_recipe(tool_name, data, query_hint) -> str`. Heuristic that picks one of the three new recipes based on response shape and query intent. |
| `app/viz/coverage_log.py` | Append-only JSONL logger. One line per envelope assembly. |
| `tests/viz/test_envelope_guarantee.py` | Parametrized test: every MCP tool × {populated, empty, single_item} factory always emits an `:::artifact` block. |
| `tests/viz/test_fallback_selection.py` | Tests for `pick_fallback_recipe` heuristic. |
| `tests/viz/test_coverage_log.py` | Logger writes correct fields. |
| `tests/viz/test_audit_ratchet.py` | Runs `audit_viz_paths.py` and asserts zero unguarded SKIP paths remain. |
| `scripts/audit_viz_paths.py` | Static AST scanner for SKIP-returning code paths. Writes `logs/viz_audit.md`. |

**Changed files:**

| Path | Change |
|---|---|
| [app/viz/contract.py](../../../app/viz/contract.py) | Add `info_card`, `concept_card`, `single_entity_card` to the `RecipeName` Literal. |
| [app/viz/recipes/__init__.py](../../../app/viz/recipes/__init__.py) | Import and register the three new recipes in `REGISTRY`. |
| [app/viz/build.py](../../../app/viz/build.py) | `build_response()`: when `decision.kind == SKIP` or `recipe_name not in REGISTRY`, dispatch through `pick_fallback_recipe(...)` instead of producing a `ui=None` envelope. Always emit a `ui` payload. |
| [app/main.py](../../../app/main.py) | (a) Find `_maybe_no_data` (or whatever shortcircuits to the `[NO DATA AVAILABLE]` path) and route its result through `build_response` so it gets a fallback recipe. (b) Add one sentence to the `instructions=` block declaring the coverage guarantee. |
| [app/viz/mcp_output.py](../../../app/viz/mcp_output.py) | Once `build_response` always returns a `ui`-bearing envelope and `_maybe_no_data` is gone, the `_format_text_only` and `_format_no_data` branches become dead. Delete them and inline the artifact path. |

**Untouched:** Existing recipes (`indication_dashboard`, `sponsor_pipeline_cards`, `target_associations_table`, `trial_detail_tabs`, `trial_search_results`, `trial_timeline_gantt`, `whitespace_card`), the adapter layer, and the LibreChat client.

---

## Task Index

1. Pre-flight: read decision.py + mcp_output.py + main.py to confirm shape
2. Build the audit script (Phase 0)
3. Run the audit, record findings
4. Add new recipe names to `RecipeName` Literal
5. Build `info_card` recipe with TDD
6. Build `concept_card` recipe with TDD
7. Build `single_entity_card` recipe with TDD
8. Register new recipes in `REGISTRY`
9. Build `pick_fallback_recipe` with TDD
10. Eliminate SKIP path in `build_response`
11. Eliminate `_maybe_no_data` path (locate, redirect through `build_response`)
12. Build `coverage_log` module with TDD
13. Wire `coverage_log` into `build_response`
14. Build the envelope guarantee test
15. Delete dead branches in `mcp_output.py`
16. Build the audit ratchet test
17. Update LLM `instructions=` block in `main.py`
18. Final end-to-end smoke + commit

---

## Task 1: Pre-flight inspection

**Files:**
- Read: `app/main.py` (specifically the `instructions=` block and the `_maybe_no_data` helper)
- Read: `app/viz/mcp_output.py`
- Read: `app/viz/build.py`
- Read: `app/viz/decision.py`

- [ ] **Step 1: Locate `_maybe_no_data` in `app/main.py`**

Run: `grep -n "_maybe_no_data\|no_data" app/main.py | head -30`

Expected: at least one definition site and N call sites. Note them down.

- [ ] **Step 2: Confirm the SKIP-returning paths in `decision.py`**

Run: `grep -n "Decision.skip" app/viz/decision.py`

Expected: ~10 distinct SKIP sites covering the cases listed in section 3 of the spec (no results, single trivial hit, sparse trial detail, single-dimension aggregate, etc.).

- [ ] **Step 3: Confirm the FastMCP tool list**

Run: `grep -c "@mcp.tool()" app/main.py`

Expected: 13. (If different, update Task 14's parametrize list.)

- [ ] **Step 4: Confirm test runner**

Run: `python -m pytest tests/viz/ -q 2>&1 | tail -5`

Expected: existing tests pass. If any fail, stop and report — the baseline is broken.

- [ ] **Step 5: No commit** (read-only inspection task)

---

## Task 2: Build the audit script

**Files:**
- Create: `scripts/audit_viz_paths.py`
- Test: (none yet — Task 16 builds the ratchet test)

- [ ] **Step 1: Create the audit script**

Create `scripts/audit_viz_paths.py`:

```python
"""Static AST scan for SKIP-returning paths in app.viz.

Walks the AST of app/viz/decision.py and any module that constructs
Decision.skip(...) or returns ui=None. Writes a markdown report to
logs/viz_audit.md and returns a summary object.

Used by the regression ratchet test (tests/viz/test_audit_ratchet.py).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    REPO_ROOT / "app" / "viz" / "decision.py",
    REPO_ROOT / "app" / "viz" / "build.py",
    REPO_ROOT / "app" / "viz" / "mcp_output.py",
    REPO_ROOT / "app" / "main.py",
]


@dataclass
class SkipSite:
    file: str
    line: int
    snippet: str


@dataclass
class AuditResult:
    skip_sites: list[SkipSite] = field(default_factory=list)
    no_data_sites: list[SkipSite] = field(default_factory=list)

    @property
    def total_unguarded(self) -> int:
        return len(self.skip_sites) + len(self.no_data_sites)


def _scan_file(path: Path) -> tuple[list[SkipSite], list[SkipSite]]:
    skip_sites: list[SkipSite] = []
    no_data_sites: list[SkipSite] = []
    if not path.exists():
        return skip_sites, no_data_sites

    source = path.read_text()
    lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))

    for node in ast.walk(tree):
        # Decision.skip(...) calls
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "skip" and isinstance(node.func.value, ast.Name):
                if node.func.value.id == "Decision":
                    skip_sites.append(SkipSite(
                        file=str(path.relative_to(REPO_ROOT)),
                        line=node.lineno,
                        snippet=lines[node.lineno - 1].strip(),
                    ))
        # `no_data": True` literal dict patterns
        if isinstance(node, ast.Constant) and node.value == "no_data":
            no_data_sites.append(SkipSite(
                file=str(path.relative_to(REPO_ROOT)),
                line=node.lineno,
                snippet=lines[node.lineno - 1].strip(),
            ))

    return skip_sites, no_data_sites


def run_audit() -> AuditResult:
    result = AuditResult()
    for path in TARGETS:
        skips, no_datas = _scan_file(path)
        result.skip_sites.extend(skips)
        result.no_data_sites.extend(no_datas)
    return result


def write_report(result: AuditResult, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Visualization SKIP Path Audit",
        "",
        f"Total unguarded sites: **{result.total_unguarded}**",
        "",
        "## Decision.skip() sites",
        "",
    ]
    if not result.skip_sites:
        lines.append("_(none)_")
    for s in result.skip_sites:
        lines.append(f"- `{s.file}:{s.line}` — `{s.snippet}`")
    lines.append("")
    lines.append("## `no_data` literal sites")
    lines.append("")
    if not result.no_data_sites:
        lines.append("_(none)_")
    for s in result.no_data_sites:
        lines.append(f"- `{s.file}:{s.line}` — `{s.snippet}`")
    out.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    result = run_audit()
    write_report(result, REPO_ROOT / "logs" / "viz_audit.md")
    print(f"Audit complete: {result.total_unguarded} unguarded sites")
    print(f"Report: logs/viz_audit.md")
```

- [ ] **Step 2: Run the audit**

Run: `python scripts/audit_viz_paths.py`

Expected output:
```
Audit complete: <N> unguarded sites
Report: logs/viz_audit.md
```

Where `<N>` is non-zero (the current code has unguarded SKIP paths). Read `logs/viz_audit.md` to see the list.

- [ ] **Step 3: Commit**

```bash
git add scripts/audit_viz_paths.py
git commit -m "feat(viz): add static audit for unguarded SKIP paths

Scans app/viz/decision.py, build.py, mcp_output.py, and app/main.py
for Decision.skip() calls and 'no_data' literal markers. Writes
logs/viz_audit.md. Used as the regression ratchet for the coverage
guarantee work."
```

---

## Task 3: Run the audit and capture baseline

**Files:**
- Read: `logs/viz_audit.md`

- [ ] **Step 1: Read the audit report**

Run: `cat logs/viz_audit.md`

Expected: a list of every `Decision.skip(...)` call and every `no_data` literal currently in the codebase. Note the total — this is the baseline. Every one of these must either be eliminated or be routed through a fallback recipe by the time Task 16 runs.

- [ ] **Step 2: No commit** (the report is in `logs/` which is gitignored)

---

## Task 4: Add new recipe names to the `RecipeName` Literal

**Files:**
- Modify: `app/viz/contract.py`

- [ ] **Step 1: Write the failing test**

Create `tests/viz/test_new_recipe_names.py`:

```python
from app.viz.contract import RecipeName, ArtifactMeta, UiPayload

def test_info_card_is_a_valid_recipe_name():
    # Pydantic Literal validation: instantiating UiPayload with the new
    # recipe name must succeed.
    payload = UiPayload(
        recipe="info_card",
        artifact=ArtifactMeta(
            identifier="info-card-test",
            type="html",
            title="Test",
        ),
        raw="<div>test</div>",
    )
    assert payload.recipe == "info_card"


def test_concept_card_is_a_valid_recipe_name():
    payload = UiPayload(
        recipe="concept_card",
        artifact=ArtifactMeta(
            identifier="concept-card-test",
            type="html",
            title="Test",
        ),
        raw="<div>test</div>",
    )
    assert payload.recipe == "concept_card"


def test_single_entity_card_is_a_valid_recipe_name():
    payload = UiPayload(
        recipe="single_entity_card",
        artifact=ArtifactMeta(
            identifier="single-entity-card-test",
            type="html",
            title="Test",
        ),
        raw="<div>test</div>",
    )
    assert payload.recipe == "single_entity_card"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/viz/test_new_recipe_names.py -v`

Expected: FAIL with `validation error … Input should be 'indication_dashboard', 'trial_search_results', …`

- [ ] **Step 3: Add the names to the Literal**

Edit `app/viz/contract.py`. Find the `RecipeName = Literal[...]` definition and add three entries at the end:

```python
RecipeName = Literal[
    "indication_dashboard",
    "trial_search_results",
    "trial_detail_tabs",
    "trial_timeline_gantt",
    "sponsor_pipeline_cards",
    "target_associations_table",
    "whitespace_card",
    "info_card",
    "concept_card",
    "single_entity_card",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/viz/test_new_recipe_names.py -v`

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/viz/contract.py tests/viz/test_new_recipe_names.py
git commit -m "feat(viz): register info_card / concept_card / single_entity_card in RecipeName

Adds three new recipe names to the Pydantic Literal type. Recipe
implementations and registry wiring follow in subsequent commits."
```

---

## Task 5: Build `info_card` recipe (universal fallback)

**Files:**
- Create: `app/viz/recipes/info_card.py`
- Test: `tests/viz/test_recipes.py` (extend existing file)

- [ ] **Step 1: Write the failing test**

Append to `tests/viz/test_recipes.py`:

```python
from app.viz.recipes import info_card


def test_info_card_renders_with_minimal_input():
    """Empty data must produce a valid UiPayload — this is the universal
    catch-all for the coverage guarantee."""
    payload = info_card.build({}, sources=[])
    assert payload.recipe == "info_card"
    assert payload.artifact.type == "html"
    assert payload.raw is not None
    assert len(payload.raw) > 0


def test_info_card_renders_with_title_and_bullets():
    data = {
        "title": "Search Results",
        "bullets": ["12 trials found", "5 sponsors", "3 phases"],
        "subtitle": "Pembrolizumab in NSCLC",
    }
    payload = info_card.build(data, sources=[])
    assert "Search Results" in payload.raw
    assert "12 trials found" in payload.raw
    assert "Pembrolizumab in NSCLC" in payload.raw


def test_info_card_handles_empty_results():
    data = {
        "title": "No results",
        "subtitle": "Adverse events for drug X",
        "no_results_hint": "Sources checked: openfda, ema",
    }
    payload = info_card.build(data, sources=[])
    assert "No results" in payload.raw
    assert "Sources checked" in payload.raw


def test_info_card_escapes_html():
    data = {"title": "<script>alert(1)</script>"}
    payload = info_card.build(data, sources=[])
    assert "<script>" not in payload.raw
    assert "&lt;script&gt;" in payload.raw
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/viz/test_recipes.py::test_info_card_renders_with_minimal_input -v`

Expected: FAIL with `ImportError: cannot import name 'info_card'`.

- [ ] **Step 3: Implement the recipe**

Create `app/viz/recipes/info_card.py`:

```python
"""HTML recipe: universal catch-all info card.

This recipe is the visualization coverage guarantor. It accepts ANY
``data`` shape (including empty dicts) and produces a valid UiPayload
with a Tailwind-styled card. When no specialized recipe matches, the
fallback dispatcher in app.viz.fallback routes here.

Input shape (all optional):

    {
        "title": "Card title (defaults to 'Result')",
        "subtitle": "Optional subtitle",
        "bullets": ["fact 1", "fact 2"],         # rendered as a bullet list
        "no_results_hint": "Hint shown when bullets is empty",
    }
"""

from __future__ import annotations

from typing import Any

from app.viz.contract import ArtifactMeta, Source, UiPayload
from app.viz.utils.html import assert_safe_html, escape_html
from app.viz.utils.identifiers import make_identifier

__all__ = ["build"]


def build(
    data: dict[str, Any],
    sources: list[Source] | None = None,
) -> UiPayload:
    title = str(data.get("title") or "Result")
    subtitle = data.get("subtitle")
    bullets = data.get("bullets") or []
    hint = data.get("no_results_hint")

    body_parts: list[str] = []
    if subtitle:
        body_parts.append(
            f'<p class="text-sm text-gray-500">{escape_html(str(subtitle))}</p>'
        )

    if bullets:
        items = "\n      ".join(
            f"<li>{escape_html(str(b))}</li>" for b in bullets if b
        )
        body_parts.append(
            f'<ul class="mt-3 list-disc list-inside text-sm text-gray-800 space-y-1">\n      {items}\n    </ul>'
        )
    elif hint:
        body_parts.append(
            f'<p class="mt-3 text-sm italic text-gray-500">{escape_html(str(hint))}</p>'
        )
    else:
        body_parts.append(
            '<p class="mt-3 text-sm italic text-gray-500">No additional details available.</p>'
        )

    body = "\n    ".join(body_parts)

    raw = f"""<div class="p-4 font-sans rounded-lg border border-gray-200 bg-white">
  <header class="border-b border-gray-100 pb-2 mb-2">
    <h2 class="text-base font-semibold text-gray-900">{escape_html(title)}</h2>
  </header>
  <section>
    {body}
  </section>
</div>"""

    assert_safe_html(raw)

    return UiPayload(
        recipe="info_card",
        artifact=ArtifactMeta(
            identifier=make_identifier("info_card", title),
            type="html",
            title=title,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/viz/test_recipes.py -v -k info_card`

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/viz/recipes/info_card.py tests/viz/test_recipes.py
git commit -m "feat(viz): add info_card universal fallback recipe

Universal catch-all recipe used as the last-resort fallback in the
coverage guarantee dispatcher. Accepts any data shape including empty
dicts. Renders a Tailwind card with optional title, subtitle, bullets,
and a no-results hint."
```

---

## Task 6: Build `concept_card` recipe (definitions)

**Files:**
- Create: `app/viz/recipes/concept_card.py`
- Test: `tests/viz/test_recipes.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/viz/test_recipes.py`:

```python
from app.viz.recipes import concept_card


def test_concept_card_renders_definition():
    data = {
        "term": "RECIST 1.1",
        "definition": "Response Evaluation Criteria In Solid Tumors, version 1.1.",
        "category": "response-criterion",
    }
    payload = concept_card.build(data, sources=[])
    assert payload.recipe == "concept_card"
    assert "RECIST 1.1" in payload.raw
    assert "Response Evaluation Criteria" in payload.raw


def test_concept_card_renders_with_extended_context():
    data = {
        "term": "Overall Survival",
        "definition": "Time from randomization to death from any cause.",
        "context": "Considered the gold standard endpoint in oncology trials.",
    }
    payload = concept_card.build(data, sources=[])
    assert "Overall Survival" in payload.raw
    assert "gold standard" in payload.raw


def test_concept_card_handles_minimal_input():
    payload = concept_card.build({"term": "Phase 3"}, sources=[])
    assert "Phase 3" in payload.raw
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/viz/test_recipes.py -v -k concept_card`

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the recipe**

Create `app/viz/recipes/concept_card.py`:

```python
"""HTML recipe: definition / concept card.

Used by the fallback dispatcher when the user query is a "what is X" /
"define X" pattern and the response is essentially a single concept
explanation. Renders the term as a heading with a definition and
optional extended context underneath.

Input shape:

    {
        "term": "Required — the canonical term",
        "definition": "1-2 sentences",
        "context": "Optional 2-4 sentence extended explanation",
        "category": "Optional category tag (rendered as small badge)",
    }
"""

from __future__ import annotations

from typing import Any

from app.viz.contract import ArtifactMeta, Source, UiPayload
from app.viz.utils.html import assert_safe_html, escape_html
from app.viz.utils.identifiers import make_identifier

__all__ = ["build"]


def build(
    data: dict[str, Any],
    sources: list[Source] | None = None,
) -> UiPayload:
    term = str(data.get("term") or "Concept")
    definition = data.get("definition")
    context = data.get("context")
    category = data.get("category")

    badge_html = ""
    if category:
        badge_html = (
            f'<span class="ml-2 inline-block rounded bg-blue-50 text-blue-700 '
            f'border border-blue-200 px-2 py-0.5 text-xs uppercase tracking-wide">'
            f"{escape_html(str(category))}</span>"
        )

    definition_html = ""
    if definition:
        definition_html = (
            f'<p class="text-sm text-gray-800 mt-2">{escape_html(str(definition))}</p>'
        )

    context_html = ""
    if context:
        context_html = (
            f'<p class="text-sm text-gray-600 mt-3 leading-relaxed">'
            f"{escape_html(str(context))}</p>"
        )

    raw = f"""<div class="p-4 font-sans rounded-lg border border-gray-200 bg-white">
  <header class="border-b border-gray-100 pb-2 mb-2">
    <h2 class="text-base font-semibold text-gray-900 inline">{escape_html(term)}</h2>{badge_html}
  </header>
  <section>
    {definition_html}
    {context_html}
  </section>
</div>"""

    assert_safe_html(raw)

    return UiPayload(
        recipe="concept_card",
        artifact=ArtifactMeta(
            identifier=make_identifier("concept_card", term),
            type="html",
            title=term,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/viz/test_recipes.py -v -k concept_card`

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/viz/recipes/concept_card.py tests/viz/test_recipes.py
git commit -m "feat(viz): add concept_card recipe for definition queries

Used by the fallback dispatcher when the response represents a single
concept (term + definition + optional context). Replaces the
[NO VISUALIZATION] path for 'what is X' / 'define X' queries."
```

---

## Task 7: Build `single_entity_card` recipe

**Files:**
- Create: `app/viz/recipes/single_entity_card.py`
- Test: `tests/viz/test_recipes.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/viz/test_recipes.py`:

```python
from app.viz.recipes import single_entity_card


def test_single_entity_card_renders_a_trial():
    data = {
        "kind": "trial",
        "title": "NCT01234567",
        "subtitle": "A Phase 3 study of pembrolizumab in NSCLC",
        "facts": [
            ("Phase", "3"),
            ("Status", "Recruiting"),
            ("Sponsor", "Merck"),
            ("Enrollment", "2,500"),
        ],
    }
    payload = single_entity_card.build(data, sources=[])
    assert payload.recipe == "single_entity_card"
    assert "NCT01234567" in payload.raw
    assert "Phase" in payload.raw
    assert "Recruiting" in payload.raw
    assert "Merck" in payload.raw


def test_single_entity_card_renders_a_drug():
    data = {
        "kind": "drug",
        "title": "Pembrolizumab",
        "subtitle": "PD-1 inhibitor",
        "facts": [
            ("Class", "Monoclonal antibody"),
            ("Approval", "FDA approved 2014"),
        ],
    }
    payload = single_entity_card.build(data, sources=[])
    assert "Pembrolizumab" in payload.raw
    assert "PD-1 inhibitor" in payload.raw


def test_single_entity_card_handles_no_facts():
    data = {"kind": "trial", "title": "NCT00000000"}
    payload = single_entity_card.build(data, sources=[])
    assert "NCT00000000" in payload.raw
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/viz/test_recipes.py -v -k single_entity_card`

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the recipe**

Create `app/viz/recipes/single_entity_card.py`:

```python
"""HTML recipe: single-entity detail card.

Used by the fallback dispatcher when the response represents one
identifiable entity (one trial, one drug, one disease, one target).
Renders a title, subtitle, and a key/value facts table.

Input shape:

    {
        "kind": "trial" | "drug" | "disease" | "target" (used for icon hint),
        "title": "Required — the entity name or ID",
        "subtitle": "Optional one-line description",
        "facts": [("Key", "Value"), ...],   # ordered key/value pairs
    }
"""

from __future__ import annotations

from typing import Any

from app.viz.contract import ArtifactMeta, Source, UiPayload
from app.viz.utils.html import assert_safe_html, escape_html
from app.viz.utils.identifiers import make_identifier

__all__ = ["build"]


def build(
    data: dict[str, Any],
    sources: list[Source] | None = None,
) -> UiPayload:
    kind = str(data.get("kind") or "entity")
    title = str(data.get("title") or "Entity")
    subtitle = data.get("subtitle")
    facts = data.get("facts") or []

    subtitle_html = ""
    if subtitle:
        subtitle_html = (
            f'<p class="text-sm text-gray-500 mt-1">{escape_html(str(subtitle))}</p>'
        )

    facts_html = ""
    if facts:
        rows = "\n        ".join(
            f"""<div class="flex justify-between border-b border-gray-100 py-1.5">
          <span class="text-xs uppercase tracking-wide text-gray-500">{escape_html(str(k))}</span>
          <span class="text-sm font-medium text-gray-900 text-right">{escape_html(str(v))}</span>
        </div>"""
            for k, v in facts if k
        )
        facts_html = (
            f'<dl class="mt-3 space-y-0">\n        {rows}\n      </dl>'
        )

    raw = f"""<div class="p-4 font-sans rounded-lg border border-gray-200 bg-white">
  <header class="border-b border-gray-100 pb-2 mb-2">
    <p class="text-xs uppercase tracking-wide text-gray-400">{escape_html(kind)}</p>
    <h2 class="text-base font-semibold text-gray-900">{escape_html(title)}</h2>
    {subtitle_html}
  </header>
  <section>
    {facts_html}
  </section>
</div>"""

    assert_safe_html(raw)

    return UiPayload(
        recipe="single_entity_card",
        artifact=ArtifactMeta(
            identifier=make_identifier("single_entity_card", title),
            type="html",
            title=title,
        ),
        components=None,
        layout=None,
        blueprint=None,
        raw=raw,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/viz/test_recipes.py -v -k single_entity_card`

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/viz/recipes/single_entity_card.py tests/viz/test_recipes.py
git commit -m "feat(viz): add single_entity_card recipe for one-entity lookups

Used by the fallback dispatcher when the response represents one
identifiable trial, drug, disease, or target. Renders a key/value
facts table inside a Tailwind card."
```

---

## Task 8: Register the new recipes in `REGISTRY`

**Files:**
- Modify: `app/viz/recipes/__init__.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/viz/test_recipes.py`:

```python
def test_new_recipes_in_registry():
    from app.viz.recipes import REGISTRY

    assert "info_card" in REGISTRY
    assert "concept_card" in REGISTRY
    assert "single_entity_card" in REGISTRY

    # Each registry entry must be a callable that produces a UiPayload
    for name in ("info_card", "concept_card", "single_entity_card"):
        builder = REGISTRY[name]
        payload = builder({}, sources=[])
        assert payload.recipe == name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/viz/test_recipes.py::test_new_recipes_in_registry -v`

Expected: FAIL with `AssertionError: 'info_card' not in REGISTRY`.

- [ ] **Step 3: Update the registry**

Edit `app/viz/recipes/__init__.py`. Add three imports and three registry entries:

```python
"""Recipe builders — one per visualization kind.

Each recipe exposes a ``build(data)`` function that takes a tool result dict
and returns a ``UiPayload``. Recipes know nothing about MCP internals — they
just transform data shapes into envelope pieces.
"""

from app.viz.recipes import (
    concept_card,
    indication_dashboard,
    info_card,
    single_entity_card,
    sponsor_pipeline_cards,
    target_associations_table,
    trial_detail_tabs,
    trial_search_results,
    trial_timeline_gantt,
    whitespace_card,
)

# Registry: recipe name → build function. Used by build.py to dispatch.
REGISTRY = {
    "indication_dashboard": indication_dashboard.build,
    "trial_search_results": trial_search_results.build,
    "trial_detail_tabs": trial_detail_tabs.build,
    "trial_timeline_gantt": trial_timeline_gantt.build,
    "sponsor_pipeline_cards": sponsor_pipeline_cards.build,
    "target_associations_table": target_associations_table.build,
    "whitespace_card": whitespace_card.build,
    "info_card": info_card.build,
    "concept_card": concept_card.build,
    "single_entity_card": single_entity_card.build,
}

__all__ = [
    "REGISTRY",
    "concept_card",
    "indication_dashboard",
    "info_card",
    "single_entity_card",
    "sponsor_pipeline_cards",
    "target_associations_table",
    "trial_detail_tabs",
    "trial_search_results",
    "trial_timeline_gantt",
    "whitespace_card",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/viz/test_recipes.py -v`

Expected: all tests pass, including `test_new_recipes_in_registry`.

- [ ] **Step 5: Commit**

```bash
git add app/viz/recipes/__init__.py tests/viz/test_recipes.py
git commit -m "feat(viz): register info_card, concept_card, single_entity_card

The three new fallback recipes are now dispatchable via REGISTRY[name]
and the build_response() pipeline can pick them by name."
```

---

## Task 9: Build `pick_fallback_recipe` heuristic

**Files:**
- Create: `app/viz/fallback.py`
- Create: `tests/viz/test_fallback_selection.py`

- [ ] **Step 1: Write the failing test**

Create `tests/viz/test_fallback_selection.py`:

```python
"""Tests for the fallback recipe selector.

The selector is the bridge between the SKIP path in build_response and
the new fallback recipes. It must always return a valid recipe name —
the universal default is 'info_card'.
"""

from app.viz.fallback import pick_fallback_recipe, build_fallback_data


# --- Recipe selection -------------------------------------------------------


def test_definition_query_picks_concept_card():
    name = pick_fallback_recipe(
        tool_name="search_publications",
        data={"results": [{"abstract": "RECIST is..."}]},
        query_hint="What is RECIST?",
    )
    assert name == "concept_card"


def test_define_query_picks_concept_card():
    name = pick_fallback_recipe(
        tool_name="search_publications",
        data={},
        query_hint="define progression-free survival",
    )
    assert name == "concept_card"


def test_single_trial_lookup_picks_single_entity_card():
    name = pick_fallback_recipe(
        tool_name="get_trial_details",
        data={"nct_id": "NCT01234567", "title": "Phase 3 study"},
        query_hint=None,
    )
    assert name == "single_entity_card"


def test_empty_response_picks_info_card():
    name = pick_fallback_recipe(
        tool_name="search_clinical_trials",
        data={"results": []},
        query_hint="any query",
    )
    assert name == "info_card"


def test_unknown_tool_picks_info_card():
    name = pick_fallback_recipe(
        tool_name="some_random_tool",
        data={"foo": "bar"},
        query_hint=None,
    )
    assert name == "info_card"


def test_no_query_hint_picks_info_card():
    name = pick_fallback_recipe(
        tool_name="search_clinical_trials",
        data={"results": [{"id": "x"}, {"id": "y"}]},
        query_hint=None,
    )
    assert name == "info_card"


# --- Fallback data shaping --------------------------------------------------


def test_build_fallback_data_for_info_card_uses_tool_name():
    data = build_fallback_data(
        recipe_name="info_card",
        tool_name="search_clinical_trials",
        original_data={"results": []},
        query_hint="pembrolizumab in NSCLC",
    )
    assert data["title"]
    assert "search_clinical_trials" in data["title"] or "Result" in data["title"]
    # The query hint should appear so the LLM has context
    assert data.get("subtitle") or data.get("no_results_hint")


def test_build_fallback_data_for_concept_card_extracts_term():
    data = build_fallback_data(
        recipe_name="concept_card",
        tool_name="search_publications",
        original_data={},
        query_hint="What is RECIST 1.1?",
    )
    assert data.get("term")
    assert "RECIST" in data["term"]


def test_build_fallback_data_for_single_entity_card_extracts_facts():
    data = build_fallback_data(
        recipe_name="single_entity_card",
        tool_name="get_trial_details",
        original_data={
            "nct_id": "NCT01234567",
            "title": "A Phase 3 study",
            "phase": "Phase 3",
            "sponsor": "Merck",
        },
        query_hint=None,
    )
    assert data.get("title") == "NCT01234567" or data.get("title") == "A Phase 3 study"
    assert data.get("facts")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/viz/test_fallback_selection.py -v`

Expected: FAIL with `ImportError: cannot import name 'pick_fallback_recipe' from 'app.viz.fallback'`.

- [ ] **Step 3: Implement the fallback selector**

Create `app/viz/fallback.py`:

```python
"""Fallback recipe selector and data shaper.

When the primary decision logic in app.viz.decision returns
``Decision.skip(...)``, this module steps in and picks one of the three
fallback recipes (``info_card``, ``concept_card``, ``single_entity_card``)
to guarantee that the envelope always contains a visualization.

The selector is intentionally simple — small heuristics on the query
hint and the data shape. It is NOT NLP. The point is determinism, not
sophistication. ``info_card`` is the universal default.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["pick_fallback_recipe", "build_fallback_data"]


# Phrases that strongly indicate a definition / "what is X" query
_DEFINITION_PATTERNS = [
    re.compile(r"\bwhat\s+is\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+are\b", re.IGNORECASE),
    re.compile(r"\bdefine\b", re.IGNORECASE),
    re.compile(r"\bdefinition\s+of\b", re.IGNORECASE),
    re.compile(r"\bexplain\b", re.IGNORECASE),
    re.compile(r"\bmeaning\s+of\b", re.IGNORECASE),
]

# Tools that return single-entity detail records when called
_SINGLE_ENTITY_TOOLS = {
    "get_trial_details",
    "get_target_context",
    "get_sponsor_overview",
}


def pick_fallback_recipe(
    tool_name: str,
    data: dict[str, Any],
    query_hint: str | None,
) -> str:
    """Pick which fallback recipe should render this response.

    Returns one of: ``"info_card"``, ``"concept_card"``,
    ``"single_entity_card"``. Never returns None — ``info_card`` is the
    universal default.
    """
    if query_hint and any(p.search(query_hint) for p in _DEFINITION_PATTERNS):
        return "concept_card"

    if tool_name in _SINGLE_ENTITY_TOOLS and data:
        # The tool returned a populated single-record response
        if data.get("nct_id") or data.get("id") or data.get("title"):
            return "single_entity_card"

    return "info_card"


def build_fallback_data(
    recipe_name: str,
    tool_name: str,
    original_data: dict[str, Any],
    query_hint: str | None,
) -> dict[str, Any]:
    """Shape the original data dict into the input format expected by
    the chosen fallback recipe."""
    if recipe_name == "concept_card":
        return _build_concept_data(tool_name, original_data, query_hint)
    if recipe_name == "single_entity_card":
        return _build_single_entity_data(tool_name, original_data)
    return _build_info_data(tool_name, original_data, query_hint)


def _build_info_data(
    tool_name: str,
    original_data: dict[str, Any],
    query_hint: str | None,
) -> dict[str, Any]:
    title = "Result"
    bullets: list[str] = []
    no_results_hint: str | None = None

    # Try to extract a sensible title from common shapes
    if original_data.get("title"):
        title = str(original_data["title"])
    elif tool_name:
        title = f"{tool_name.replace('_', ' ').title()} Result"

    # Pull bullets from common list-shaped fields
    for key in ("results", "trials", "publications", "associations", "items"):
        items = original_data.get(key)
        if isinstance(items, list) and items:
            bullets.append(f"{len(items)} {key} returned")
            break

    if not bullets:
        if query_hint:
            no_results_hint = f"No results for: {query_hint}"
        else:
            no_results_hint = f"Tool '{tool_name}' returned no displayable records"

    return {
        "title": title,
        "subtitle": query_hint,
        "bullets": bullets,
        "no_results_hint": no_results_hint,
    }


def _build_concept_data(
    tool_name: str,
    original_data: dict[str, Any],
    query_hint: str | None,
) -> dict[str, Any]:
    term = "Concept"
    if query_hint:
        # Strip the question scaffolding to leave the bare term
        cleaned = query_hint
        for p in _DEFINITION_PATTERNS:
            cleaned = p.sub("", cleaned)
        cleaned = cleaned.strip(" ?.!,")
        if cleaned:
            term = cleaned

    # Try to find a definition-like field in the data
    definition: str | None = None
    for key in ("definition", "summary", "abstract", "description"):
        value = original_data.get(key)
        if isinstance(value, str) and value.strip():
            definition = value.strip()
            break

    # Look one level deeper into the most common list shape
    if definition is None:
        results = original_data.get("results")
        if isinstance(results, list) and results:
            first = results[0]
            if isinstance(first, dict):
                for key in ("abstract", "summary", "snippet"):
                    if first.get(key):
                        definition = str(first[key])
                        break

    return {
        "term": term,
        "definition": definition,
        "category": tool_name.replace("_", "-"),
    }


def _build_single_entity_data(
    tool_name: str,
    original_data: dict[str, Any],
) -> dict[str, Any]:
    title = (
        original_data.get("nct_id")
        or original_data.get("id")
        or original_data.get("title")
        or "Entity"
    )
    subtitle = original_data.get("title") if original_data.get("nct_id") else None

    facts: list[tuple[str, str]] = []
    for key in (
        "phase",
        "status",
        "sponsor",
        "enrollment",
        "start_date",
        "primary_completion_date",
        "condition",
        "intervention",
    ):
        value = original_data.get(key)
        if value:
            facts.append((key.replace("_", " ").title(), str(value)))

    return {
        "kind": tool_name.replace("get_", "").replace("_", " ").rstrip("s"),
        "title": str(title),
        "subtitle": subtitle,
        "facts": facts,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/viz/test_fallback_selection.py -v`

Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/viz/fallback.py tests/viz/test_fallback_selection.py
git commit -m "feat(viz): add pick_fallback_recipe + build_fallback_data

Heuristic selector that maps any tool response to one of the three
fallback recipes. Definition queries (what is, define, explain) →
concept_card. Single-entity tool responses with an id/title →
single_entity_card. Everything else → info_card."
```

---

## Task 10: Eliminate the SKIP path in `build_response`

**Files:**
- Modify: `app/viz/build.py`
- Test: `tests/viz/test_envelope_guarantee.py` (built in Task 14, but a smaller smoke test now)

- [ ] **Step 1: Write a smoke test for the new dispatcher behavior**

Create `tests/viz/test_build_response_fallback.py`:

```python
"""Smoke tests: build_response must always return an envelope with ui."""

from app.viz.build import build_response


def test_build_response_with_no_results_emits_ui():
    envelope = build_response(
        tool_name="search_clinical_trials",
        data={"results": []},
        sources=[],
    )
    # Pre-fix: ui is None. Post-fix: ui is populated.
    assert envelope.get("ui") is not None
    assert envelope["ui"]["recipe"] in ("info_card", "concept_card", "single_entity_card")


def test_build_response_with_unknown_tool_emits_ui():
    envelope = build_response(
        tool_name="totally_made_up_tool",
        data={"some": "data"},
        sources=[],
    )
    assert envelope.get("ui") is not None


def test_build_response_with_definition_query_emits_concept_card():
    envelope = build_response(
        tool_name="search_publications",
        data={"results": []},
        sources=[],
    )
    # Without query hint we get info_card (default)
    assert envelope.get("ui") is not None


def test_build_response_with_existing_recipe_unchanged():
    """The happy path must not regress: a real search_clinical_trials response
    with multiple results still gets the trial_search_results recipe."""
    envelope = build_response(
        tool_name="search_clinical_trials",
        data={"results": [
            {"id": "NCT01", "title": "T1", "sponsor": "S1", "phase": "3", "status": "Recruiting"},
            {"id": "NCT02", "title": "T2", "sponsor": "S2", "phase": "3", "status": "Active"},
        ]},
        sources=[],
    )
    assert envelope.get("ui") is not None
    assert envelope["ui"]["recipe"] == "trial_search_results"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/viz/test_build_response_fallback.py -v`

Expected: FAIL on the SKIP-path tests with `assert envelope.get("ui") is not None` failing.

- [ ] **Step 3: Refactor `build_response` to dispatch through the fallback**

Edit `app/viz/build.py`. Replace the existing function with this version (the `_normalize_sources` and `_serialize` helpers stay as they are):

```python
"""Top-level entrypoint: build_response()

The MCP Yallah server calls this at the end of each tool to turn raw tool
output into a LibreChat-ready envelope. Everything else in app.viz is an
implementation detail behind this single function.
"""

from __future__ import annotations

from typing import Any

from app.viz import render_hints
from app.viz.contract import Decision, DecisionKind, Envelope, PreferVisualization, Source
from app.viz.decision import should_visualize
from app.viz.fallback import build_fallback_data, pick_fallback_recipe
from app.viz.recipes import REGISTRY

__all__ = ["build_response"]


def build_response(
    tool_name: str,
    data: dict[str, Any],
    sources: list[Source] | list[dict[str, Any]] | None = None,
    prefer_visualization: PreferVisualization = "auto",
    query_hint: str | None = None,
) -> dict[str, Any]:
    """Wrap a tool's result into a LibreChat visualization envelope.

    Coverage guarantee: this function ALWAYS returns an envelope with a
    populated ``ui`` field. If the primary decision logic skips, the
    fallback dispatcher routes the response through one of the three
    fallback recipes (info_card / concept_card / single_entity_card).

    Args:
        tool_name: The MCP tool name.
        data: The tool's raw result payload.
        sources: List of public-data citations.
        prefer_visualization: LLM-set override.
        query_hint: Optional original user query, used by the fallback
            dispatcher to pick concept_card vs info_card. Pass through
            from the MCP tool wrapper if available.
    """
    normalized_sources = _normalize_sources(sources)

    decision = should_visualize(tool_name, data, prefer_visualization)
    recipe_name: str
    recipe_data: dict[str, Any]
    fallback_used = False
    fallback_reason = ""

    if decision.kind == DecisionKind.USE and decision.recipe in REGISTRY:
        recipe_name = decision.recipe
        recipe_data = data
    else:
        # Fallback path — guaranteed to produce a recipe
        fallback_used = True
        fallback_reason = (
            decision.reason if decision.kind == DecisionKind.SKIP
            else f"primary recipe '{decision.recipe}' not in REGISTRY"
        )
        recipe_name = pick_fallback_recipe(tool_name, data, query_hint)
        recipe_data = build_fallback_data(
            recipe_name=recipe_name,
            tool_name=tool_name,
            original_data=data,
            query_hint=query_hint,
        )

    builder = REGISTRY[recipe_name]
    ui = builder(recipe_data, sources=normalized_sources)

    envelope = Envelope(
        render_hint=render_hints.for_artifact_type(ui.artifact.type),
        ui=ui,
        data=data,  # original data preserved for downstream consumers
        sources=normalized_sources,
    )
    serialized = _serialize(envelope)

    # Coverage log hook (Task 13 will add the actual write — for now we
    # just stash the metadata so the test can observe it).
    serialized["_coverage"] = {
        "tool": tool_name,
        "recipe": recipe_name,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
    }
    return serialized


def _normalize_sources(
    sources: list[Source] | list[dict[str, Any]] | None,
) -> list[Source]:
    if sources is None:
        return []
    normalized: list[Source] = []
    for entry in sources:
        if isinstance(entry, Source):
            normalized.append(entry)
        elif isinstance(entry, dict):
            normalized.append(Source(**entry))
        else:
            raise TypeError(
                f"Source entries must be Source instances or dicts, got {type(entry).__name__}"
            )
    return normalized


def _serialize(envelope: Envelope) -> dict[str, Any]:
    return envelope.model_dump(by_alias=True, exclude_none=True, mode="json")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/viz/test_build_response_fallback.py -v`

Expected: 4 PASS.

- [ ] **Step 5: Run the full viz test suite to confirm no regressions**

Run: `python -m pytest tests/viz/ -q`

Expected: all tests pass. If any existing test fails because it expected `ui=None` for SKIP cases, update that test to expect a fallback recipe instead — the SKIP path is gone by design.

- [ ] **Step 6: Commit**

```bash
git add app/viz/build.py tests/viz/test_build_response_fallback.py
git commit -m "feat(viz): always emit a ui payload from build_response

Refactors build_response to dispatch through pick_fallback_recipe
whenever the primary decision returns SKIP or names a recipe that is
not in REGISTRY. The envelope's ui field is now ALWAYS populated.
The legacy ui=None branch is dead.

Adds an optional query_hint kwarg so the fallback dispatcher can
distinguish definition queries from generic ones."
```

---

## Task 11: Eliminate the `_maybe_no_data` shortcircuit path

**Files:**
- Modify: `app/main.py` (locate `_maybe_no_data` and its callers)

- [ ] **Step 1: Locate the function**

Run: `grep -n "_maybe_no_data\|no_data.*True" app/main.py`

Expected: a definition site and several call sites. Read the function.

- [ ] **Step 2: Locate all callers and the path that produces `[NO DATA AVAILABLE]`**

Run: `grep -B2 -A4 "_maybe_no_data" app/main.py`

Read the surrounding context. The function likely returns a dict like
`{"no_data": True, "source": ..., "query": ..., "do_not_supplement": ...}`
which then gets passed straight to `envelope_to_llm_text` and triggers
`_format_no_data` (the `[NO DATA AVAILABLE]` path).

- [ ] **Step 3: Write a guarding test**

Create `tests/viz/test_no_data_path_eliminated.py`:

```python
"""When a tool's data fetch yields no records, the response must still
contain an artifact block. The legacy [NO DATA AVAILABLE] path must be
gone."""

from app.viz.build import build_response


def test_empty_search_clinical_trials_emits_artifact_not_no_data():
    envelope = build_response(
        tool_name="search_clinical_trials",
        data={"results": [], "total": 0},
        sources=[],
        query_hint="some query that returned nothing",
    )
    assert envelope.get("ui") is not None
    assert "raw" in envelope["ui"]
    assert envelope["ui"]["raw"]


def test_empty_get_trial_details_emits_artifact():
    envelope = build_response(
        tool_name="get_trial_details",
        data={},
        sources=[],
        query_hint="NCT99999999",
    )
    assert envelope.get("ui") is not None
```

- [ ] **Step 4: Run the test (it should already pass after Task 10)**

Run: `python -m pytest tests/viz/test_no_data_path_eliminated.py -v`

Expected: PASS. (Task 10 already routes empty responses through the fallback.) If it fails, debug the fallback chain before continuing.

- [ ] **Step 5: Reroute `_maybe_no_data` callers through `build_response`**

Edit `app/main.py`. For every call site of `_maybe_no_data`, replace the pattern:

```python
# OLD
no_data_envelope = _maybe_no_data(...)
if no_data_envelope:
    return envelope_to_llm_text(no_data_envelope)
```

with:

```python
# NEW
if not <records>:  # whatever the empty check was
    envelope = build_response(
        tool_name=<tool_name>,
        data=<empty_data_dict_or_original_data>,
        sources=<sources>,
        query_hint=<query>,
    )
    return envelope_to_llm_text(envelope)
```

After every call site is rewritten, delete the `_maybe_no_data` function definition.

**Note:** the exact rewrite depends on what `_maybe_no_data` looks like. Run `grep -n "_maybe_no_data" app/main.py` and rewrite each call site by hand, copying the surrounding context. Do NOT bulk-replace.

- [ ] **Step 6: Run the full test suite**

Run: `python -m pytest tests/ -q`

Expected: all tests pass. The test from Step 3 still passes (now via a real call path). Any tests that exercised the `_maybe_no_data` path now exercise the fallback path instead and should still pass because the envelope shape is unchanged from the consumer's view.

- [ ] **Step 7: Commit**

```bash
git add app/main.py tests/viz/test_no_data_path_eliminated.py
git commit -m "refactor(main): route no-data shortcircuits through build_response

Removes _maybe_no_data and its custom envelope shape. Empty tool
responses now flow through build_response which guarantees a
fallback recipe (info_card by default). The [NO DATA AVAILABLE]
path is gone from the LLM-facing text."
```

---

## Task 12: Build `coverage_log` module

**Files:**
- Create: `app/viz/coverage_log.py`
- Create: `tests/viz/test_coverage_log.py`

- [ ] **Step 1: Write the failing test**

Create `tests/viz/test_coverage_log.py`:

```python
"""Tests for the lightweight coverage logger."""

import json
from pathlib import Path

import pytest

from app.viz import coverage_log


@pytest.fixture
def tmp_log_path(tmp_path, monkeypatch) -> Path:
    log_file = tmp_path / "viz_coverage.jsonl"
    monkeypatch.setattr(coverage_log, "LOG_PATH", log_file)
    return log_file


def test_log_entry_writes_jsonl(tmp_log_path):
    coverage_log.log_entry(
        tool="search_clinical_trials",
        recipe="trial_search_results",
        fallback_used=False,
        fallback_reason="",
    )
    lines = tmp_log_path.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["tool"] == "search_clinical_trials"
    assert record["recipe"] == "trial_search_results"
    assert record["fallback_used"] is False
    assert "ts" in record


def test_log_entry_records_fallback_with_reason(tmp_log_path):
    coverage_log.log_entry(
        tool="get_trial_details",
        recipe="info_card",
        fallback_used=True,
        fallback_reason="sparse trial record",
    )
    record = json.loads(tmp_log_path.read_text().strip())
    assert record["fallback_used"] is True
    assert record["fallback_reason"] == "sparse trial record"


def test_log_entry_appends_does_not_overwrite(tmp_log_path):
    coverage_log.log_entry(tool="t1", recipe="r1", fallback_used=False, fallback_reason="")
    coverage_log.log_entry(tool="t2", recipe="r2", fallback_used=True, fallback_reason="x")
    lines = tmp_log_path.read_text().strip().splitlines()
    assert len(lines) == 2


def test_log_entry_creates_parent_dir(tmp_path, monkeypatch):
    nested = tmp_path / "deep" / "nested" / "viz_coverage.jsonl"
    monkeypatch.setattr(coverage_log, "LOG_PATH", nested)
    coverage_log.log_entry(tool="t", recipe="r", fallback_used=False, fallback_reason="")
    assert nested.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/viz/test_coverage_log.py -v`

Expected: FAIL with `ImportError: cannot import name 'coverage_log'`.

- [ ] **Step 3: Implement the logger**

Create `app/viz/coverage_log.py`:

```python
"""Lightweight JSONL coverage logger.

Writes one line per build_response() invocation to logs/viz_coverage.jsonl.
Used to validate the visualization coverage guarantee against real traffic
and prioritize fallback hot spots.

This is intentionally trivial — no log rotation, no async, no
configurable level. If logging fails for any reason (disk full, perms),
the failure is swallowed because coverage logging must NEVER break the
hot path.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["log_entry", "LOG_PATH"]


REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = REPO_ROOT / "logs" / "viz_coverage.jsonl"


def log_entry(
    tool: str,
    recipe: str,
    fallback_used: bool,
    fallback_reason: str,
) -> None:
    """Append one coverage record to the JSONL log.

    Failures are silently swallowed — this function MUST NOT raise.
    """
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "recipe": recipe,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
        }
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - logging must not break hot path
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/viz/test_coverage_log.py -v`

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/viz/coverage_log.py tests/viz/test_coverage_log.py
git commit -m "feat(viz): add lightweight JSONL coverage logger

Writes one line per envelope assembly to logs/viz_coverage.jsonl.
Failures are silently swallowed — logging must never break the hot
path. Wired into build_response in the next commit."
```

---

## Task 13: Wire `coverage_log` into `build_response`

**Files:**
- Modify: `app/viz/build.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/viz/test_coverage_log.py`:

```python
def test_build_response_writes_coverage_log(tmp_log_path):
    from app.viz.build import build_response

    build_response(
        tool_name="search_clinical_trials",
        data={"results": []},
        sources=[],
        query_hint="any",
    )
    lines = tmp_log_path.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["tool"] == "search_clinical_trials"
    assert record["fallback_used"] is True  # empty results triggers fallback
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/viz/test_coverage_log.py::test_build_response_writes_coverage_log -v`

Expected: FAIL — `build_response` doesn't write logs yet.

- [ ] **Step 3: Wire the logger and remove the temporary `_coverage` stash**

Edit `app/viz/build.py`. Add the import and the log call:

Find this block (added in Task 10):
```python
    serialized = _serialize(envelope)

    # Coverage log hook (Task 13 will add the actual write — for now we
    # just stash the metadata so the test can observe it).
    serialized["_coverage"] = {
        "tool": tool_name,
        "recipe": recipe_name,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
    }
    return serialized
```

Replace it with:
```python
    serialized = _serialize(envelope)

    coverage_log.log_entry(
        tool=tool_name,
        recipe=recipe_name,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
    )
    return serialized
```

And add at the top of the file with the other imports:
```python
from app.viz import coverage_log
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/viz/test_coverage_log.py -v`

Expected: 5 PASS.

- [ ] **Step 5: Run the full viz suite to ensure nothing else broke**

Run: `python -m pytest tests/viz/ -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/viz/build.py tests/viz/test_coverage_log.py
git commit -m "feat(viz): wire coverage_log into build_response

Every envelope assembly now writes a JSONL line to logs/viz_coverage.jsonl
with tool, recipe, fallback_used, and fallback_reason. Removes the
temporary _coverage stash from the serialized envelope."
```

---

## Task 14: Build the envelope guarantee test

**Files:**
- Create: `tests/viz/test_envelope_guarantee.py`

- [ ] **Step 1: Write the parametrized test**

Create `tests/viz/test_envelope_guarantee.py`:

```python
"""Coverage guarantee test — the keystone of the viz coverage workstream.

For every MCP tool, parametrized over three response factories
(populated, empty, single_item), assert that build_response() returns
an envelope whose ui field is populated and whose ui.raw contains
non-empty rendered content.

This is the regression test for the entire coverage guarantee.
"""

from typing import Any, Callable

import pytest

from app.viz.build import build_response

# All MCP tools defined in app/main.py. Keep in sync with @mcp.tool() decorators.
ALL_TOOLS = [
    "search_clinical_trials",
    "search_publications",
    "get_trial_details",
    "get_indication_landscape",
    "compare_trials",
    "get_target_context",
    "build_trial_comparison",
    "analyze_whitespace",
    "analyze_indication_landscape",
    "get_sponsor_overview",
    # The remaining 3 tools — fill in from `grep @mcp.tool app/main.py`
    # before running. If a tool name is unknown, the fallback dispatcher
    # still routes it to info_card.
]


def _populated(tool: str) -> dict[str, Any]:
    """Return a richly-populated data dict for the given tool."""
    if tool == "search_clinical_trials" or tool == "search_publications":
        return {"results": [
            {"id": "NCT01", "title": "T1", "sponsor": "S1", "phase": "3", "status": "Recruiting", "abstract": "X"},
            {"id": "NCT02", "title": "T2", "sponsor": "S2", "phase": "3", "status": "Active", "abstract": "Y"},
        ]}
    if tool == "get_trial_details":
        return {
            "nct_id": "NCT01234567",
            "title": "A Phase 3 study",
            "phase": "3",
            "status": "Recruiting",
            "sponsor": "Merck",
            "arms": [{"name": "Arm A"}],
            "endpoints": ["OS"],
            "eligibility": {"min_age": "18"},
            "locations": [{"country": "US"}],
            "interventions": [{"name": "Drug X"}],
        }
    if tool in ("compare_trials", "build_trial_comparison"):
        return {"trials": [
            {"id": "NCT01", "start_date": "2024-01-01", "primary_completion_date": "2026-01-01", "title": "T1"},
            {"id": "NCT02", "start_date": "2024-06-01", "primary_completion_date": "2026-06-01", "title": "T2"},
        ]}
    if tool == "get_indication_landscape":
        return {
            "phase_distribution": [{"phase": "3", "count": 12}, {"phase": "2", "count": 8}],
            "top_sponsors": [{"name": "Merck", "count": 5}, {"name": "Pfizer", "count": 4}],
            "status_breakdown": [{"status": "Recruiting", "count": 15}],
        }
    if tool == "get_target_context":
        return {"associations": [{"target": "EGFR", "score": 0.9}, {"target": "KRAS", "score": 0.8}]}
    if tool == "analyze_whitespace":
        return {
            "condition": "NSCLC",
            "trial_counts_by_phase": {"phase_1": 12, "phase_2": 8, "phase_3": 4},
            "trial_counts_by_status": {"recruiting": 14},
            "identified_whitespace": ["Few Phase 3 trials"],
        }
    return {"some_data": "populated", "title": f"{tool} result"}


def _empty(tool: str) -> dict[str, Any]:
    """Return an empty / no-results data dict."""
    return {"results": [], "trials": [], "associations": [], "total": 0}


def _single_item(tool: str) -> dict[str, Any]:
    """Return a single-record data dict — common for trivial-hit cases."""
    if tool == "search_clinical_trials":
        return {"results": [{"id": "NCT01", "title": "T1"}]}
    if tool == "get_trial_details":
        return {"nct_id": "NCT01"}
    return {"results": [{"id": "1"}]}


@pytest.mark.parametrize("tool", ALL_TOOLS)
@pytest.mark.parametrize(
    "factory",
    [_populated, _empty, _single_item],
    ids=["populated", "empty", "single_item"],
)
def test_envelope_always_emits_artifact(tool: str, factory: Callable[[str], dict[str, Any]]):
    data = factory(tool)
    envelope = build_response(
        tool_name=tool,
        data=data,
        sources=[],
        query_hint="test query",
    )
    # The keystone assertion
    assert envelope.get("ui") is not None, (
        f"tool={tool} factory={factory.__name__} produced ui=None — coverage guarantee broken"
    )
    ui = envelope["ui"]
    assert ui.get("raw"), (
        f"tool={tool} factory={factory.__name__} produced empty ui.raw — recipe failed"
    )
    assert ui.get("recipe") in (
        "indication_dashboard", "trial_search_results", "trial_detail_tabs",
        "trial_timeline_gantt", "sponsor_pipeline_cards", "target_associations_table",
        "whitespace_card", "info_card", "concept_card", "single_entity_card",
    )


def test_unknown_tool_still_emits_artifact():
    envelope = build_response(
        tool_name="totally_unknown_tool",
        data={"weird": "shape"},
        sources=[],
    )
    assert envelope.get("ui") is not None
    assert envelope["ui"]["recipe"] == "info_card"
```

- [ ] **Step 2: Update `ALL_TOOLS` with the actual tool list**

Run: `grep -A2 "@mcp.tool()" app/main.py | grep "^def\|^async def" | sed 's/^\(async \)\?def \([a-z_]*\).*/\2/'`

Copy the resulting tool names into the `ALL_TOOLS` list. Make sure all 13 are present.

- [ ] **Step 3: Run the test**

Run: `python -m pytest tests/viz/test_envelope_guarantee.py -v`

Expected: ALL combinations PASS. If any combination fails, the failing tool's response shape needs a bigger factory or the fallback dispatcher needs to handle it. Fix and re-run.

- [ ] **Step 4: Commit**

```bash
git add tests/viz/test_envelope_guarantee.py
git commit -m "test(viz): add envelope coverage guarantee parametrized test

Parametrized over every MCP tool x {populated, empty, single_item}
factory. Asserts build_response always returns ui != None and
ui.raw is non-empty. This is the keystone regression test for the
coverage guarantee."
```

---

## Task 15: Delete dead branches in `mcp_output.py`

**Files:**
- Modify: `app/viz/mcp_output.py`

- [ ] **Step 1: Confirm the dead branches**

Run: `grep -n "no_data\|NO VISUALIZATION\|_format_text_only\|_format_no_data" app/viz/mcp_output.py`

Now that `build_response` always returns `ui != None` and `_maybe_no_data` is gone, the `_format_text_only` and `_format_no_data` functions are unreachable from the production path.

- [ ] **Step 2: Write a regression-guarding test**

Append to `tests/viz/test_mcp_output.py` (existing file):

```python
def test_mcp_output_never_emits_no_visualization_marker():
    """The [NO VISUALIZATION] and [NO DATA AVAILABLE] markers must not
    appear for any envelope produced by build_response."""
    from app.viz.build import build_response
    from app.viz.mcp_output import envelope_to_llm_text

    for empty_data in ({}, {"results": []}, {"trials": []}):
        envelope = build_response(
            tool_name="search_clinical_trials",
            data=empty_data,
            sources=[],
            query_hint="test",
        )
        text = envelope_to_llm_text(envelope)
        assert ":::artifact" in text
        assert "[NO VISUALIZATION]" not in text
        assert "[NO DATA AVAILABLE]" not in text
```

- [ ] **Step 3: Run the test**

Run: `python -m pytest tests/viz/test_mcp_output.py::test_mcp_output_never_emits_no_visualization_marker -v`

Expected: PASS (the new behavior in build_response is sufficient).

- [ ] **Step 4: Delete the dead branches (preserve the ACTION REQUIRED preamble)**

Edit `app/viz/mcp_output.py`. Replace the entire file with the version below.

**Important:** the `_format_with_artifact` function in this version preserves the multi-line `ACTION REQUIRED` preamble that was added by commit `5001d95` on main. Do NOT remove or shorten the preamble — it is the in-band guarantee that the LLM pastes the artifact block. Only the SKIP and no_data branches are deleted.

```python
"""Convert an envelope dict into LLM-ready text for MCP tool returns.

This module pre-assembles the ``:::artifact{…}:::`` directive with
``ui.raw`` as its body and returns it as plain text wrapped in an
"ACTION REQUIRED" preamble. The LLM reads the tool result as "the
thing to paste" and just includes it in its reply, optionally adding
a few sentences of commentary afterwards. No JSON parsing needed.

Coverage guarantee: every envelope produced by
``app.viz.build.build_response`` contains a populated ``ui`` field.
There is no longer a SKIP path or a ``[NO DATA AVAILABLE]``
shortcircuit — the legacy ``_format_text_only`` and ``_format_no_data``
branches have been removed.
"""

from __future__ import annotations

from typing import Any

__all__ = ["envelope_to_llm_text"]


# Cap the sources footer length — the full citation list can be many
# dozens of entries, but the LLM only needs a handful for its commentary.
_MAX_SOURCES_IN_FOOTER = 10


def envelope_to_llm_text(envelope: dict[str, Any]) -> str:
    """Render an envelope dict as the text payload an MCP tool should return.

    The envelope MUST contain a populated ``ui`` field. ``build_response``
    guarantees this; any caller bypassing ``build_response`` is a bug.
    """
    ui = envelope.get("ui")
    if ui is None:
        raise ValueError(
            "envelope_to_llm_text received an envelope without a ui field. "
            "All envelopes must come from build_response, which guarantees ui."
        )
    sources = envelope.get("sources") or []
    return _format_with_artifact(ui, sources)


# --- Visualization path ----------------------------------------------------


def _format_with_artifact(
    ui: dict[str, Any], sources: list[dict[str, Any]]
) -> str:
    """Pre-assemble the :::artifact{…}::: block the LLM should paste.

    The tool result deliberately STARTS with a one-line imperative
    telling the LLM to paste the block below verbatim. We tried system-
    prompt-level instructions ("MANDATORY: always include the artifact")
    and still saw the LLM skip the block unless the user explicitly
    asked for a visualization. Putting the instruction in-band — right
    next to the thing it should copy — gets the LLM to reliably forward
    the artifact to LibreChat's side pane.
    """
    artifact = ui["artifact"]
    identifier = artifact["identifier"]
    art_type = artifact["type"]
    title = _escape_attr(artifact["title"])
    raw = (ui.get("raw") or "").rstrip()

    artifact_block = (
        f':::artifact{{identifier="{identifier}" type="{art_type}" title="{title}"}}\n'
        f"{raw}\n"
        f":::"
    )

    footer = _sources_footer(sources)

    # In-band instruction. The LLM sees this BEFORE the artifact block and
    # treats it as guidance-for-this-tool-result, not as content to echo.
    # Phrasing:
    #   - "ACTION REQUIRED" is a strong trigger phrase for tool-following
    #   - The explicit "paste the :::artifact block below verbatim at the
    #     start of your reply" tells it exactly what to do
    #   - "do NOT write your own visualization / do NOT skip the block"
    #     closes the two failure modes we saw in production
    preamble = (
        "ACTION REQUIRED — copy the :::artifact{…}::: block below into your "
        "reply VERBATIM, as the very first thing you write. Do not rewrite "
        "the HTML, do not paraphrase it, do not build your own alternative "
        "visualization, and do not skip the block because you think prose "
        "is enough. LibreChat only opens the side pane when the artifact "
        "directive appears in your reply, so omitting it means the user "
        "sees nothing. AFTER the artifact block you MAY add 2–5 sentences "
        "of analysis that interpret the visualization. This applies to "
        "every single tool call — the user does NOT need to ask for a "
        "visualization, it is the default whenever a tool returns one."
    )

    return f"{preamble}\n\n{artifact_block}\n\n{footer}"


# --- Helpers ---------------------------------------------------------------


def _sources_footer(sources: list[dict[str, Any]]) -> str:
    """Compact one-block citation list for the LLM's commentary section."""
    if not sources:
        return "Sources: (none returned by this tool)"
    lines = ["Sources:"]
    for s in sources[:_MAX_SOURCES_IN_FOOTER]:
        kind = s.get("kind", "?")
        sid = s.get("id", "?")
        url = s.get("url", "")
        lines.append(f"  - [{kind}] {sid} {url}".rstrip())
    extra = len(sources) - _MAX_SOURCES_IN_FOOTER
    if extra > 0:
        lines.append(f"  (+{extra} more)")
    return "\n".join(lines)


def _escape_attr(value: object) -> str:
    """Escape double quotes for safe inclusion inside an artifact attribute."""
    if value is None:
        return ""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')
```

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest tests/ -q`

Expected: all tests pass. If any test fails because it directly constructed a `ui=None` envelope and called `envelope_to_llm_text`, update it to use `build_response` instead — that's the correct entrypoint now.

- [ ] **Step 6: Commit**

```bash
git add app/viz/mcp_output.py tests/viz/test_mcp_output.py
git commit -m "refactor(viz): delete dead [NO VISUALIZATION] and [NO DATA] branches

The coverage guarantee in build_response makes ui=None impossible. The
_format_text_only and _format_no_data branches in mcp_output.py have
been removed. envelope_to_llm_text now raises if it receives an
envelope without a ui field — that would be a caller bug."
```

---

## Task 16: Build the audit ratchet test

**Files:**
- Create: `tests/viz/test_audit_ratchet.py`

- [ ] **Step 1: Write the ratchet test**

Create `tests/viz/test_audit_ratchet.py`:

```python
"""Regression ratchet: no new unguarded SKIP paths may enter the codebase.

After the coverage guarantee work, every Decision.skip(...) call has been
either removed from app/viz/decision.py or routed through build_response's
fallback dispatcher. This test re-runs the static audit and asserts the
total count is at or below the locked-in baseline.

Update RATCHET_MAX only when intentionally adding a new SKIP that you
know will be caught by build_response's fallback (e.g., adding a new
tool whose decision logic skips for the trivial case). Never update it
to make a failing test pass without understanding why.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from audit_viz_paths import run_audit  # noqa: E402

# Locked-in baseline: the number of Decision.skip() sites that are
# acceptable because build_response routes them through the fallback
# dispatcher. The legacy `_maybe_no_data` and dict `no_data` literals
# must be ZERO.
RATCHET_MAX_SKIP_SITES = 20  # adjust on first run after Task 11
RATCHET_MAX_NO_DATA_SITES = 0


def test_skip_sites_within_baseline():
    result = run_audit()
    assert len(result.skip_sites) <= RATCHET_MAX_SKIP_SITES, (
        f"Found {len(result.skip_sites)} Decision.skip() sites — "
        f"baseline is {RATCHET_MAX_SKIP_SITES}. New SKIP sites are only "
        f"allowed if you also verify build_response routes them through "
        f"the fallback dispatcher. Sites:\n"
        + "\n".join(f"  {s.file}:{s.line} — {s.snippet}" for s in result.skip_sites)
    )


def test_no_data_literals_eliminated():
    result = run_audit()
    assert len(result.no_data_sites) == RATCHET_MAX_NO_DATA_SITES, (
        f"Found {len(result.no_data_sites)} `no_data` literal sites — "
        f"all such sites must be eliminated. The [NO DATA AVAILABLE] "
        f"path is dead. Sites:\n"
        + "\n".join(f"  {s.file}:{s.line} — {s.snippet}" for s in result.no_data_sites)
    )
```

- [ ] **Step 2: Run the audit to find the actual baseline**

Run: `python scripts/audit_viz_paths.py && cat logs/viz_audit.md`

Note the actual count of `Decision.skip()` sites. Update `RATCHET_MAX_SKIP_SITES` in the test to match this number (this is your locked-in baseline).

- [ ] **Step 3: Run the test**

Run: `python -m pytest tests/viz/test_audit_ratchet.py -v`

Expected: PASS. If `test_no_data_literals_eliminated` fails, go back to Task 11 and finish removing the `_maybe_no_data` callers.

- [ ] **Step 4: Commit**

```bash
git add tests/viz/test_audit_ratchet.py
git commit -m "test(viz): add ratchet test for SKIP path baseline

Locks in the current count of Decision.skip() sites and asserts zero
no_data literal markers. New SKIP sites are only allowed if they are
routed through build_response's fallback dispatcher; new no_data
markers are never allowed."
```

---

## Task 17: Trim obsolete shape descriptions from the LLM `instructions=` block

**Note (post-merge):** the `## ZERO-EXCEPTION RULE` block at lines 64–88 of `app/main.py` (added by commit `5001d95`) is already in place and is stronger than what was originally planned for this task. The work here is now to **delete the obsolete sections** that describe response shapes that no longer exist after Tasks 10, 11, and 15.

**Files:**
- Modify: `app/main.py` (the `instructions=` string in the FastMCP constructor)

- [ ] **Step 1: Locate the THREE SHAPES block**

Run: `grep -n "THREE SHAPES\|Visualization result\|NO VISUALIZATION\|NO DATA AVAILABLE" app/main.py`

Expected: the `## PARSING THE TOOL RESPONSE` section around line 90, with the three shape descriptions at lines ~98 (1), ~125 (2), ~140 (3).

- [ ] **Step 2: Read the current block**

Run: `sed -n '90,160p' app/main.py`

Confirm the three shape descriptions are present. After this task, only shape (1) remains, and it should be slightly retitled because there is now only one shape.

- [ ] **Step 3: Replace the THREE SHAPES block with a single SHAPE block**

Edit `app/main.py`. Find this block (the exact text comes from the file you just inspected — match it carefully):

```
THE TOOL RESPONSE HAS ONE OF THREE SHAPES:

(1) Visualization result — starts with a ``:::artifact{…}:::`` directive:
... [section 1 content] ...

(2) Text-only result — starts with ``[NO VISUALIZATION]``:
... [section 2 content] ...

(3) Empty result — starts with ``[NO DATA AVAILABLE]``:
... [section 3 content] ...
```

Replace the entire block (sections 1, 2, AND 3) with this single section:

```
THE TOOL RESPONSE ALWAYS HAS THE SAME SHAPE:

Every tool result starts with an ``ACTION REQUIRED`` preamble line followed
by exactly one ``:::artifact{…}:::`` directive. There are no other shapes
anymore — empty results, definition queries, single-entity lookups, and
unknown tools all produce a fallback info-card / concept-card / single-
entity-card artifact. The legacy ``[NO VISUALIZATION]`` and
``[NO DATA AVAILABLE]`` markers no longer exist in the wire format.

    ACTION REQUIRED — copy the :::artifact{…}::: block below into your
    reply VERBATIM, as the very first thing you write. ...

    :::artifact{identifier="..." type="html" title="..."}
    <div class="...">
      …HTML body…
    </div>
    :::

    (Type values are the short LibreChat names: ``html`` or ``mermaid`` —
    NOT MIME types. Leave the type string exactly as the tool emitted it.)

    Sources:
      - [clinicaltrials.gov] NCT01234567 https://clinicaltrials.gov/study/NCT01234567
      - [pubmed] 12345678 https://pubmed.ncbi.nlm.nih.gov/12345678/

MANDATORY: Copy the ENTIRE ``:::artifact{…}:::`` block (from the opening
``:::artifact`` line through the closing ``:::``) into your reply
VERBATIM. Do not rewrite, reformat, paraphrase, truncate, or reorder
the HTML / Mermaid inside the fence. Do not wrap a Mermaid diagram in
a ```mermaid fence — the artifact directive already declares the type.
Do not echo the ACTION REQUIRED preamble — it is a tool-internal
instruction.

After you have pasted the artifact block, you MAY add 2–5 sentences
of analytical commentary interpreting the visualization or connecting
it to the user's question. Cite sources from the footer using
NCT / PMID identifiers. The commentary is optional; the verbatim
artifact paste is not.
```

- [ ] **Step 4: Verify no stale references remain**

Run: `grep -n "NO VISUALIZATION\|NO DATA AVAILABLE\|THREE SHAPES" app/main.py`

Expected: zero hits inside the `instructions=` string. (Hits inside `_maybe_no_data` are fine if any survived — Task 11 deletes that function.)

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest tests/ -q`

Expected: all tests pass. The instructions block is a Python string literal — no code changes, just docs inside the string.

- [ ] **Step 6: Commit**

```bash
git add app/main.py
git commit -m "docs(mcp): trim obsolete [NO VIZ] / [NO DATA] shape descriptions

After WS1 coverage guarantee work, every tool response has the same
shape: ACTION REQUIRED preamble + exactly one :::artifact::: block.
The legacy [NO VISUALIZATION] and [NO DATA AVAILABLE] markers are
gone. The ZERO-EXCEPTION RULE block (already present) is unchanged."
```

---

## Task 18: Final end-to-end smoke + commit

**Files:**
- Run: full test suite + audit + smoke

- [ ] **Step 1: Re-run the audit**

Run: `python scripts/audit_viz_paths.py && cat logs/viz_audit.md`

Expected: `Total unguarded sites: <N>` where N matches `RATCHET_MAX_SKIP_SITES` and the `no_data` section is empty.

- [ ] **Step 2: Run the full test suite**

Run: `python -m pytest tests/ -q`

Expected: all tests pass.

- [ ] **Step 3: Smoke-test a real MCP call**

If a manual test harness is available (e.g., `scripts/mcp_healthcheck.py`), run it. Otherwise, exercise `build_response` from a Python REPL:

```bash
python -c "
from app.viz.build import build_response
from app.viz.mcp_output import envelope_to_llm_text

# Empty result case
env = build_response('search_clinical_trials', {'results': []}, sources=[], query_hint='test')
text = envelope_to_llm_text(env)
assert ':::artifact' in text
print('OK: empty result produces artifact')

# Definition case
env = build_response('search_publications', {'results': [{'abstract': 'RECIST is...'}]}, sources=[], query_hint='What is RECIST?')
text = envelope_to_llm_text(env)
assert ':::artifact' in text
print('OK: definition query produces artifact')

# Unknown tool case
env = build_response('made_up_tool', {'foo': 'bar'}, sources=[])
text = envelope_to_llm_text(env)
assert ':::artifact' in text
print('OK: unknown tool produces artifact')
"
```

Expected output:
```
OK: empty result produces artifact
OK: definition query produces artifact
OK: unknown tool produces artifact
```

- [ ] **Step 4: Inspect the coverage log**

Run: `cat logs/viz_coverage.jsonl`

Expected: at least 3 lines from the smoke test, all with `recipe` populated.

- [ ] **Step 5: No additional commit** — the work is already committed in tasks 2–17.

- [ ] **Step 6: (Optional) Push the branch**

```bash
git status
git log --oneline main..HEAD
```

Verify the commit history is clean and matches the task list.

---

## Success Criteria Recap

| Criterion | Verification |
|---|---|
| Every MCP tool response emits an `:::artifact:::` block | `tests/viz/test_envelope_guarantee.py` (39+ assertions) |
| Zero unguarded `Decision.skip()` paths beyond the baseline | `tests/viz/test_audit_ratchet.py` |
| Zero `no_data` literal markers | `tests/viz/test_audit_ratchet.py::test_no_data_literals_eliminated` |
| Coverage logging works | `tests/viz/test_coverage_log.py` (5 tests) |
| Three new fallback recipes render correctly | `tests/viz/test_recipes.py` (10+ new tests) |
| Fallback selector picks the right recipe | `tests/viz/test_fallback_selection.py` (9 tests) |
| `[NO VISUALIZATION]` / `[NO DATA AVAILABLE]` markers absent | `tests/viz/test_mcp_output.py::test_mcp_output_never_emits_no_visualization_marker` |
| LLM instructions reflect the new guarantee | Manual review of `app/main.py` instructions block |

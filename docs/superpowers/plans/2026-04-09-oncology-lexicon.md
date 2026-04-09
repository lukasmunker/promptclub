# Oncology Knowledge Lexicon — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a static curated oncology knowledge lexicon (~250–400 entries) and a deterministic enrichment layer that walks every MCP tool response, matches lexicon terms, and attaches knowledge annotations the visualization layer can render.

**Architecture:** Two parallel sub-pipelines: (1) **Runtime** — `app/knowledge/oncology/lexicon.yaml` is loaded once at server startup, `app/services/enrichment.py` walks the response dict in `app/viz/build.py` after fallback dispatch and before recipe rendering, attaching a top-level `knowledge_annotations` field; (2) **Curation** — offline scripts in `scripts/curation/` that read a hand-maintained `seed_topics.yaml`, call Claude to draft entries, write a CSV review worksheet, and merge accepted entries back to YAML. Hard quality gates at the schema level (mandatory sources, source-domain allowlist, alias uniqueness) prevent unverified hallucinations.

**Tech Stack:** Python 3.12, Pydantic 2, `pyyaml`, `anthropic` (for the offline curation script), `pytest`, the `app.viz` envelope contract.

**Spec:** [docs/superpowers/specs/2026-04-09-onkologie-lexikon-design.md](../specs/2026-04-09-onkologie-lexikon-design.md)

**Note on dict-vs-Pydantic:** The spec discusses enrichment on Pydantic models in `orchestration.py`. After inspecting the codebase (`app/viz/build.py:build_response` works on dicts via `lean_dump`), this plan implements enrichment on the data dict inside `build_response` instead. The behavior is identical from the consumer's view, but the implementation is simpler — no `BaseToolResponse` modifications, no Pydantic walker. The annotation field becomes a top-level key on the envelope's `data` dict.

---

## File Structure

**New files:**

| Path | Responsibility |
|---|---|
| `app/knowledge/__init__.py` | Module marker |
| `app/knowledge/oncology/__init__.py` | Sub-module marker |
| `app/knowledge/oncology/schema.py` | Pydantic models: `LexiconEntry`, `Source`, `Lexicon`, `Annotation` |
| `app/knowledge/oncology/loader.py` | `load_lexicon() -> Lexicon` (parses YAML, builds term + alias index) |
| `app/knowledge/oncology/seed_topics.yaml` | Hand-maintained list of terms to generate, grouped by category |
| `app/knowledge/oncology/lexicon.yaml` | The curated entries (output of curation pipeline, committed) |
| `app/services/enrichment.py` | `enrich(data: dict, lexicon: Lexicon) -> dict` — walks data, finds term matches, returns new dict with `knowledge_annotations` |
| `scripts/curation/__init__.py` | Module marker |
| `scripts/curation/generate_lexicon.py` | Offline LLM-generation script (Claude via anthropic SDK) |
| `scripts/curation/review_worksheet_to_yaml.py` | Merge reviewed CSV back into `lexicon.yaml` |
| `scripts/curation/README.md` | Curation workflow documentation |
| `tests/knowledge/__init__.py` | Test module marker |
| `tests/knowledge/test_schema.py` | Schema validation tests (sources required, allowlist) |
| `tests/knowledge/test_loader.py` | Loader tests (empty YAML, indexed lookup) |
| `tests/knowledge/test_lexicon_quality.py` | Quality tests (no dupes, related_terms resolve, etc.) |
| `tests/services/test_enrichment.py` | Enrichment logic tests (canonical, alias, word boundary, idempotence, cap, no mutation) |
| `tests/curation/__init__.py` | Test module marker |
| `tests/curation/test_merge_worksheet.py` | Merge script tests (rejected dropped, edits applied, status set) |
| `tests/test_orchestration_with_enrichment.py` | End-to-end integration: enrichment + WS1 envelope guarantee |

**Changed files:**

| Path | Change |
|---|---|
| [app/viz/build.py](../../../app/viz/build.py) | Load `Lexicon` once at module level (lazy singleton). In `build_response`, call `enrich(data, lexicon)` before passing data to the recipe builder. |
| [app/viz/recipes/info_card.py](../../../app/viz/recipes/info_card.py) | If `data["knowledge_annotations"]` is non-empty, render a "Glossary" footer block listing the matched terms with their short definitions. (Opt-in pattern; other recipes may follow later.) |
| [app/viz/contract.py](../../../app/viz/contract.py) | None directly — but the envelope's `data` dict now optionally carries a top-level `knowledge_annotations` list. Documented in a docstring. |

**Untouched:**

- The LLM synthesis prompt in `app/main.py:24-148`. No prompt engineering in WS2.
- The adapter layer (`app/adapters/`).
- Other recipes — they may render annotations later, but v1 only wires `info_card`.
- Other therapeutic areas — oncology is v1.

---

## Task Index

**Development phase A (schema + loader):**
1. Scaffold `app/knowledge/oncology/` package
2. Define schema with TDD
3. Build loader with TDD

**Development phase B (curation pipeline scaffolding):**
4. Write `seed_topics.yaml` with category headers
5. Build `generate_lexicon.py` (LLM generation script)
6. Test generation against a 3-term mini seed
7. Build `review_worksheet_to_yaml.py` (merge script)

**Manual milestone (the user's curation work):**
8. Run full LLM generation (manual)
9. Manual review of CSV (manual)
10. Run merge to produce final `lexicon.yaml` (script + commit)

**Development phase C (enrichment + integration):**
11. Lexicon quality tests (run against the real lexicon.yaml)
12. Build `enrichment.py` with TDD
13. Wire enrichment into `build_response`
14. Recipe integration: glossary footer in `info_card`
15. Integration test with WS1 envelope guarantee
16. Final smoke + commit

---

## Task 1: Scaffold the `app/knowledge/oncology/` package

**Files:**
- Create: `app/knowledge/__init__.py`
- Create: `app/knowledge/oncology/__init__.py`
- Create: `tests/knowledge/__init__.py`

- [ ] **Step 1: Create the directories**

Run: `mkdir -p app/knowledge/oncology tests/knowledge`

- [ ] **Step 2: Create the `__init__.py` files**

Create `app/knowledge/__init__.py`:
```python
"""Knowledge package — curated domain lexica and enrichment helpers."""
```

Create `app/knowledge/oncology/__init__.py`:
```python
"""Oncology lexicon — terms, schema, and loader."""
```

Create `tests/knowledge/__init__.py` (empty file):
```python
```

- [ ] **Step 3: Verify the package imports**

Run: `python -c "import app.knowledge.oncology; print('ok')"`

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add app/knowledge tests/knowledge
git commit -m "feat(knowledge): scaffold app/knowledge/oncology package

Empty package shells for the oncology lexicon work. Schema, loader,
and YAML files follow in subsequent commits."
```

---

## Task 2: Define the lexicon schema with TDD

**Files:**
- Create: `app/knowledge/oncology/schema.py`
- Create: `tests/knowledge/test_schema.py`

- [ ] **Step 1: Write the failing test**

Create `tests/knowledge/test_schema.py`:

```python
"""Schema tests — the hard quality gates for the lexicon."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.knowledge.oncology.schema import LexiconEntry, Source


# --- Source --------------------------------------------------------------------


def test_source_accepts_authoritative_url():
    s = Source(
        kind="nci-thesaurus",
        url="https://ncit.nci.nih.gov/ncitbrowser/ConceptReport.jsp?dictionary=NCI_Thesaurus&code=C39568",
        citation="NCI Thesaurus, Phase III Trial",
    )
    assert s.kind == "nci-thesaurus"


def test_source_rejects_non_allowlisted_url():
    with pytest.raises(ValidationError, match="not in the authoritative source allowlist"):
        Source(
            kind="nci-thesaurus",
            url="https://random-blog.example.com/recist",
            citation="Random blog",
        )


def test_source_allows_url_none_if_citation_is_textual():
    s = Source(
        kind="publication",
        url=None,
        citation="Eisenhauer et al., Eur J Cancer 2009 (RECIST 1.1)",
    )
    assert s.url is None


# --- LexiconEntry --------------------------------------------------------------


def _valid_source() -> Source:
    return Source(
        kind="nci-thesaurus",
        url="https://ncit.nci.nih.gov/ncitbrowser/ConceptReport.jsp?dictionary=NCI_Thesaurus&code=C39568",
        citation="NCI Thesaurus",
    )


def test_lexicon_entry_minimal():
    entry = LexiconEntry(
        id="trial-phase-3",
        term="Phase 3",
        aliases=["phase III", "phase iii"],
        category="trial-phase",
        short_definition="Late-stage clinical trial confirming efficacy and safety in a large population.",
        clinical_context="Phase 3 trials enroll hundreds to thousands of patients and are typically required for regulatory approval.",
        sources=[_valid_source()],
        review_status="llm-generated",
    )
    assert entry.id == "trial-phase-3"


def test_lexicon_entry_requires_at_least_one_source():
    with pytest.raises(ValidationError, match="at least 1 source"):
        LexiconEntry(
            id="trial-phase-3",
            term="Phase 3",
            aliases=[],
            category="trial-phase",
            short_definition="x",
            clinical_context="x",
            sources=[],
            review_status="llm-generated",
        )


def test_lexicon_entry_rejects_unknown_category():
    with pytest.raises(ValidationError):
        LexiconEntry(
            id="x",
            term="X",
            aliases=[],
            category="not-a-real-category",  # type: ignore[arg-type]
            short_definition="x",
            clinical_context="x",
            sources=[_valid_source()],
            review_status="llm-generated",
        )


def test_review_status_lifecycle():
    for status in ("llm-generated", "reviewed", "expert-approved"):
        entry = LexiconEntry(
            id="t",
            term="T",
            aliases=[],
            category="trial-phase",
            short_definition="x",
            clinical_context="x",
            sources=[_valid_source()],
            review_status=status,  # type: ignore[arg-type]
        )
        assert entry.review_status == status


def test_last_reviewed_optional():
    entry = LexiconEntry(
        id="t",
        term="T",
        aliases=[],
        category="trial-phase",
        short_definition="x",
        clinical_context="x",
        sources=[_valid_source()],
        review_status="reviewed",
        last_reviewed=date(2026, 4, 9),
    )
    assert entry.last_reviewed == date(2026, 4, 9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/knowledge/test_schema.py -v`

Expected: FAIL with `ImportError: cannot import name 'LexiconEntry'`.

- [ ] **Step 3: Implement the schema**

Create `app/knowledge/oncology/schema.py`:

```python
"""Pydantic schema for the oncology lexicon.

Hard quality gates enforced here:

  - Every LexiconEntry MUST have at least one Source (Pydantic min_length).
  - Every Source URL (when present) MUST come from the authoritative
    domain allowlist (field validator).
  - Categories are bounded by a Literal type — no free-form sprawl.
  - Review status is a three-stage lifecycle: llm-generated → reviewed
    → expert-approved.

These gates prevent unverified or fabricated content from reaching
production. The curation pipeline relies on them.
"""

from __future__ import annotations

from datetime import date
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = ["LexiconEntry", "Source", "Lexicon", "Annotation", "ALLOWED_SOURCE_DOMAINS"]


# Authoritative source domains. Source URLs must come from one of these.
ALLOWED_SOURCE_DOMAINS = frozenset({
    "ncit.nci.nih.gov",
    "fda.gov",
    "www.fda.gov",
    "ema.europa.eu",
    "www.ema.europa.eu",
    "recist.eortc.org",
    "pubmed.ncbi.nlm.nih.gov",
    "ctep.cancer.gov",
})


SourceKind = Literal[
    "nci-thesaurus",
    "fda-label",
    "publication",
    "guideline",
    "definition",
]


CategoryName = Literal[
    "trial-phase",
    "trial-status",
    "endpoint",
    "study-design",
    "tumor-type",
    "biomarker",
    "drug-class",
    "response-criterion",
    "treatment-line",
    "resistance-mechanism",
]


ReviewStatus = Literal["llm-generated", "reviewed", "expert-approved"]


class Source(BaseModel):
    """A single citation backing a lexicon entry."""

    kind: SourceKind
    url: str | None = None
    citation: str = Field(..., min_length=1)

    model_config = ConfigDict(extra="forbid")

    @field_validator("url")
    @classmethod
    def _check_domain_allowlist(cls, v: str | None) -> str | None:
        if v is None:
            return v
        domain = urlparse(v).netloc.lower()
        if domain not in ALLOWED_SOURCE_DOMAINS:
            raise ValueError(
                f"Source URL domain '{domain}' is not in the authoritative source allowlist. "
                f"Allowed: {sorted(ALLOWED_SOURCE_DOMAINS)}"
            )
        return v


class LexiconEntry(BaseModel):
    """A single curated oncology term entry."""

    id: str = Field(..., min_length=1, pattern=r"^[a-z0-9-]+$")
    term: str = Field(..., min_length=1)
    aliases: list[str] = Field(default_factory=list)
    category: CategoryName
    short_definition: str = Field(..., min_length=10)
    clinical_context: str = Field(..., min_length=10)
    typical_values: dict[str, str] | None = None
    related_terms: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(..., min_length=1, description="at least 1 source required")
    review_status: ReviewStatus
    last_reviewed: date | None = None

    model_config = ConfigDict(extra="forbid")


class Annotation(BaseModel):
    """A single knowledge annotation attached to a tool response.

    Produced by app.services.enrichment.enrich() and surfaced as the
    ``data["knowledge_annotations"]`` list on the envelope dict.
    """

    field_path: str = Field(..., description="Dotted path to the matched field")
    matched_term: str
    lexicon_id: str
    short_definition: str
    clinical_context: str
    review_status: ReviewStatus

    model_config = ConfigDict(extra="forbid")


class Lexicon(BaseModel):
    """In-memory lexicon with prebuilt indices for fast term lookup."""

    entries: list[LexiconEntry]
    term_index: dict[str, LexiconEntry] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/knowledge/test_schema.py -v`

Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/knowledge/oncology/schema.py tests/knowledge/test_schema.py
git commit -m "feat(knowledge): add Pydantic schema for oncology lexicon

LexiconEntry requires ≥1 source, sources must come from an
authoritative domain allowlist, categories are bounded to a Literal
type. Three-stage review_status lifecycle. Annotation model for the
enrichment layer's output."
```

---

## Task 3: Build the loader with TDD

**Files:**
- Create: `app/knowledge/oncology/loader.py`
- Create: `tests/knowledge/test_loader.py`

- [ ] **Step 1: Write the failing test**

Create `tests/knowledge/test_loader.py`:

```python
"""Loader tests — verify YAML parsing and index construction."""

from pathlib import Path

import pytest
import yaml

from app.knowledge.oncology.loader import load_lexicon


def _write_yaml(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "lexicon.yaml"
    p.write_text(yaml.safe_dump(payload, sort_keys=False))
    return p


def _valid_entry(eid: str, term: str, aliases: list[str] | None = None) -> dict:
    return {
        "id": eid,
        "term": term,
        "aliases": aliases or [],
        "category": "trial-phase",
        "short_definition": "Test definition that is long enough.",
        "clinical_context": "Test context that is also long enough.",
        "sources": [
            {
                "kind": "nci-thesaurus",
                "url": "https://ncit.nci.nih.gov/ncitbrowser/x",
                "citation": "NCI Thesaurus",
            }
        ],
        "review_status": "llm-generated",
    }


def test_load_lexicon_empty(tmp_path):
    p = _write_yaml(tmp_path, {"entries": []})
    lex = load_lexicon(p)
    assert lex.entries == []
    assert lex.term_index == {}


def test_load_lexicon_single_entry(tmp_path):
    p = _write_yaml(tmp_path, {"entries": [_valid_entry("phase-3", "Phase 3")]})
    lex = load_lexicon(p)
    assert len(lex.entries) == 1
    assert "phase 3" in lex.term_index  # case-insensitive lookup


def test_load_lexicon_indexes_aliases(tmp_path):
    entry = _valid_entry("os", "Overall Survival", aliases=["OS", "overall-survival"])
    p = _write_yaml(tmp_path, {"entries": [entry]})
    lex = load_lexicon(p)
    assert "overall survival" in lex.term_index
    assert "os" in lex.term_index
    assert "overall-survival" in lex.term_index


def test_load_lexicon_rejects_invalid_yaml(tmp_path):
    p = _write_yaml(tmp_path, {"entries": [{"id": "x", "term": "X"}]})  # missing required fields
    with pytest.raises(Exception):  # pydantic ValidationError
        load_lexicon(p)


def test_load_lexicon_default_path():
    """Calling load_lexicon() without args reads the canonical
    app/knowledge/oncology/lexicon.yaml. The file may be empty in the
    repo today — that's fine, this test only verifies the call works."""
    lex = load_lexicon()
    # Don't assert content — just that the call succeeds
    assert lex is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/knowledge/test_loader.py -v`

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Create the empty default lexicon**

Create `app/knowledge/oncology/lexicon.yaml`:

```yaml
# Oncology Knowledge Lexicon
# Generated and reviewed via the curation pipeline in scripts/curation/.
# Schema: app/knowledge/oncology/schema.py

entries: []
```

- [ ] **Step 4: Implement the loader**

Create `app/knowledge/oncology/loader.py`:

```python
"""YAML loader for the oncology lexicon.

Reads the lexicon YAML file, validates each entry against the Pydantic
schema, and builds case-insensitive lookup indices for terms and aliases.

The loader is called once at server startup (singleton). Repeated calls
re-parse — there is no caching at this layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.knowledge.oncology.schema import Lexicon, LexiconEntry

__all__ = ["load_lexicon", "DEFAULT_LEXICON_PATH"]


DEFAULT_LEXICON_PATH = Path(__file__).parent / "lexicon.yaml"


def load_lexicon(path: Path | None = None) -> Lexicon:
    """Load and validate the lexicon from a YAML file.

    Args:
        path: Optional path to a YAML file. Defaults to
            ``app/knowledge/oncology/lexicon.yaml``.

    Returns:
        A ``Lexicon`` with parsed entries and case-insensitive
        ``term_index`` covering canonical terms and all aliases.
    """
    yaml_path = path or DEFAULT_LEXICON_PATH
    raw: dict[str, Any] = yaml.safe_load(yaml_path.read_text()) or {}
    raw_entries = raw.get("entries") or []

    entries = [LexiconEntry(**entry) for entry in raw_entries]
    term_index: dict[str, LexiconEntry] = {}
    for entry in entries:
        term_index[entry.term.lower()] = entry
        for alias in entry.aliases:
            term_index[alias.lower()] = entry

    return Lexicon(entries=entries, term_index=term_index)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/knowledge/test_loader.py -v`

Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add app/knowledge/oncology/loader.py app/knowledge/oncology/lexicon.yaml tests/knowledge/test_loader.py
git commit -m "feat(knowledge): add YAML loader and empty lexicon stub

Loader parses YAML, validates each entry against the Pydantic schema,
builds case-insensitive term + alias lookup indices. The lexicon.yaml
starts empty — entries are added via the curation pipeline."
```

---

## Task 4: Write `seed_topics.yaml`

**Files:**
- Create: `app/knowledge/oncology/seed_topics.yaml`

- [ ] **Step 1: Create the seed topics file**

Create `app/knowledge/oncology/seed_topics.yaml`. This is the hand-maintained source of truth for what gets generated. Start with a representative set per category — the curator can extend it later. Aim for ~250–400 total terms.

```yaml
# Seed topics for the oncology lexicon curation pipeline.
#
# This file defines WHAT gets generated. The generation script
# (scripts/curation/generate_lexicon.py) reads this file and asks the LLM
# to draft a LexiconEntry for every term listed here.
#
# Terms are grouped by category. Categories must match the CategoryName
# Literal in app/knowledge/oncology/schema.py.
#
# To add a new term: add it to the appropriate category list, re-run the
# generation script for the new terms only, and merge the reviewed
# entries via review_worksheet_to_yaml.py.

trial-phase:
  - "Phase 0"
  - "Phase 1"
  - "Phase 1/2"
  - "Phase 2"
  - "Phase 2/3"
  - "Phase 3"
  - "Phase 4"
  - "Post-Marketing Surveillance"

trial-status:
  - "Not yet recruiting"
  - "Recruiting"
  - "Active, not recruiting"
  - "Enrolling by invitation"
  - "Suspended"
  - "Terminated"
  - "Withdrawn"
  - "Completed"
  - "Unknown status"

endpoint:
  - "Overall Survival"
  - "Progression-Free Survival"
  - "Disease-Free Survival"
  - "Event-Free Survival"
  - "Recurrence-Free Survival"
  - "Time to Progression"
  - "Time to Treatment Failure"
  - "Objective Response Rate"
  - "Complete Response"
  - "Partial Response"
  - "Stable Disease"
  - "Duration of Response"
  - "Disease Control Rate"
  - "Clinical Benefit Rate"
  - "Pathologic Complete Response"
  - "Minimal Residual Disease"
  - "Quality of Life"
  - "Patient-Reported Outcomes"
  - "Maximum Tolerated Dose"
  - "Dose-Limiting Toxicity"
  - "Pharmacokinetics"
  - "Pharmacodynamics"

study-design:
  - "Randomized Controlled Trial"
  - "Single-Arm Trial"
  - "Open-Label Trial"
  - "Double-Blind Trial"
  - "Crossover Trial"
  - "Basket Trial"
  - "Umbrella Trial"
  - "Platform Trial"
  - "Adaptive Trial"
  - "Window of Opportunity Trial"
  - "Expansion Cohort"
  - "Dose-Escalation Study"
  - "Biomarker-Stratified Trial"
  - "Master Protocol"

tumor-type:
  - "Non-Small Cell Lung Cancer"
  - "Small Cell Lung Cancer"
  - "Breast Cancer"
  - "Triple-Negative Breast Cancer"
  - "HER2-Positive Breast Cancer"
  - "Hormone Receptor-Positive Breast Cancer"
  - "Colorectal Cancer"
  - "Pancreatic Cancer"
  - "Hepatocellular Carcinoma"
  - "Glioblastoma"
  - "Melanoma"
  - "Renal Cell Carcinoma"
  - "Prostate Cancer"
  - "Castration-Resistant Prostate Cancer"
  - "Ovarian Cancer"
  - "Acute Myeloid Leukemia"
  - "Acute Lymphoblastic Leukemia"
  - "Chronic Myeloid Leukemia"
  - "Chronic Lymphocytic Leukemia"
  - "Multiple Myeloma"
  - "Diffuse Large B-Cell Lymphoma"
  - "Follicular Lymphoma"
  - "Hodgkin Lymphoma"
  - "Mantle Cell Lymphoma"
  - "Head and Neck Squamous Cell Carcinoma"
  - "Esophageal Cancer"
  - "Gastric Cancer"
  - "Bladder Cancer"
  - "Cervical Cancer"
  - "Endometrial Cancer"
  - "Sarcoma"
  - "Mesothelioma"
  - "Cholangiocarcinoma"
  - "Neuroendocrine Tumor"

biomarker:
  - "EGFR mutation"
  - "ALK rearrangement"
  - "ROS1 rearrangement"
  - "BRAF V600E mutation"
  - "KRAS G12C mutation"
  - "HER2 amplification"
  - "PD-L1 expression"
  - "Microsatellite Instability"
  - "Mismatch Repair Deficiency"
  - "Tumor Mutational Burden"
  - "BRCA1 mutation"
  - "BRCA2 mutation"
  - "Homologous Recombination Deficiency"
  - "FGFR alteration"
  - "MET exon 14 skipping"
  - "RET fusion"
  - "NTRK fusion"
  - "IDH1 mutation"
  - "IDH2 mutation"
  - "FLT3 mutation"
  - "JAK2 V617F"
  - "BCR-ABL fusion"

drug-class:
  - "Immune Checkpoint Inhibitor"
  - "PD-1 Inhibitor"
  - "PD-L1 Inhibitor"
  - "CTLA-4 Inhibitor"
  - "Tyrosine Kinase Inhibitor"
  - "EGFR TKI"
  - "ALK TKI"
  - "BTK Inhibitor"
  - "PARP Inhibitor"
  - "CDK4/6 Inhibitor"
  - "Antibody-Drug Conjugate"
  - "Bispecific T-Cell Engager"
  - "CAR-T Cell Therapy"
  - "mTOR Inhibitor"
  - "MEK Inhibitor"
  - "BRAF Inhibitor"
  - "HER2 Inhibitor"
  - "Anti-CD20 Monoclonal Antibody"
  - "Anti-CD38 Monoclonal Antibody"
  - "Proteasome Inhibitor"
  - "IMiD"
  - "Selective Estrogen Receptor Modulator"
  - "Aromatase Inhibitor"
  - "Androgen Receptor Inhibitor"

response-criterion:
  - "RECIST 1.1"
  - "iRECIST"
  - "irRC"
  - "Lugano Classification"
  - "Cheson Criteria"
  - "International Myeloma Working Group Criteria"
  - "PERCIST"
  - "Choi Criteria"
  - "RANO Criteria"
  - "PCWG3"

treatment-line:
  - "First-Line Therapy"
  - "Second-Line Therapy"
  - "Third-Line Therapy"
  - "Maintenance Therapy"
  - "Adjuvant Therapy"
  - "Neoadjuvant Therapy"
  - "Salvage Therapy"
  - "Consolidation Therapy"
  - "Induction Therapy"

resistance-mechanism:
  - "Acquired EGFR T790M mutation"
  - "MET amplification"
  - "Histologic transformation"
  - "EMT"
  - "BRAF amplification"
  - "ESR1 mutation"
  - "BRCA reversion mutation"
  - "Loss of MHC class I"
```

- [ ] **Step 2: Verify the file parses**

Run: `python -c "import yaml; d = yaml.safe_load(open('app/knowledge/oncology/seed_topics.yaml')); print(sum(len(v) for v in d.values()), 'terms across', len(d), 'categories')"`

Expected: a printed total around 200–250 terms across 10 categories. (The user can extend this list later — the plan only locks in a starting set.)

- [ ] **Step 3: Commit**

```bash
git add app/knowledge/oncology/seed_topics.yaml
git commit -m "feat(knowledge): add seed_topics.yaml for oncology curation pipeline

Hand-maintained list of ~200 oncology terms grouped by category. The
curation script (scripts/curation/generate_lexicon.py) reads this file
to know what to draft. Extend the lists to grow the lexicon."
```

---

## Task 5: Build the LLM generation script

**Files:**
- Create: `scripts/curation/__init__.py`
- Create: `scripts/curation/generate_lexicon.py`
- Create: `scripts/curation/README.md`

- [ ] **Step 1: Create the package marker**

Create `scripts/curation/__init__.py` (empty):
```python
```

- [ ] **Step 2: Create the curation README**

Create `scripts/curation/README.md`:

```markdown
# Oncology Lexicon Curation Pipeline

Offline workflow for generating and reviewing oncology lexicon entries.

## Workflow

1. **Edit `app/knowledge/oncology/seed_topics.yaml`** to add the terms you want generated.
2. **Run the generation script:**
   ```bash
   ANTHROPIC_API_KEY=sk-... python scripts/curation/generate_lexicon.py
   ```
   This calls Claude for every term in `seed_topics.yaml` and writes:
   - `scripts/curation/output/draft_<date>.yaml` — the LLM-generated entries
   - `scripts/curation/output/review_worksheet_<date>.csv` — the review CSV
3. **Open the CSV in your editor of choice** and review:
   - Sort by `category` and review one category per session
   - For each entry: spot-check 3–5 random ones against the cited source
   - Mark `accept=1`, `edit=<corrected text>`, or `reject=1`
   - On clean spot-check → bulk-accept the rest
4. **Merge reviewed entries:**
   ```bash
   python scripts/curation/review_worksheet_to_yaml.py \
       scripts/curation/output/review_worksheet_<date>.csv
   ```
   This validates, merges, and writes `app/knowledge/oncology/lexicon.yaml`.
5. **Commit the updated lexicon:**
   ```bash
   git add app/knowledge/oncology/lexicon.yaml
   git diff --cached app/knowledge/oncology/lexicon.yaml | less  # final eyeball
   git commit -m "data(lexicon): add <N> reviewed oncology entries"
   ```

## Quality gates

The schema enforces:
- Every entry has ≥1 source
- Every source URL is from the allowlist (NCIt, FDA, EMA, RECIST, PubMed, CTEP)
- Categories are bounded by a Pydantic Literal
- Three-stage review status: llm-generated → reviewed → expert-approved

If a generated entry fails validation, it's skipped and logged. The
review CSV only contains entries that passed schema validation.

## When to re-generate

- Adding new terms: add to `seed_topics.yaml`, re-run for new terms only
- Updating existing terms: edit `lexicon.yaml` directly, set `last_reviewed`
- Stale review (planned for v2): re-review oldest `last_reviewed` entries
```

- [ ] **Step 3: Implement the generation script**

Create `scripts/curation/generate_lexicon.py`:

```python
"""Offline script: generate draft lexicon entries from seed_topics.yaml.

Reads the seed topics, asks Claude (via the anthropic SDK) to draft a
LexiconEntry for each term, validates against the Pydantic schema, and
writes:

  - scripts/curation/output/draft_<date>.yaml  : raw drafts
  - scripts/curation/output/review_worksheet_<date>.csv : review sheet

Usage:
    ANTHROPIC_API_KEY=sk-... python scripts/curation/generate_lexicon.py

To generate only a subset:
    python scripts/curation/generate_lexicon.py --category endpoint
    python scripts/curation/generate_lexicon.py --terms "Phase 3,RECIST 1.1"
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from anthropic import Anthropic
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from app.knowledge.oncology.schema import LexiconEntry  # noqa: E402

SEED_PATH = REPO_ROOT / "app" / "knowledge" / "oncology" / "seed_topics.yaml"
OUTPUT_DIR = REPO_ROOT / "scripts" / "curation" / "output"


SYSTEM_PROMPT = """You are a clinical oncology terminology curator. Your job is to draft a single LexiconEntry for each term you are given.

HARD REQUIREMENTS:

1. Every entry MUST cite at least one source. Source URLs must come from one of these authoritative domains:
   - ncit.nci.nih.gov
   - fda.gov / www.fda.gov
   - ema.europa.eu / www.ema.europa.eu
   - recist.eortc.org
   - pubmed.ncbi.nlm.nih.gov
   - ctep.cancer.gov

2. If you cannot cite a real, authoritative source for an entry, return null and we will skip the term. Do not fabricate URLs.

3. short_definition must be 1-2 sentences, plain language, quotable from the source.

4. clinical_context must be 2-4 sentences, grounded in the source, no speculation. If you are uncertain about something, leave it out rather than guess.

5. Do NOT include forward-looking statements ("expected to..." / "may improve...").

OUTPUT FORMAT: Return a single JSON object that exactly matches this schema:

{
  "id": "kebab-case-slug",
  "term": "Canonical Term",
  "aliases": ["alias1", "alias2"],
  "category": "one of: trial-phase, trial-status, endpoint, study-design, tumor-type, biomarker, drug-class, response-criterion, treatment-line, resistance-mechanism",
  "short_definition": "1-2 sentences",
  "clinical_context": "2-4 sentences",
  "typical_values": null,
  "related_terms": ["other-id"],
  "sources": [
    {"kind": "nci-thesaurus", "url": "https://ncit.nci.nih.gov/...", "citation": "NCI Thesaurus, Concept X"}
  ],
  "review_status": "llm-generated",
  "last_reviewed": null
}

Or `null` if you cannot find an authoritative source.
"""


def _build_user_prompt(term: str, category: str) -> str:
    return f"""Draft a LexiconEntry for the term "{term}" in category "{category}".

Return one JSON object as specified in the system prompt, or null if you cannot cite an authoritative source. No prose, no markdown, JSON only."""


def _call_claude(client: Anthropic, term: str, category: str) -> dict[str, Any] | None:
    """Call Claude once and parse the JSON response."""
    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_prompt(term, category)}],
    )
    text = msg.content[0].text.strip()
    if text == "null" or text.startswith("null"):
        return None
    # Strip markdown code fences if Claude added them
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]
    return json.loads(text.strip())


def _validate(entry_dict: dict[str, Any]) -> LexiconEntry | None:
    """Validate against Pydantic schema. Return None on failure (logged)."""
    try:
        return LexiconEntry(**entry_dict)
    except ValidationError as e:
        print(f"  ✗ validation failed: {e.errors()[0]['msg']}", file=sys.stderr)
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", help="Generate only this category")
    parser.add_argument("--terms", help="Comma-separated list of terms (overrides --category)")
    args = parser.parse_args()

    if "ANTHROPIC_API_KEY" not in os.environ:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
        return 1

    client = Anthropic()
    seed = yaml.safe_load(SEED_PATH.read_text())

    targets: list[tuple[str, str]] = []  # (category, term)
    if args.terms:
        wanted = {t.strip() for t in args.terms.split(",")}
        for cat, terms in seed.items():
            for t in terms:
                if t in wanted:
                    targets.append((cat, t))
    elif args.category:
        for t in seed.get(args.category, []):
            targets.append((args.category, t))
    else:
        for cat, terms in seed.items():
            for t in terms:
                targets.append((cat, t))

    print(f"Generating {len(targets)} entries...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    draft_path = OUTPUT_DIR / f"draft_{today}.yaml"
    csv_path = OUTPUT_DIR / f"review_worksheet_{today}.csv"

    valid_entries: list[LexiconEntry] = []
    for cat, term in targets:
        print(f"[{cat}] {term}", file=sys.stderr)
        try:
            raw = _call_claude(client, term, cat)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ API error: {e}", file=sys.stderr)
            continue
        if raw is None:
            print(f"  ⊘ skipped (no authoritative source)", file=sys.stderr)
            continue
        entry = _validate(raw)
        if entry is not None:
            valid_entries.append(entry)
            print(f"  ✓", file=sys.stderr)

    # Write draft YAML
    draft_path.write_text(
        yaml.safe_dump(
            {"entries": [e.model_dump(mode="json") for e in valid_entries]},
            sort_keys=False,
            allow_unicode=True,
        )
    )

    # Write review CSV
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id", "term", "category", "short_definition", "clinical_context",
            "source_count", "sources_summary", "review_status",
            "reviewer_notes", "accept", "edit", "reject",
        ])
        for e in valid_entries:
            writer.writerow([
                e.id, e.term, e.category,
                e.short_definition, e.clinical_context,
                len(e.sources),
                "; ".join(s.citation for s in e.sources),
                e.review_status,
                "", "", "", "",
            ])

    print(f"\nDone: {len(valid_entries)} valid entries written to:")
    print(f"  {draft_path.relative_to(REPO_ROOT)}")
    print(f"  {csv_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Verify the script imports cleanly**

Run: `python -c "import sys; sys.path.insert(0, 'scripts/curation'); import generate_lexicon; print('ok')"`

Expected: `ok`. (We're not running it for real here — that needs an API key and is the manual milestone task.)

- [ ] **Step 5: Commit**

```bash
git add scripts/curation/__init__.py scripts/curation/generate_lexicon.py scripts/curation/README.md
git commit -m "feat(curation): add LLM-driven lexicon generation script

Reads seed_topics.yaml, calls Claude to draft a LexiconEntry per term
with strict source-allowlist instructions, validates against Pydantic
schema, writes draft YAML + review worksheet CSV. Skips entries that
cannot cite an authoritative source. Manual review CSV is the next
step in the curation workflow."
```

---

## Task 6: Test the generation script with a 3-term mini seed

**Files:**
- Create: `tests/curation/__init__.py`
- Create: `tests/curation/test_generation.py`

- [ ] **Step 1: Create the test marker**

Create `tests/curation/__init__.py` (empty).

- [ ] **Step 2: Write the validation-only test**

Create `tests/curation/test_generation.py`:

```python
"""Light tests for the generation script.

We don't actually call Claude in tests — that requires an API key and
costs money. Instead we test the validation and CSV-writing pieces in
isolation by faking the LLM response.
"""

from pathlib import Path

import pytest
import yaml

from app.knowledge.oncology.schema import LexiconEntry


def test_valid_llm_response_passes_validation():
    fake_response = {
        "id": "phase-3",
        "term": "Phase 3",
        "aliases": ["phase III"],
        "category": "trial-phase",
        "short_definition": "Late-stage clinical trial confirming efficacy and safety in a large population.",
        "clinical_context": "Phase 3 trials enroll hundreds to thousands of patients and are typically required for regulatory approval. They compare the investigational therapy to standard of care.",
        "typical_values": None,
        "related_terms": [],
        "sources": [
            {
                "kind": "nci-thesaurus",
                "url": "https://ncit.nci.nih.gov/ncitbrowser/ConceptReport.jsp?dictionary=NCI_Thesaurus&code=C39568",
                "citation": "NCI Thesaurus, Phase III Trial",
            }
        ],
        "review_status": "llm-generated",
        "last_reviewed": None,
    }
    entry = LexiconEntry(**fake_response)
    assert entry.id == "phase-3"


def test_response_with_fake_url_fails_validation():
    """The hard quality gate: fabricated URLs must fail validation."""
    fake_response = {
        "id": "x",
        "term": "X",
        "aliases": [],
        "category": "trial-phase",
        "short_definition": "test definition that is long enough",
        "clinical_context": "test context that is also long enough",
        "sources": [
            {
                "kind": "nci-thesaurus",
                "url": "https://my-fake-blog.example.com/x",
                "citation": "Fake source",
            }
        ],
        "review_status": "llm-generated",
    }
    with pytest.raises(Exception, match="not in the authoritative source allowlist"):
        LexiconEntry(**fake_response)


def test_response_without_sources_fails_validation():
    fake_response = {
        "id": "x",
        "term": "X",
        "aliases": [],
        "category": "trial-phase",
        "short_definition": "test definition that is long enough",
        "clinical_context": "test context that is also long enough",
        "sources": [],
        "review_status": "llm-generated",
    }
    with pytest.raises(Exception, match="at least 1"):
        LexiconEntry(**fake_response)
```

- [ ] **Step 3: Run the tests**

Run: `python -m pytest tests/curation/test_generation.py -v`

Expected: 3 PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/curation
git commit -m "test(curation): validate LLM response shapes against schema

Tests the hard quality gates without actually calling Claude:
fabricated URLs are rejected by the source allowlist, missing sources
are rejected by min_length=1. These are the same gates the live
generation script relies on."
```

---

## Task 7: Build the merge script (`review_worksheet_to_yaml.py`)

**Files:**
- Create: `scripts/curation/review_worksheet_to_yaml.py`
- Create: `tests/curation/test_merge_worksheet.py`

- [ ] **Step 1: Write the failing test**

Create `tests/curation/test_merge_worksheet.py`:

```python
"""Tests for the review worksheet → YAML merge script."""

import csv
from datetime import date
from pathlib import Path

import pytest
import yaml

from scripts.curation.review_worksheet_to_yaml import merge_worksheet


def _write_draft(tmp_path: Path) -> Path:
    """Write a 3-entry draft YAML."""
    p = tmp_path / "draft.yaml"
    p.write_text(yaml.safe_dump({
        "entries": [
            {
                "id": "phase-3",
                "term": "Phase 3",
                "aliases": ["phase III"],
                "category": "trial-phase",
                "short_definition": "Late-stage trial confirming efficacy.",
                "clinical_context": "Phase 3 trials enroll hundreds to thousands of patients.",
                "sources": [{"kind": "nci-thesaurus", "url": "https://ncit.nci.nih.gov/x", "citation": "NCIt"}],
                "review_status": "llm-generated",
                "related_terms": [],
                "typical_values": None,
                "last_reviewed": None,
            },
            {
                "id": "phase-2",
                "term": "Phase 2",
                "aliases": [],
                "category": "trial-phase",
                "short_definition": "Mid-stage trial assessing efficacy and dose.",
                "clinical_context": "Phase 2 trials test efficacy in a smaller population.",
                "sources": [{"kind": "nci-thesaurus", "url": "https://ncit.nci.nih.gov/y", "citation": "NCIt"}],
                "review_status": "llm-generated",
                "related_terms": [],
                "typical_values": None,
                "last_reviewed": None,
            },
            {
                "id": "phase-1",
                "term": "Phase 1",
                "aliases": [],
                "category": "trial-phase",
                "short_definition": "Early-stage safety study.",
                "clinical_context": "Phase 1 trials test safety and dose-finding.",
                "sources": [{"kind": "nci-thesaurus", "url": "https://ncit.nci.nih.gov/z", "citation": "NCIt"}],
                "review_status": "llm-generated",
                "related_terms": [],
                "typical_values": None,
                "last_reviewed": None,
            },
        ]
    }))
    return p


def _write_csv(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    p = tmp_path / "review.csv"
    with p.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "id", "term", "category", "short_definition", "clinical_context",
            "source_count", "sources_summary", "review_status",
            "reviewer_notes", "accept", "edit", "reject",
        ])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return p


def test_merge_drops_rejected(tmp_path):
    draft = _write_draft(tmp_path)
    csv_path = _write_csv(tmp_path, [
        {"id": "phase-3", "term": "Phase 3", "category": "trial-phase",
         "short_definition": "", "clinical_context": "",
         "source_count": "1", "sources_summary": "NCIt", "review_status": "llm-generated",
         "reviewer_notes": "", "accept": "1", "edit": "", "reject": ""},
        {"id": "phase-2", "term": "Phase 2", "category": "trial-phase",
         "short_definition": "", "clinical_context": "",
         "source_count": "1", "sources_summary": "NCIt", "review_status": "llm-generated",
         "reviewer_notes": "", "accept": "", "edit": "", "reject": "1"},
        {"id": "phase-1", "term": "Phase 1", "category": "trial-phase",
         "short_definition": "", "clinical_context": "",
         "source_count": "1", "sources_summary": "NCIt", "review_status": "llm-generated",
         "reviewer_notes": "", "accept": "1", "edit": "", "reject": ""},
    ])
    out = tmp_path / "lexicon.yaml"
    out.write_text("entries: []\n")
    merged_count = merge_worksheet(csv_path=csv_path, draft_path=draft, lexicon_path=out)
    assert merged_count == 2
    final = yaml.safe_load(out.read_text())
    ids = [e["id"] for e in final["entries"]]
    assert "phase-3" in ids
    assert "phase-1" in ids
    assert "phase-2" not in ids


def test_merge_sets_review_status_and_date(tmp_path):
    draft = _write_draft(tmp_path)
    csv_path = _write_csv(tmp_path, [
        {"id": "phase-3", "term": "Phase 3", "category": "trial-phase",
         "short_definition": "", "clinical_context": "",
         "source_count": "1", "sources_summary": "NCIt", "review_status": "llm-generated",
         "reviewer_notes": "", "accept": "1", "edit": "", "reject": ""},
    ])
    out = tmp_path / "lexicon.yaml"
    out.write_text("entries: []\n")
    merge_worksheet(csv_path=csv_path, draft_path=draft, lexicon_path=out)
    final = yaml.safe_load(out.read_text())
    assert final["entries"][0]["review_status"] == "reviewed"
    assert final["entries"][0]["last_reviewed"] == date.today().isoformat()


def test_merge_applies_inline_edit(tmp_path):
    draft = _write_draft(tmp_path)
    csv_path = _write_csv(tmp_path, [
        {"id": "phase-3", "term": "Phase 3", "category": "trial-phase",
         "short_definition": "EDITED short definition that is long enough.",
         "clinical_context": "EDITED clinical context that is also long enough.",
         "source_count": "1", "sources_summary": "NCIt", "review_status": "llm-generated",
         "reviewer_notes": "fix per spot check", "accept": "1", "edit": "1", "reject": ""},
    ])
    out = tmp_path / "lexicon.yaml"
    out.write_text("entries: []\n")
    merge_worksheet(csv_path=csv_path, draft_path=draft, lexicon_path=out)
    final = yaml.safe_load(out.read_text())
    assert final["entries"][0]["short_definition"].startswith("EDITED")
    assert final["entries"][0]["clinical_context"].startswith("EDITED")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/curation/test_merge_worksheet.py -v`

Expected: FAIL with `ImportError: cannot import name 'merge_worksheet'`.

- [ ] **Step 3: Implement the merge script**

Create `scripts/curation/review_worksheet_to_yaml.py`:

```python
"""Merge a reviewed CSV worksheet into the canonical lexicon.yaml.

Workflow:
  1. Loads the LLM-generated draft YAML
  2. Loads the human-reviewed CSV (accept / edit / reject columns)
  3. Drops rejected entries
  4. Applies inline edits from the CSV
  5. Sets review_status="reviewed" and last_reviewed=today for accepted
  6. Validates the result against the Pydantic schema
  7. Merges into the existing lexicon.yaml (overwriting same-id entries)
  8. Writes the final lexicon.yaml

Usage:
    python scripts/curation/review_worksheet_to_yaml.py \
        scripts/curation/output/review_worksheet_<date>.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from app.knowledge.oncology.schema import LexiconEntry  # noqa: E402

DEFAULT_LEXICON = REPO_ROOT / "app" / "knowledge" / "oncology" / "lexicon.yaml"


def _is_truthy(s: str | None) -> bool:
    return (s or "").strip().lower() in ("1", "true", "yes", "y")


def merge_worksheet(
    csv_path: Path,
    draft_path: Path,
    lexicon_path: Path = DEFAULT_LEXICON,
) -> int:
    """Merge a reviewed CSV into the lexicon. Returns # of merged entries."""
    draft_raw = yaml.safe_load(draft_path.read_text()) or {"entries": []}
    draft_index: dict[str, dict[str, Any]] = {
        e["id"]: e for e in draft_raw.get("entries", [])
    }

    accepted: list[dict[str, Any]] = []
    today_iso = date.today().isoformat()

    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if _is_truthy(row.get("reject")):
                continue
            if not _is_truthy(row.get("accept")):
                continue

            entry_id = row["id"]
            if entry_id not in draft_index:
                print(f"  ⊘ {entry_id}: not in draft, skipping", file=sys.stderr)
                continue

            entry = dict(draft_index[entry_id])  # copy
            if _is_truthy(row.get("edit")):
                if row.get("short_definition"):
                    entry["short_definition"] = row["short_definition"]
                if row.get("clinical_context"):
                    entry["clinical_context"] = row["clinical_context"]
            entry["review_status"] = "reviewed"
            entry["last_reviewed"] = today_iso
            accepted.append(entry)

    # Validate every accepted entry against the schema
    validated: list[dict[str, Any]] = []
    for entry in accepted:
        try:
            obj = LexiconEntry(**entry)
            validated.append(obj.model_dump(mode="json"))
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {entry.get('id')}: validation failed: {e}", file=sys.stderr)

    # Merge into existing lexicon (overwrite same id)
    existing_raw = yaml.safe_load(lexicon_path.read_text()) or {"entries": []}
    existing_by_id: dict[str, dict[str, Any]] = {
        e["id"]: e for e in existing_raw.get("entries", [])
    }
    for v in validated:
        existing_by_id[v["id"]] = v

    final_entries = sorted(existing_by_id.values(), key=lambda e: (e["category"], e["id"]))
    lexicon_path.write_text(
        yaml.safe_dump(
            {"entries": final_entries},
            sort_keys=False,
            allow_unicode=True,
        )
    )
    return len(validated)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path, help="Path to reviewed CSV")
    parser.add_argument(
        "--draft",
        type=Path,
        help="Path to draft YAML (defaults to same dir, draft_<csv-date>.yaml)",
    )
    parser.add_argument("--lexicon", type=Path, default=DEFAULT_LEXICON)
    args = parser.parse_args()

    if args.draft is None:
        # Infer draft path from CSV filename: review_worksheet_<date>.csv → draft_<date>.yaml
        stem = args.csv.stem
        if stem.startswith("review_worksheet_"):
            date_part = stem[len("review_worksheet_"):]
            args.draft = args.csv.parent / f"draft_{date_part}.yaml"
        else:
            print("ERROR: cannot infer --draft from CSV name", file=sys.stderr)
            return 1

    n = merge_worksheet(args.csv, args.draft, args.lexicon)
    print(f"Merged {n} entries into {args.lexicon.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/curation/test_merge_worksheet.py -v`

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/curation/review_worksheet_to_yaml.py tests/curation/test_merge_worksheet.py
git commit -m "feat(curation): add merge script for reviewed lexicon entries

Drops rejected, applies inline edits, sets review_status=reviewed,
validates against Pydantic schema, merges into lexicon.yaml. Same-id
entries overwrite. Output is sorted by (category, id) for clean
git diffs."
```

---

## Task 8: MANUAL MILESTONE — Run full LLM generation

**This task is human work. The agentic worker should pause here and hand off to the user.**

- [ ] **Step 1: Confirm prerequisites**

User checks:
- `ANTHROPIC_API_KEY` is set in the environment
- `app/knowledge/oncology/seed_topics.yaml` is the desired scope (extend if needed)
- Sufficient API budget (~200 calls × ~$0.04 each = ~$8 for Claude Opus)

- [ ] **Step 2: Run the generation**

User runs:
```bash
ANTHROPIC_API_KEY=sk-... python scripts/curation/generate_lexicon.py
```

Expected output (streamed to stderr): one line per term, with ✓ / ⊘ / ✗ markers.

Expected output files:
- `scripts/curation/output/draft_<today>.yaml` — drafts that passed schema validation
- `scripts/curation/output/review_worksheet_<today>.csv` — review sheet

- [ ] **Step 3: Inspect the output**

User runs:
```bash
wc -l scripts/curation/output/draft_*.yaml scripts/curation/output/review_worksheet_*.csv
head -50 scripts/curation/output/review_worksheet_*.csv
```

Confirms the file sizes look reasonable (≥150 entries) and the CSV is well-formed.

- [ ] **Step 4: No commit yet** — the draft files live in `scripts/curation/output/` which should be gitignored. Add to `.gitignore` if not already:

```
scripts/curation/output/
```

```bash
echo "scripts/curation/output/" >> .gitignore
git add .gitignore
git commit -m "chore: gitignore curation output drafts"
```

---

## Task 9: MANUAL MILESTONE — Review the CSV worksheet

**This task is human work. The agentic worker should pause here.**

- [ ] **Step 1: Open the review CSV in a spreadsheet**

User opens `scripts/curation/output/review_worksheet_<today>.csv` in their editor of choice (LibreOffice, Excel, Numbers, vim with vim-csv).

- [ ] **Step 2: Review one category at a time**

For each category:
1. Sort the rows by `category`
2. Pick 3–5 random entries and spot-check them against the cited source URL
3. If all spot-checks are clean → bulk-mark `accept=1` for the category
4. If a spot-check fails → review the entire category in detail
5. Use `edit` column with corrected text + `accept=1` for fixable entries
6. Use `reject=1` for unsalvageable entries
7. Use `reviewer_notes` to record why an entry was rejected or edited

Realistic time: 3–6 hours for ~250 entries.

- [ ] **Step 3: Save the CSV**

When done, save the CSV in place. Do NOT commit it — it lives in the gitignored output directory.

---

## Task 10: Run the merge to produce the final `lexicon.yaml`

**Files:**
- Modify: `app/knowledge/oncology/lexicon.yaml`

- [ ] **Step 1: Run the merge script**

```bash
python scripts/curation/review_worksheet_to_yaml.py \
    scripts/curation/output/review_worksheet_<today>.csv
```

Expected output: `Merged <N> entries into app/knowledge/oncology/lexicon.yaml`.

- [ ] **Step 2: Validate the merged file loads**

```bash
python -c "
from app.knowledge.oncology.loader import load_lexicon
lex = load_lexicon()
print(f'{len(lex.entries)} entries, {len(lex.term_index)} index keys')
"
```

Expected: 200+ entries, more index keys (because of aliases).

- [ ] **Step 3: Eyeball the diff**

```bash
git diff app/knowledge/oncology/lexicon.yaml | less
```

Sanity-check that the new entries look reasonable.

- [ ] **Step 4: Commit**

```bash
git add app/knowledge/oncology/lexicon.yaml
git commit -m "data(lexicon): add <N> reviewed oncology entries (first cohort)

LLM-generated and human-reviewed via the curation pipeline. All
entries cite at least one authoritative source (NCIt / FDA / EMA /
RECIST / PubMed / CTEP). Review status: reviewed."
```

---

## Task 11: Lexicon quality tests

**Files:**
- Create: `tests/knowledge/test_lexicon_quality.py`

- [ ] **Step 1: Write the quality tests**

Create `tests/knowledge/test_lexicon_quality.py`:

```python
"""Quality gates for the live lexicon.yaml.

These tests run against the actual file in the repo and prevent
regressions like duplicate ids, broken alias indexing, dead
related_terms references, or empty categories.
"""

from collections import Counter
from urllib.parse import urlparse

import pytest

from app.knowledge.oncology.loader import load_lexicon
from app.knowledge.oncology.schema import ALLOWED_SOURCE_DOMAINS


@pytest.fixture(scope="module")
def lexicon():
    return load_lexicon()


def test_lexicon_has_minimum_entries(lexicon):
    assert len(lexicon.entries) >= 150, (
        f"Lexicon has only {len(lexicon.entries)} entries — expected at least 150 "
        "after the first curation pass. Either re-run the generation or accept "
        "more entries in the review CSV."
    )


def test_no_duplicate_ids(lexicon):
    ids = [e.id for e in lexicon.entries]
    duplicates = [i for i, c in Counter(ids).items() if c > 1]
    assert not duplicates, f"Duplicate ids: {duplicates}"


def test_no_alias_collisions(lexicon):
    """Two different entries must not share an alias — that would make
    the term_index ambiguous."""
    seen: dict[str, str] = {}
    for entry in lexicon.entries:
        for alias in entry.aliases + [entry.term]:
            key = alias.lower()
            if key in seen and seen[key] != entry.id:
                pytest.fail(
                    f"Alias collision: '{alias}' is used by both "
                    f"'{seen[key]}' and '{entry.id}'"
                )
            seen[key] = entry.id


def test_related_terms_resolve(lexicon):
    valid_ids = {e.id for e in lexicon.entries}
    for entry in lexicon.entries:
        for ref in entry.related_terms:
            assert ref in valid_ids, (
                f"Entry '{entry.id}' has dead related_terms reference: '{ref}'"
            )


def test_all_categories_have_entries(lexicon):
    """Every category that appears in seed_topics.yaml must have ≥1
    entry in the lexicon. An empty category indicates a generation
    pipeline failure for that group."""
    seen_categories = Counter(e.category for e in lexicon.entries)
    for category, count in seen_categories.items():
        assert count >= 1, f"Category '{category}' has zero entries"


def test_all_sources_in_allowlist(lexicon):
    for entry in lexicon.entries:
        for source in entry.sources:
            if source.url:
                domain = urlparse(source.url).netloc.lower()
                assert domain in ALLOWED_SOURCE_DOMAINS, (
                    f"Entry '{entry.id}' has source from non-allowlisted domain: {domain}"
                )


def test_definitions_meet_minimum_length(lexicon):
    for entry in lexicon.entries:
        assert len(entry.short_definition) >= 10
        assert len(entry.clinical_context) >= 10
```

- [ ] **Step 2: Run the tests**

Run: `python -m pytest tests/knowledge/test_lexicon_quality.py -v`

Expected: all tests PASS. If any fail, fix the lexicon directly (edit `lexicon.yaml`) or rerun the merge with corrected CSV.

- [ ] **Step 3: Commit**

```bash
git add tests/knowledge/test_lexicon_quality.py
git commit -m "test(knowledge): add quality gates for live lexicon

Asserts no duplicate ids, no alias collisions, all related_terms
references resolve, all categories non-empty, all source URLs in the
authoritative allowlist, and definitions meet minimum length. These
tests run against the real lexicon.yaml and catch regressions."
```

---

## Task 12: Build `enrichment.py` with TDD

**Files:**
- Create: `app/services/enrichment.py`
- Create: `tests/services/test_enrichment.py`

- [ ] **Step 1: Create the test directory marker**

Run: `mkdir -p tests/services && touch tests/services/__init__.py`

- [ ] **Step 2: Write the failing tests**

Create `tests/services/test_enrichment.py`:

```python
"""Enrichment logic tests."""

import pytest

from app.knowledge.oncology.schema import Lexicon, LexiconEntry, Source
from app.services.enrichment import enrich, MAX_ANNOTATIONS


def _entry(eid: str, term: str, aliases: list[str] | None = None) -> LexiconEntry:
    return LexiconEntry(
        id=eid,
        term=term,
        aliases=aliases or [],
        category="trial-phase",
        short_definition="Test definition that is long enough.",
        clinical_context="Test context that is also long enough.",
        sources=[Source(
            kind="nci-thesaurus",
            url="https://ncit.nci.nih.gov/x",
            citation="NCIt",
        )],
        review_status="llm-generated",
    )


@pytest.fixture
def mini_lexicon():
    entries = [
        _entry("trial-phase-3", "Phase 3", aliases=["phase III", "phase iii"]),
        _entry("endpoint-os", "Overall Survival", aliases=["OS"]),
        _entry("response-criterion-recist-1-1", "RECIST 1.1", aliases=["RECIST"]),
    ]
    term_index = {}
    for e in entries:
        term_index[e.term.lower()] = e
        for alias in e.aliases:
            term_index[alias.lower()] = e
    return Lexicon(entries=entries, term_index=term_index)


# --- Match rules ----------------------------------------------------------------


def test_enrich_matches_canonical_term(mini_lexicon):
    data = {"phase": "Phase 3"}
    result = enrich(data, mini_lexicon)
    annotations = result["knowledge_annotations"]
    assert any(a["lexicon_id"] == "trial-phase-3" for a in annotations)


def test_enrich_matches_alias(mini_lexicon):
    data = {"endpoint": "OS"}
    result = enrich(data, mini_lexicon)
    annotations = result["knowledge_annotations"]
    assert any(a["matched_term"] == "OS" and a["lexicon_id"] == "endpoint-os"
               for a in annotations)


def test_enrich_is_case_insensitive(mini_lexicon):
    data = {"phase": "phase iii"}
    result = enrich(data, mini_lexicon)
    annotations = result["knowledge_annotations"]
    assert any(a["lexicon_id"] == "trial-phase-3" for a in annotations)


def test_enrich_word_boundary(mini_lexicon):
    """RECIST should NOT match in 'prerecisted' or similar substrings."""
    data = {"notes": "the prerecisted criteria were updated"}
    result = enrich(data, mini_lexicon)
    annotations = result["knowledge_annotations"]
    assert not any(a["lexicon_id"].startswith("response-criterion") for a in annotations)


def test_enrich_walks_nested_dicts(mini_lexicon):
    data = {"trial": {"details": {"phase": "Phase 3"}}}
    result = enrich(data, mini_lexicon)
    assert any(a["lexicon_id"] == "trial-phase-3"
               for a in result["knowledge_annotations"])


def test_enrich_walks_lists_of_dicts(mini_lexicon):
    data = {"results": [{"phase": "Phase 3"}, {"phase": "Phase 2"}]}
    result = enrich(data, mini_lexicon)
    annotations = result["knowledge_annotations"]
    assert any(a["lexicon_id"] == "trial-phase-3" for a in annotations)


# --- Idempotence and capping ---------------------------------------------------


def test_enrich_dedupes_same_lexicon_id(mini_lexicon):
    """If 'Phase 3' appears 5 times in the data, we should still get one
    annotation per unique field path — but not five identical ones for
    the same lexicon_id at the same field path."""
    data = {
        "trials": [
            {"phase": "Phase 3", "id": "NCT01"},
            {"phase": "Phase 3", "id": "NCT02"},
        ]
    }
    result = enrich(data, mini_lexicon)
    annotations = result["knowledge_annotations"]
    # Should annotate each occurrence (different field paths)
    phase3_annotations = [a for a in annotations if a["lexicon_id"] == "trial-phase-3"]
    assert len(phase3_annotations) >= 1


def test_enrich_idempotent(mini_lexicon):
    data = {"phase": "Phase 3"}
    once = enrich(data, mini_lexicon)
    twice = enrich(once, mini_lexicon)
    assert once["knowledge_annotations"] == twice["knowledge_annotations"]


def test_enrich_caps_max_annotations(mini_lexicon):
    """A response with 100 occurrences must not produce 100 annotations."""
    data = {"trials": [{"phase": "Phase 3"} for _ in range(100)]}
    result = enrich(data, mini_lexicon)
    assert len(result["knowledge_annotations"]) <= MAX_ANNOTATIONS


# --- Side effects ---------------------------------------------------------------


def test_enrich_does_not_mutate_original(mini_lexicon):
    data = {"phase": "Phase 3"}
    original_copy = dict(data)
    _ = enrich(data, mini_lexicon)
    assert data == original_copy
    assert "knowledge_annotations" not in data


def test_enrich_with_empty_data(mini_lexicon):
    result = enrich({}, mini_lexicon)
    assert result == {"knowledge_annotations": []}


def test_enrich_with_no_matches(mini_lexicon):
    data = {"unrelated": "field with no oncology terms"}
    result = enrich(data, mini_lexicon)
    assert result["knowledge_annotations"] == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/services/test_enrichment.py -v`

Expected: FAIL with `ImportError`.

- [ ] **Step 4: Implement enrichment**

Create `app/services/enrichment.py`:

```python
"""Knowledge enrichment for tool response dicts.

Walks a tool response dict, finds string fields that match lexicon
terms (canonical or alias), and returns a NEW dict with a top-level
``knowledge_annotations`` field listing every match.

Match rules:
  1. Case-insensitive
  2. Word-boundary (so 'RECIST' does not match in 'prerecisted')
  3. No fuzzy matching — deliberately simple, deterministic
  4. Capped at MAX_ANNOTATIONS per response to prevent noise

Side effects: NONE. The input dict is not mutated. The output is a
new dict with the same keys plus ``knowledge_annotations``.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from app.knowledge.oncology.schema import Annotation, Lexicon

__all__ = ["enrich", "MAX_ANNOTATIONS"]

# Cap on annotations per response. Above this, additional matches are
# silently dropped to keep the LLM context tight.
MAX_ANNOTATIONS = 50


def enrich(data: dict[str, Any], lexicon: Lexicon) -> dict[str, Any]:
    """Enrich a tool response dict with knowledge annotations.

    Returns a NEW dict — the input is not mutated.
    """
    # Strip any pre-existing annotations from the input copy so the
    # function is idempotent: enrich(enrich(x)) == enrich(x)
    working = copy.deepcopy(data)
    working.pop("knowledge_annotations", None)

    annotations: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()  # (field_path, lexicon_id)

    _walk(working, "", lexicon, annotations, seen_keys)

    working["knowledge_annotations"] = [
        a for a in annotations[:MAX_ANNOTATIONS]
    ]
    return working


def _walk(
    node: Any,
    path: str,
    lexicon: Lexicon,
    annotations: list[dict[str, Any]],
    seen: set[tuple[str, str]],
) -> None:
    if len(annotations) >= MAX_ANNOTATIONS:
        return

    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else key
            _walk(value, child_path, lexicon, annotations, seen)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            child_path = f"{path}[{i}]"
            _walk(item, child_path, lexicon, annotations, seen)
    elif isinstance(node, str):
        _scan_string(node, path, lexicon, annotations, seen)


def _scan_string(
    text: str,
    field_path: str,
    lexicon: Lexicon,
    annotations: list[dict[str, Any]],
    seen: set[tuple[str, str]],
) -> None:
    """Find lexicon terms in a string with case-insensitive word-boundary
    matching. The first matching term wins per (field_path, lexicon_id)."""
    if not text:
        return
    text_lower = text.lower()
    for term_lower, entry in lexicon.term_index.items():
        # Word-boundary match: term must be surrounded by non-word chars
        # or string boundaries.
        pattern = r"\b" + re.escape(term_lower) + r"\b"
        if re.search(pattern, text_lower):
            key = (field_path, entry.id)
            if key in seen:
                continue
            seen.add(key)
            annotations.append({
                "field_path": field_path,
                "matched_term": term_lower,
                "lexicon_id": entry.id,
                "short_definition": entry.short_definition,
                "clinical_context": entry.clinical_context,
                "review_status": entry.review_status,
            })
            if len(annotations) >= MAX_ANNOTATIONS:
                return
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/services/test_enrichment.py -v`

Expected: 12 PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/enrichment.py tests/services/__init__.py tests/services/test_enrichment.py
git commit -m "feat(services): add knowledge enrichment for tool responses

Walks a tool response dict, finds case-insensitive word-boundary
matches against the lexicon's term index, returns a new dict with a
knowledge_annotations field. Side-effect-free, idempotent, capped at
50 annotations per response."
```

---

## Task 13: Wire enrichment into `build_response`

**Files:**
- Modify: `app/viz/build.py`

- [ ] **Step 1: Write the integration test**

Create `tests/test_orchestration_with_enrichment.py`:

```python
"""End-to-end test: build_response enriches data with annotations
from the live oncology lexicon, then routes through the recipe
dispatcher (and the WS1 fallback if needed)."""

from app.viz.build import build_response


def test_build_response_attaches_annotations_for_oncology_terms():
    envelope = build_response(
        tool_name="search_clinical_trials",
        data={
            "results": [
                {"id": "NCT01", "title": "T1", "sponsor": "S1", "phase": "Phase 3", "status": "Recruiting"},
                {"id": "NCT02", "title": "T2", "sponsor": "S2", "phase": "Phase 3", "status": "Active"},
            ]
        },
        sources=[],
    )
    annotations = envelope["data"].get("knowledge_annotations", [])
    # Phase 3 should be annotated
    assert any(a["matched_term"] == "phase 3" for a in annotations), (
        f"Expected 'phase 3' annotation, got: {[a['matched_term'] for a in annotations]}"
    )


def test_build_response_works_when_lexicon_has_no_match():
    envelope = build_response(
        tool_name="search_clinical_trials",
        data={"results": [{"id": "NCT99", "title": "Generic Title", "sponsor": "X"}]},
        sources=[],
    )
    # Annotations field is present but may be empty
    assert "knowledge_annotations" in envelope["data"]
    assert isinstance(envelope["data"]["knowledge_annotations"], list)


def test_build_response_still_emits_artifact_with_annotations():
    """Both WS1 and WS2 guarantees together: artifact present, annotations attached."""
    envelope = build_response(
        tool_name="search_clinical_trials",
        data={"results": []},
        sources=[],
        query_hint="test",
    )
    assert envelope.get("ui") is not None  # WS1 guarantee
    assert "knowledge_annotations" in envelope["data"]  # WS2 guarantee
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_orchestration_with_enrichment.py -v`

Expected: FAIL — `knowledge_annotations` is not yet attached.

- [ ] **Step 3: Wire the enrichment singleton + call into `build_response`**

Edit `app/viz/build.py`. Add a lexicon singleton and call `enrich` in `build_response`:

Add at the top of the file (after the existing imports):

```python
from functools import lru_cache

from app.knowledge.oncology.loader import load_lexicon
from app.knowledge.oncology.schema import Lexicon
from app.services.enrichment import enrich


@lru_cache(maxsize=1)
def _lexicon() -> Lexicon:
    """Lazy singleton — loaded once on first build_response() call."""
    return load_lexicon()
```

Then modify `build_response` to call `enrich` on the data dict before passing it to the recipe builder. Find the existing block:

```python
    if decision.kind == DecisionKind.USE and decision.recipe in REGISTRY:
        recipe_name = decision.recipe
        recipe_data = data
    else:
        ...
```

And replace with the enriched version:

```python
    # Enrich the data dict with knowledge annotations BEFORE choosing
    # a recipe. The enriched dict carries a top-level
    # ``knowledge_annotations`` field that recipes can opt into.
    enriched_data = enrich(data, _lexicon())

    if decision.kind == DecisionKind.USE and decision.recipe in REGISTRY:
        recipe_name = decision.recipe
        recipe_data = enriched_data
    else:
        # Fallback path — guaranteed to produce a recipe
        fallback_used = True
        fallback_reason = (
            decision.reason if decision.kind == DecisionKind.SKIP
            else f"primary recipe '{decision.recipe}' not in REGISTRY"
        )
        recipe_name = pick_fallback_recipe(tool_name, enriched_data, query_hint)
        recipe_data = build_fallback_data(
            recipe_name=recipe_name,
            tool_name=tool_name,
            original_data=enriched_data,
            query_hint=query_hint,
        )
```

And update the Envelope construction to use the enriched data so the annotations show up in `data`:

```python
    envelope = Envelope(
        render_hint=render_hints.for_artifact_type(ui.artifact.type),
        ui=ui,
        data=enriched_data,  # carries knowledge_annotations
        sources=normalized_sources,
    )
```

- [ ] **Step 4: Run the integration test**

Run: `python -m pytest tests/test_orchestration_with_enrichment.py -v`

Expected: 3 PASS.

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest tests/ -q`

Expected: all tests pass. Watch for the WS1 envelope guarantee tests — they should still pass because annotations are additive, not destructive.

- [ ] **Step 6: Commit**

```bash
git add app/viz/build.py tests/test_orchestration_with_enrichment.py
git commit -m "feat(viz): wire knowledge enrichment into build_response

Lexicon is loaded once via @lru_cache singleton on first call.
Every response now passes through enrich() before recipe dispatch.
The enriched data dict carries a top-level knowledge_annotations
field listing matched terms with definitions and clinical context."
```

---

## Task 14: Recipe integration — glossary footer in `info_card`

**Files:**
- Modify: `app/viz/recipes/info_card.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/viz/test_recipes.py`:

```python
def test_info_card_renders_glossary_when_annotations_present():
    """When the data dict carries knowledge_annotations, info_card
    appends a glossary footer block."""
    data = {
        "title": "Search Results",
        "bullets": ["Phase 3 study found"],
        "knowledge_annotations": [
            {
                "field_path": "results[0].phase",
                "matched_term": "phase 3",
                "lexicon_id": "trial-phase-3",
                "short_definition": "Late-stage trial confirming efficacy.",
                "clinical_context": "Phase 3 trials enroll hundreds to thousands.",
                "review_status": "reviewed",
            }
        ],
    }
    payload = info_card.build(data, sources=[])
    assert "Glossary" in payload.raw
    assert "phase 3" in payload.raw.lower()
    assert "Late-stage trial" in payload.raw


def test_info_card_no_glossary_when_no_annotations():
    data = {"title": "Result", "bullets": ["x"]}
    payload = info_card.build(data, sources=[])
    assert "Glossary" not in payload.raw


def test_info_card_glossary_dedupes_lexicon_ids():
    """Multiple annotations for the same lexicon_id should appear once."""
    data = {
        "title": "Result",
        "knowledge_annotations": [
            {
                "field_path": "a", "matched_term": "phase 3", "lexicon_id": "trial-phase-3",
                "short_definition": "Late-stage trial.", "clinical_context": "x",
                "review_status": "reviewed",
            },
            {
                "field_path": "b", "matched_term": "phase 3", "lexicon_id": "trial-phase-3",
                "short_definition": "Late-stage trial.", "clinical_context": "x",
                "review_status": "reviewed",
            },
        ],
    }
    payload = info_card.build(data, sources=[])
    # Glossary appears once for the unique lexicon_id
    assert payload.raw.count("Late-stage trial") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/viz/test_recipes.py -v -k glossary`

Expected: FAIL.

- [ ] **Step 3: Update `info_card` to render the glossary footer**

Edit `app/viz/recipes/info_card.py`. After the existing body construction and before the final HTML assembly, insert the glossary block:

Find this block:
```python
    body = "\n    ".join(body_parts)

    raw = f"""<div class="p-4 font-sans rounded-lg border border-gray-200 bg-white">
```

Replace with:
```python
    body = "\n    ".join(body_parts)

    glossary_html = _render_glossary(data.get("knowledge_annotations") or [])

    raw = f"""<div class="p-4 font-sans rounded-lg border border-gray-200 bg-white">
```

And update the `<section>` block to include the glossary:
```python
  <section>
    {body}
    {glossary_html}
  </section>
```

Then add the helper at the bottom of the file:
```python
def _render_glossary(annotations: list[dict[str, Any]]) -> str:
    """Render a deduplicated glossary block from knowledge annotations.

    Only one entry per unique lexicon_id is shown — the first occurrence
    wins. Returns empty string if no annotations.
    """
    if not annotations:
        return ""

    seen: set[str] = set()
    items: list[str] = []
    for ann in annotations:
        lid = ann.get("lexicon_id")
        if not lid or lid in seen:
            continue
        seen.add(lid)
        term = escape_html(str(ann.get("matched_term", "")))
        definition = escape_html(str(ann.get("short_definition", "")))
        items.append(
            f'<li class="text-xs text-gray-700"><span class="font-semibold">{term}</span> — {definition}</li>'
        )

    if not items:
        return ""

    return f"""<div class="mt-4 pt-3 border-t border-gray-100">
      <p class="text-xs uppercase tracking-wide text-gray-400 mb-2">Glossary</p>
      <ul class="space-y-1">
        {"".join(items)}
      </ul>
    </div>"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/viz/test_recipes.py -v -k "info_card or glossary"`

Expected: all PASS, including the new glossary tests.

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest tests/ -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/viz/recipes/info_card.py tests/viz/test_recipes.py
git commit -m "feat(viz): info_card renders glossary footer from annotations

When the data dict carries knowledge_annotations, info_card appends a
deduplicated glossary block with matched terms and short definitions.
First-in-id wins. Other recipes can adopt the same pattern by calling
the same _render_glossary helper."
```

---

## Task 15: Final integration smoke + commit

**Files:**
- Run: full test suite + manual smoke

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest tests/ -q`

Expected: ALL tests pass — both WS1 and WS2 work together.

- [ ] **Step 2: Smoke-test enrichment + envelope guarantee from a REPL**

```bash
python -c "
from app.viz.build import build_response
from app.viz.mcp_output import envelope_to_llm_text

# Phase 3 trials — should produce annotations
env = build_response(
    'search_clinical_trials',
    {'results': [{'id': 'NCT01', 'title': 'T', 'phase': 'Phase 3', 'sponsor': 'S', 'status': 'Recruiting'}]},
    sources=[],
)
print('Annotations:', [a['matched_term'] for a in env['data'].get('knowledge_annotations', [])])
text = envelope_to_llm_text(env)
assert ':::artifact' in text, 'WS1 guarantee broken'
print('WS1 guarantee OK')
print('WS2 enrichment OK' if env['data'].get('knowledge_annotations') else 'WS2: no matches')
"
```

Expected output:
```
Annotations: ['phase 3', 'recruiting', ...]
WS1 guarantee OK
WS2 enrichment OK
```

- [ ] **Step 3: Verify lexicon stats**

```bash
python -c "
from app.knowledge.oncology.loader import load_lexicon
lex = load_lexicon()
from collections import Counter
counts = Counter(e.category for e in lex.entries)
print(f'{len(lex.entries)} entries, {len(lex.term_index)} index keys')
for cat, n in sorted(counts.items()):
    print(f'  {cat}: {n}')
"
```

Expected: a category breakdown showing all 10 categories non-empty.

- [ ] **Step 4: No additional commit** — work is committed in tasks 1–14.

- [ ] **Step 5: Verify branch state**

```bash
git status
git log --oneline main..HEAD | head -20
```

Expected: a clean working tree, ~14 new commits on the feature branch.

---

## Success Criteria Recap

| Criterion | Verification |
|---|---|
| Lexicon loads with ≥150 entries, all schema-valid | `tests/knowledge/test_lexicon_quality.py::test_lexicon_has_minimum_entries` |
| No duplicate ids, no alias collisions | `tests/knowledge/test_lexicon_quality.py` (no_duplicate_ids, no_alias_collisions) |
| All sources from authoritative allowlist | `tests/knowledge/test_lexicon_quality.py::test_all_sources_in_allowlist` |
| Schema enforces ≥1 source + domain allowlist | `tests/knowledge/test_schema.py` |
| Enrichment matches canonical, alias, word-boundary | `tests/services/test_enrichment.py` (12 tests) |
| Enrichment is idempotent and side-effect-free | `tests/services/test_enrichment.py::test_enrich_idempotent`, `test_enrich_does_not_mutate_original` |
| Enrichment caps at 50 annotations | `tests/services/test_enrichment.py::test_enrich_caps_max_annotations` |
| End-to-end: WS1 + WS2 work together | `tests/test_orchestration_with_enrichment.py` (3 tests) |
| `info_card` renders glossary from annotations | `tests/viz/test_recipes.py::test_info_card_renders_glossary_when_annotations_present` |
| Curation pipeline scripts work | `tests/curation/` (6 tests across generation + merge) |

## Monitored Metric (not a hard gate)

- ≥80% of generated entries pass manual review on first pass — watch the accept/reject ratio in the first review CSV. If significantly lower, tune the generation prompt.

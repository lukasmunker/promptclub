# Oncology Lexicon Curation Pipeline

Offline workflow for generating and reviewing oncology lexicon entries.

## Workflow

1. **Edit `app/knowledge/oncology/seed_topics.yaml`** to add the terms you want generated.

2. **Generate entries via parallel Claude Code subagents.**

   From an interactive Claude Code session, dispatch one subagent per category. Each subagent receives:

   - The strict system prompt below (authoritative sources, no speculation, no forward-looking statements, JSON-only output)
   - The list of terms for its category
   - The `LexiconEntry` schema definition
   - An instruction to write a JSON array to `scripts/curation/output/agent_<category>.json`

   The subagents work in parallel — categories are independent. Each returns a JSON array of `LexiconEntry` dicts (terms the agent cannot cite authoritatively are omitted).

   **Note:** Earlier iterations of this workflow used an external `anthropic` SDK call with a hardcoded `claude-opus-4-6` model. That is unnecessary when working from inside a Claude Code session — the ambient agent IS Claude, and parallel subagent dispatch is faster, free, and does not require an API key.

3. **Aggregate via the library.**

   ```bash
   /Users/joschahaertel/Projects/promptclub/.venv/bin/python \
       scripts/curation/generate_lexicon.py
   ```

   This reads every `agent_<category>.json` in `scripts/curation/output/`, validates each entry against the Pydantic schema, and writes:

   - `scripts/curation/output/draft_<date>.yaml` — entries that passed schema validation
   - `scripts/curation/output/review_worksheet_<date>.csv` — the review sheet

   Entries that fail schema validation (fabricated URLs, missing sources, wrong category names) are dropped with a per-entry error logged to stderr.

4. **Review the CSV.** Open `review_worksheet_<date>.csv` in your editor of choice.

   For each category:
   - Sort by `category` and review one category per session
   - Spot-check 3–5 random entries against the cited source URL
   - Mark `accept=1`, `edit=<corrected text>`, or `reject=1`
   - On a clean spot-check, bulk-accept the rest
   - Use `reviewer_notes` to record why an entry was rejected or edited

   Realistic time: 3–6 hours for ~150–200 entries.

5. **Merge reviewed entries:**

   ```bash
   /Users/joschahaertel/Projects/promptclub/.venv/bin/python \
       scripts/curation/review_worksheet_to_yaml.py \
       scripts/curation/output/review_worksheet_<date>.csv
   ```

   Validates, merges, and writes `app/knowledge/oncology/lexicon.yaml`.

6. **Commit the updated lexicon:**

   ```bash
   git add app/knowledge/oncology/lexicon.yaml
   git diff --cached app/knowledge/oncology/lexicon.yaml | less  # final eyeball
   git commit -m "data(lexicon): add <N> reviewed oncology entries"
   ```

## Quality gates

The `LexiconEntry` schema (`app/knowledge/oncology/schema.py`) enforces:

- Every entry has **≥1 source** (Pydantic `model_validator`)
- Every source URL comes from an **authoritative domain allowlist**:
  - `ncit.nci.nih.gov`
  - `fda.gov` / `www.fda.gov`
  - `ema.europa.eu` / `www.ema.europa.eu`
  - `recist.eortc.org`
  - `pubmed.ncbi.nlm.nih.gov`
  - `ctep.cancer.gov`
- Categories are bounded by a Pydantic `Literal` — no category sprawl
- Three-stage review lifecycle: `llm-generated` → `reviewed` → `expert-approved`

If a generated entry fails validation, it is dropped by `generate_lexicon.py` and logged to stderr. The review CSV only contains entries that passed schema validation.

## System prompt (for subagent dispatch)

Use this prompt verbatim when dispatching a category subagent. Replace `<category>` and `<terms>` with the actual values.

```
You are a clinical oncology terminology curator. Your job is to draft one LexiconEntry for each term I give you, writing the final JSON array to scripts/curation/output/agent_<category>.json.

HARD REQUIREMENTS:

1. Every entry MUST cite at least one source. Source URLs must come from one of these authoritative domains:
   - ncit.nci.nih.gov
   - fda.gov / www.fda.gov
   - ema.europa.eu / www.ema.europa.eu
   - recist.eortc.org
   - pubmed.ncbi.nlm.nih.gov
   - ctep.cancer.gov

2. If you cannot cite a real, authoritative source for an entry, OMIT it from the output array. Do not fabricate URLs. Do not include placeholder URLs.

3. short_definition must be 1-2 sentences, plain language, quotable from the source.

4. clinical_context must be 2-4 sentences, grounded in the source, no speculation. If you are uncertain about something, leave it out rather than guess.

5. Do NOT include forward-looking statements ("expected to..." / "may improve...").

SCHEMA (each entry in the array must match this shape exactly):

{
  "id": "kebab-case-slug",
  "term": "Canonical Term",
  "aliases": ["alias1", "alias2"],
  "category": "<category>",
  "short_definition": "1-2 sentences",
  "clinical_context": "2-4 sentences",
  "typical_values": null,
  "related_terms": [],
  "sources": [
    {"kind": "nci-thesaurus", "url": "https://ncit.nci.nih.gov/...", "citation": "NCI Thesaurus, Concept X"}
  ],
  "review_status": "llm-generated",
  "last_reviewed": null
}

Valid "kind" values: "nci-thesaurus", "fda-label", "publication", "guideline", "definition"

TERMS TO DRAFT:
<terms>

Write the JSON array (entries only, no prose) to scripts/curation/output/agent_<category>.json. Return a short status report: how many entries were written, how many terms were skipped, and any notes.
```

## When to re-generate

- Adding new terms: add to `seed_topics.yaml`, re-dispatch the affected category's subagent for just the new terms
- Updating existing terms: edit `lexicon.yaml` directly, set `last_reviewed`
- Stale review (planned for v2): re-review oldest `last_reviewed` entries

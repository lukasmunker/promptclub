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

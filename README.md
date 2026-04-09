# Clinical Intelligence MCP Server - MVP 1

## What this MVP includes

- ClinicalTrials.gov v2 search
- PubMed search via NCBI E-utilities
- Open Targets target lookup
- openFDA regulatory context
- Optional Vertex AI Google Search grounding
- Optional GPT-5.4 orchestration via the OpenAI Responses API
- FastMCP over Streamable HTTP for LibreChat

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Health checks
```
curl http://localhost:8000/health
curl http://localhost:8000/health/sources
```
## MCP endpoint
```http://localhost:8000/mcp
```

## Useful test URLs
```
curl "http://localhost:8000/health/sources"
```

## Pytest
```
pytest -q
```

## Vertex AI Google Search grounding

This is optional.

Set:

GOOGLE_CLOUD_PROJECT
GOOGLE_CLOUD_LOCATION=global
ENABLE_VERTEX_WEB_SEARCH=true

Also ensure your environment has Google Cloud credentials available.

If this is disabled, the rest of the server still works.

## Search latency

The `search_trials` tool does ClinicalTrials.gov search first, then enriches a limited number of
trial records with linked PubMed publications. To keep MCP responses fast enough for chat clients,
publication enrichment is done in parallel and each per-trial PubMed lookup is time-bounded.

Optional:

ANSWER_CLINICAL_QUESTION_TIMEOUT_SECONDS=28
SEARCH_TRIALS_TOTAL_TIMEOUT_SECONDS=24
MAX_TRIALS_TO_ENRICH_WITH_PUBLICATIONS=5
PER_TRIAL_PUBLICATION_LOOKUP_TIMEOUT_SECONDS=8

## GPT-5.4 tool orchestration

This is optional and fail-open.

If configured, the MCP tool `answer_clinical_question` uses GPT-5.4 to decide which of the
existing clinical tools to call internally. If OpenAI is not configured, or the orchestration
request fails, the server falls back to deterministic routing and the existing tool surface
continues to work.

Set:

OPENAI_API_KEY
ENABLE_LLM_TOOL_ORCHESTRATION=true
OPENAI_ORCHESTRATOR_MODEL=gpt-5.4

Optional:

OPENAI_BASE_URL
OPENAI_ORCHESTRATOR_REASONING_EFFORT=medium
OPENAI_ORCHESTRATOR_MAX_STEPS=6
OPENAI_ORCHESTRATOR_MAX_OUTPUT_TOKENS=1800
OPENAI_ORCHESTRATOR_TIMEOUT_SECONDS=60
ANSWER_CLINICAL_QUESTION_TIMEOUT_SECONDS=28

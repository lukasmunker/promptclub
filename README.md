# Clinical Intelligence MCP Server - MVP 1

## What this MVP includes

- ClinicalTrials.gov v2 search
- PubMed search via NCBI E-utilities
- Open Targets target lookup
- openFDA regulatory context
- Optional Vertex AI Google Search grounding
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
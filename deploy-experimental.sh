#!/usr/bin/env bash
# deploy-experimental.sh — deploy the Pfad B (LLM-as-designer) experimental
# Cloud Run service.
#
# This deploys to a SEPARATE service (mcp-yallah-experimental) so the live
# Pfad A service (mcp-yallah) keeps serving the BioNTech demo while we
# evaluate Pfad B in parallel. Both services share the same Cloud Run project
# and region, but get distinct URLs and Traffic.
#
# Pfad B sets VIZ_DESIGNER_MODE=true which makes app/viz/build.py skip the
# Python recipe pipeline entirely. The LLM constructs every visualization
# itself from the BIONTECH BRAND TOKENS + SHADCN/RECHARTS/MERMAID catalogs
# embedded in app/main.py's system prompt.
#
# Usage:
#   ./deploy-experimental.sh                     # deploys to default project + region
#   PROJECT=my-proj ./deploy-experimental.sh     # override project
#   REGION=us-central1 ./deploy-experimental.sh  # override region

set -euo pipefail

# --- Defaults ---------------------------------------------------------------

PROJECT="${PROJECT:-ai-hack26ham-402}"
REGION="${REGION:-europe-west1}"
SERVICE="${SERVICE:-mcp-yallah-experimental}"

echo "==> Deploying ${SERVICE} (Pfad B — LLM-as-designer)"
echo "    project: ${PROJECT}"
echo "    region : ${REGION}"
echo "    branch : $(git rev-parse --abbrev-ref HEAD) @ $(git rev-parse --short HEAD)"
echo

# --- Make sure gcloud points at the right project --------------------------

gcloud config set project "${PROJECT}" >/dev/null

# --- Deploy (builds image via Cloud Build + pushes + rolls out) ------------
#
# Note the extra VIZ_DESIGNER_MODE=true env var compared to deploy.sh.

gcloud run deploy "${SERVICE}" \
  --source=. \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --port=8080 \
  --memory=1Gi \
  --cpu=1 \
  --timeout=300 \
  --max-instances=5 \
  --concurrency=40 \
  --set-env-vars="APP_ENV=prod,USER_AGENT=mcp-yallah-experimental/0.4.0,GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_VERTEXAI=true,VERTEX_GEMINI_MODEL=gemini-2.5-flash,ENABLE_VERTEX_WEB_SEARCH=true,VIZ_DESIGNER_MODE=true"

# --- Report the URL --------------------------------------------------------

URL="$(gcloud run services describe "${SERVICE}" --region="${REGION}" --format='value(status.url)')"

echo
echo "==> Deployed successfully (Pfad B experimental)"
echo "    service URL : ${URL}"
echo "    health       : ${URL}/health"
echo "    MCP endpoint : ${URL}/mcp"
echo
echo "==> LibreChat mcpServers snippet — add ALONGSIDE your existing mcp-yallah entry:"
cat <<EOF

  mcpServers:
    clinical-intel-experimental:
      type: streamable-http
      url: ${URL}/mcp
      timeout: 30000
      initTimeout: 15000
      serverInstructions: true
EOF

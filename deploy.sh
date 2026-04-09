#!/usr/bin/env bash
# deploy.sh — deploy the pharmafuse-mcp Cloud Run service.
#
# One-command convenience wrapper around `gcloud run deploy --source=.`.
# Uses the Dockerfile in the repo root; no manual image-push step needed.
#
# Usage:
#   ./deploy.sh                     # deploys to default project + region
#   PROJECT=my-proj ./deploy.sh     # override project
#   REGION=us-central1 ./deploy.sh  # override region
#
# After a successful deploy the script prints the service URL and the
# full MCP endpoint (URL + "/mcp").
#
# Note: the service was previously called "mcp-yallah" — the first deploy
# after this rename creates a NEW Cloud Run service at a NEW URL. The old
# service is not removed automatically; delete it manually from the Cloud
# Run console once LibreChat is pointing at the new URL.

set -euo pipefail

# --- Defaults ---------------------------------------------------------------

PROJECT="${PROJECT:-ai-hack26ham-402}"
REGION="${REGION:-europe-west1}"
SERVICE="${SERVICE:-pharmafuse-mcp}"

echo "==> Deploying ${SERVICE}"
echo "    project: ${PROJECT}"
echo "    region : ${REGION}"
echo

# --- Make sure gcloud points at the right project --------------------------

gcloud config set project "${PROJECT}" >/dev/null

# --- Deploy (builds image via Cloud Build + pushes + rolls out) ------------

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
  --set-env-vars="APP_ENV=prod,USER_AGENT=pharmafuse-mcp/0.3.0,GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_VERTEXAI=true,VERTEX_GEMINI_MODEL=gemini-2.5-flash,ENABLE_VERTEX_WEB_SEARCH=true"

# --- Report the URL --------------------------------------------------------

URL="$(gcloud run services describe "${SERVICE}" --region="${REGION}" --format='value(status.url)')"

echo
echo "==> Deployed successfully"
echo "    service URL : ${URL}"
echo "    health       : ${URL}/health"
echo "    MCP endpoint : ${URL}/mcp"
echo
echo "==> LibreChat mcpServers snippet:"
cat <<EOF

  mcpServers:
    clinical-intel:
      type: streamable-http
      url: ${URL}/mcp
      timeout: 30000
      initTimeout: 15000
      serverInstructions: true
EOF

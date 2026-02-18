#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-asia-south1}"
SERVICE_NAME="${SERVICE_NAME:-hiring-agent-api}"
AUTH_MODE="${AUTH_MODE:-enabled}"
RELEASE_TOKEN="${RELEASE_TOKEN:-}"

python -m ruff check .
python -m pytest -q

PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" bash infra/gcp/cloudrun/deploy.sh

SERVICE_URL="$(
  gcloud run services describe "${SERVICE_NAME}" \
    --region "${REGION}" \
    --project "${PROJECT_ID}" \
    --format="value(status.url)"
)"

if [[ -z "${SERVICE_URL}" ]]; then
  echo "Failed to resolve Cloud Run service URL." >&2
  exit 1
fi

if [[ -n "${RELEASE_TOKEN}" ]]; then
  python scripts/smoke_test.py --base-url "${SERVICE_URL}" --auth-mode "${AUTH_MODE}" --token "${RELEASE_TOKEN}"
else
  python scripts/smoke_test.py --base-url "${SERVICE_URL}" --auth-mode "${AUTH_MODE}"
fi

echo "Release complete: ${SERVICE_URL}"


#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-asia-south1}"
REPO="${REPO:-hiring-agent}"
IMAGE="hiring-agent-api"
TAG="${TAG:-$(date +%Y%m%d%H%M%S)}"

gcloud config set project "${PROJECT_ID}"

gcloud artifacts repositories describe "${REPO}" --location "${REGION}" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "${REPO}" --repository-format=docker --location="${REGION}"

FULL_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE}:${TAG}"

gcloud builds submit --tag "${FULL_IMAGE}" .

sed \
  -e "s|REGION|${REGION}|g" \
  -e "s|PROJECT_ID|${PROJECT_ID}|g" \
  -e "s|:latest|:${TAG}|g" \
  infra/gcp/cloudrun/service.yaml | gcloud run services replace -

echo "Deployed ${FULL_IMAGE}"


#!/usr/bin/env bash
# Deploy Wenjin from prebuilt DockerHub images.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ENV_FILE:-${PROJECT_ROOT}/.env}"

cd "${PROJECT_ROOT}"

if [ ! -f "${ENV_FILE}" ]; then
  echo "[prebuilt-deploy] missing env file: ${ENV_FILE}" >&2
  echo "[prebuilt-deploy] copy .env.prebuilt.example to .env and fill passwords first" >&2
  exit 1
fi

echo "[prebuilt-deploy] using env file: ${ENV_FILE}"

docker compose \
  --env-file "${ENV_FILE}" \
  -f docker-compose.yml \
  -f docker-compose.prebuilt.yml \
  pull

docker compose \
  --env-file "${ENV_FILE}" \
  -f docker-compose.yml \
  -f docker-compose.prebuilt.yml \
  up -d --remove-orphans

docker compose \
  --env-file "${ENV_FILE}" \
  -f docker-compose.yml \
  -f docker-compose.prebuilt.yml \
  ps

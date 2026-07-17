#!/usr/bin/env bash
# Build Wenjin deployable images and push them to DockerHub.
#
# Usage:
#   scripts/docker-build-push-images.sh [dockerhub-namespace] [tag]
#
# Examples:
#   scripts/docker-build-push-images.sh junze0514 latest
#   WENJIN_IMAGE_TAG=$(git rev-parse --short HEAD) scripts/docker-build-push-images.sh junze0514

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

NAMESPACE="${1:-${DOCKERHUB_NAMESPACE:-junze0514}}"
TAG="${2:-${WENJIN_IMAGE_TAG:-$(git -C "${PROJECT_ROOT}" rev-parse --short HEAD)}}"
PUSH_LATEST="${PUSH_LATEST:-1}"
ENV_FILE="${ENV_FILE:-${PROJECT_ROOT}/.env}"

if [ -f "${ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

PYTHON_IMAGE="${PYTHON_IMAGE:-docker.m.daocloud.io/library/python:3.13-slim}"
NODE_IMAGE="${NODE_IMAGE:-docker.m.daocloud.io/library/node:24-alpine}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
APT_MIRROR="${APT_MIRROR:-https://mirrors.tuna.tsinghua.edu.cn/debian}"
APT_SECURITY_MIRROR="${APT_SECURITY_MIRROR:-https://mirrors.tuna.tsinghua.edu.cn/debian-security}"
NPM_REGISTRY="${NPM_REGISTRY:-https://registry.npmmirror.com}"
NPM_FALLBACK_REGISTRY="${NPM_FALLBACK_REGISTRY:-https://registry.npmjs.org}"
ALPINE_MIRROR="${ALPINE_MIRROR:-https://mirrors.tuna.tsinghua.edu.cn/alpine}"
PLATFORM_ARGS=()
if [ -n "${PLATFORM:-}" ]; then
  PLATFORM_ARGS=(--platform "${PLATFORM}")
fi

build_backend() {
  local target="$1"
  local image="$2"

  docker build "${PLATFORM_ARGS[@]}" \
    --target "${target}" \
    --build-arg "PYTHON_IMAGE=${PYTHON_IMAGE}" \
    --build-arg "PIP_INDEX_URL=${PIP_INDEX_URL}" \
    --build-arg "APT_MIRROR=${APT_MIRROR}" \
    --build-arg "APT_SECURITY_MIRROR=${APT_SECURITY_MIRROR}" \
    -f "${PROJECT_ROOT}/backend/Dockerfile" \
    -t "${image}" \
    "${PROJECT_ROOT}/backend"
}

push_with_latest() {
  local image="$1"
  local repo="$2"

  docker push "${image}"

  if [ "${PUSH_LATEST}" = "1" ] && [ "${TAG}" != "latest" ]; then
    docker tag "${image}" "${repo}:latest"
    docker push "${repo}:latest"
  fi
}

BACKEND_REPO="${NAMESPACE}/wenjin-backend"
FRONTEND_REPO="${NAMESPACE}/wenjin-frontend"

BACKEND_IMAGE="${BACKEND_REPO}:${TAG}"
FRONTEND_IMAGE="${FRONTEND_REPO}:${TAG}"

echo "[docker-push] namespace=${NAMESPACE} tag=${TAG}"
echo "[docker-push] backend base=${PYTHON_IMAGE}"
echo "[docker-push] frontend base=${NODE_IMAGE}"

build_backend "gateway" "${BACKEND_IMAGE}"
push_with_latest "${BACKEND_IMAGE}" "${BACKEND_REPO}"

docker build "${PLATFORM_ARGS[@]}" \
  --build-arg "NODE_IMAGE=${NODE_IMAGE}" \
  --build-arg "ALPINE_MIRROR=${ALPINE_MIRROR}" \
  --build-arg "NPM_REGISTRY=${NPM_REGISTRY}" \
  --build-arg "NPM_FALLBACK_REGISTRY=${NPM_FALLBACK_REGISTRY}" \
  -f "${PROJECT_ROOT}/frontend/Dockerfile" \
  -t "${FRONTEND_IMAGE}" \
  "${PROJECT_ROOT}/frontend"
push_with_latest "${FRONTEND_IMAGE}" "${FRONTEND_REPO}"

cat <<EOF
[docker-push] done

Use these values with docker-compose.yml:
BACKEND_GATEWAY_IMAGE=${BACKEND_REPO}:${TAG}
FRONTEND_IMAGE=${FRONTEND_REPO}:${TAG}
EOF

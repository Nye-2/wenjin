#!/usr/bin/env bash
# Push Wenjin TeXLive image to Docker Hub
# Usage: ./scripts/push-texlive.sh [docker-hub-username]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

USERNAME="${1:-}"

if [ -z "${USERNAME}" ]; then
    echo "❌ 请提供 Docker Hub 用户名"
    echo "用法: $0 <docker-hub-username>"
    echo "示例: $0 junzecai"
    exit 1
fi

SOURCE_IMAGE="wenjin/texlive:2024"
TARGET_IMAGE="${USERNAME}/wenjin-texlive:2024"
TEXLIVE_BASE_IMAGE="${TEXLIVE_BASE_IMAGE:-docker.m.daocloud.io/library/ubuntu:22.04}"
TEXLIVE_APT_MIRROR="${TEXLIVE_APT_MIRROR:-}"

echo "🔍 检查本地镜像 ${SOURCE_IMAGE}..."
if ! docker images --format '{{.Repository}}:{{.Tag}}' | grep -q "^${SOURCE_IMAGE}$"; then
    echo "⚠️  本地镜像不存在，开始构建..."
    docker build \
        --build-arg "BASE_IMAGE=${TEXLIVE_BASE_IMAGE}" \
        --build-arg "APT_MIRROR=${TEXLIVE_APT_MIRROR}" \
        -t "${SOURCE_IMAGE}" \
        "${PROJECT_ROOT}/backend/docker/images/texlive"
fi

echo "🏷️  打标签: ${SOURCE_IMAGE} -> ${TARGET_IMAGE}"
docker tag "${SOURCE_IMAGE}" "${TARGET_IMAGE}"

echo "🚀 推送到 Docker Hub..."
docker push "${TARGET_IMAGE}"

echo "✅ 推送完成: ${TARGET_IMAGE}"
echo ""
echo "📋 团队成员使用时，在 .env 中设置:"
echo "   TEXLIVE_IMAGE_NAME=${TARGET_IMAGE}"
echo ""
echo "🚀 然后直接启动:"
echo "   docker compose up -d"

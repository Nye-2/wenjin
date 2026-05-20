#!/usr/bin/env bash
# Auto-retry docker compose build until success

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$PROJECT_ROOT"

MAX_RETRIES=10
RETRY=0
COMPOSE_ENV_FILE="${COMPOSE_ENV_FILE:-.env}"

while [ $RETRY -lt $MAX_RETRIES ]; do
    RETRY=$((RETRY + 1))
    echo ""
    echo "=========================================="
    echo "🔄 第 $RETRY 次尝试构建..."
    echo "=========================================="
    
    if docker compose --env-file "${COMPOSE_ENV_FILE}" up -d --build; then
        echo ""
        echo "✅ 构建成功！"
        exit 0
    fi
    
    echo ""
    echo "⚠️ 构建失败，5秒后自动重试..."
    sleep 5
done

echo ""
echo "❌ 已达到最大重试次数 ($MAX_RETRIES)，构建失败。"
echo "建议检查网络连接或配置代理/VPN。"
exit 1

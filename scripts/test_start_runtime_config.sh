#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

START_SH_NO_MAIN=1 source "$ROOT_DIR/start.sh"

BACKEND_ENV_FILE="$TMP_DIR/backend.env"
ROOT_ENV_FILE="$TMP_DIR/root.env"

cat > "$BACKEND_ENV_FILE" <<'ENV'
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/wenjin
REDIS_URL=redis://localhost:6379/0
MODEL_SECRET_KEY=base64:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=
ENV

load_runtime_config

if [ "$RUNTIME_MODEL_SECRET_KEY" != "base64:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=" ]; then
    echo "RUNTIME_MODEL_SECRET_KEY was not loaded from backend env" >&2
    exit 1
fi

if [ -n "$RUNTIME_MODEL_SECRET_KEY_FILE" ]; then
    echo "RUNTIME_MODEL_SECRET_KEY_FILE should be empty when inline key is configured" >&2
    exit 1
fi

echo "start runtime config test passed"

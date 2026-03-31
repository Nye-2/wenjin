#!/usr/bin/env bash

# Ensure LaTeX runtime image exists locally for execution service.
# Priority:
# 1) Existing local image
# 2) Load from local tar archive
# 3) Build from bundled Dockerfile
# 4) Pull from registry as last resort

set -euo pipefail

IMAGE_NAME="${TEXLIVE_IMAGE_NAME:-wenjin/texlive:2024}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

IMAGE_TAR_PATH="${TEXLIVE_IMAGE_TAR:-$PROJECT_ROOT/backend/docker/images/texlive/wenjin-texlive-2024.tar}"
IMAGE_DOCKERFILE="${TEXLIVE_IMAGE_DOCKERFILE:-$PROJECT_ROOT/backend/docker/images/texlive/Dockerfile}"
IMAGE_BUILD_CONTEXT="${TEXLIVE_IMAGE_CONTEXT:-$PROJECT_ROOT/backend/docker/images/texlive}"

log_info() { echo "[texlive-image] $1"; }
log_warn() { echo "[texlive-image][WARN] $1"; }
log_error() { echo "[texlive-image][ERROR] $1" >&2; }

image_exists() {
    docker image inspect "$IMAGE_NAME" >/dev/null 2>&1
}

if ! command -v docker >/dev/null 2>&1; then
    log_error "docker not found in PATH"
    exit 1
fi

if image_exists; then
    log_info "Image already exists: $IMAGE_NAME"
    exit 0
fi

if [ -f "$IMAGE_TAR_PATH" ]; then
    log_info "Loading image from tar: $IMAGE_TAR_PATH"
    docker load -i "$IMAGE_TAR_PATH" >/dev/null
    if image_exists; then
        log_info "Loaded image successfully: $IMAGE_NAME"
        exit 0
    fi
    log_warn "Tar load completed but image tag not found: $IMAGE_NAME"
fi

if [ -f "$IMAGE_DOCKERFILE" ]; then
    log_info "Building image locally from Dockerfile: $IMAGE_DOCKERFILE"
    docker build -t "$IMAGE_NAME" -f "$IMAGE_DOCKERFILE" "$IMAGE_BUILD_CONTEXT"
    if image_exists; then
        log_info "Built image successfully: $IMAGE_NAME"
        exit 0
    fi
    log_warn "Build completed but image tag not found: $IMAGE_NAME"
fi

log_warn "Falling back to registry pull: $IMAGE_NAME"
docker pull "$IMAGE_NAME"

if image_exists; then
    log_info "Pulled image successfully: $IMAGE_NAME"
    exit 0
fi

log_error "Failed to prepare image: $IMAGE_NAME"
exit 1

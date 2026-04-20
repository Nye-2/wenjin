#!/usr/bin/env bash

# Build and package TeXLive runtime image for Wenjin LaTeX compilation.
# Outputs an offline-loadable tar archive used by DockerClient fallback.

set -euo pipefail

IMAGE_NAME="${TEXLIVE_IMAGE_NAME:-${GUANLAN_TEXLIVE_IMAGE:-wenjin/texlive:2024}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
IMAGE_DOCKERFILE="${TEXLIVE_IMAGE_DOCKERFILE:-$PROJECT_ROOT/backend/docker/images/texlive/Dockerfile}"
IMAGE_BUILD_CONTEXT="${TEXLIVE_IMAGE_CONTEXT:-$PROJECT_ROOT/backend/docker/images/texlive}"
IMAGE_TAR_PATH="${TEXLIVE_IMAGE_TAR:-${GUANLAN_TEXLIVE_IMAGE_TAR:-$PROJECT_ROOT/backend/docker/images/texlive/wenjin-texlive-2024.tar}}"
IMAGE_BASE="${TEXLIVE_BASE_IMAGE:-ubuntu:22.04}"
APT_MIRROR="${TEXLIVE_APT_MIRROR:-}"

log_info() { echo "[package-texlive] $1"; }
log_error() { echo "[package-texlive][ERROR] $1" >&2; }

if ! command -v docker >/dev/null 2>&1; then
    log_error "docker not found in PATH"
    exit 1
fi

if [ ! -f "$IMAGE_DOCKERFILE" ]; then
    log_error "Dockerfile not found: $IMAGE_DOCKERFILE"
    exit 1
fi

log_info "Building image: $IMAGE_NAME"
log_info "Using base image: $IMAGE_BASE"
docker build \
    --build-arg "BASE_IMAGE=$IMAGE_BASE" \
    --build-arg "APT_MIRROR=$APT_MIRROR" \
    -t "$IMAGE_NAME" \
    -f "$IMAGE_DOCKERFILE" \
    "$IMAGE_BUILD_CONTEXT"

log_info "Verifying TeX toolchain and key packages inside image"
docker run --rm --entrypoint sh "$IMAGE_NAME" -lc "xelatex --version >/dev/null"
docker run --rm --entrypoint sh "$IMAGE_NAME" -lc "pdflatex --version >/dev/null"
docker run --rm --entrypoint sh "$IMAGE_NAME" -lc "biber --version >/dev/null"
docker run --rm --entrypoint sh "$IMAGE_NAME" -lc "kpsewhich listings.sty >/dev/null"
docker run --rm --entrypoint sh "$IMAGE_NAME" -lc "kpsewhich ctexart.cls >/dev/null"

mkdir -p "$(dirname "$IMAGE_TAR_PATH")"
log_info "Saving image tar: $IMAGE_TAR_PATH"
docker save "$IMAGE_NAME" -o "$IMAGE_TAR_PATH"

log_info "Done. You can point runtime to this tar via:"
log_info "  export GUANLAN_TEXLIVE_IMAGE_TAR=$IMAGE_TAR_PATH"
log_info "Script also accepts: export TEXLIVE_IMAGE_TAR=$IMAGE_TAR_PATH"
log_info "Optional speed-up env:"
log_info "  export TEXLIVE_BASE_IMAGE=ubuntu:22.04"
log_info "  export TEXLIVE_APT_MIRROR=https://mirrors.ustc.edu.cn/ubuntu/"

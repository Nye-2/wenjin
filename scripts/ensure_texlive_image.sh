#!/usr/bin/env bash

# Ensure LaTeX runtime image exists locally for execution service.
# Priority:
# 1) Existing local image
# 2) Load from local tar archive
# 3) Build from bundled Dockerfile
# 4) Pull from registry as last resort

set -euo pipefail

IMAGE_NAME="${TEXLIVE_IMAGE_NAME:-${GUANLAN_TEXLIVE_IMAGE:-wenjin/texlive:2024}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

IMAGE_TAR_PATH="${TEXLIVE_IMAGE_TAR:-${GUANLAN_TEXLIVE_IMAGE_TAR:-$PROJECT_ROOT/backend/docker/images/texlive/wenjin-texlive-2024.tar}}"
IMAGE_DOCKERFILE="${TEXLIVE_IMAGE_DOCKERFILE:-$PROJECT_ROOT/backend/docker/images/texlive/Dockerfile}"
IMAGE_BUILD_CONTEXT="${TEXLIVE_IMAGE_CONTEXT:-$PROJECT_ROOT/backend/docker/images/texlive}"
IMAGE_BASE="${TEXLIVE_BASE_IMAGE:-ubuntu:22.04}"
APT_MIRROR="${TEXLIVE_APT_MIRROR:-}"
EXPORT_TAR_ON_SUCCESS="${TEXLIVE_EXPORT_TAR_ON_SUCCESS:-1}"
REQUIRED_TEX_FILES="${TEXLIVE_REQUIRED_TEX_FILES:-listings.sty,ctexart.cls}"

log_info() { echo "[texlive-image] $1"; }
log_warn() { echo "[texlive-image][WARN] $1"; }
log_error() { echo "[texlive-image][ERROR] $1" >&2; }

image_exists() {
    docker image inspect "$IMAGE_NAME" >/dev/null 2>&1
}

verify_image_runtime() {
    local file_list="$REQUIRED_TEX_FILES"
    local old_ifs="$IFS"
    IFS=','
    read -ra files <<< "$file_list"
    IFS="$old_ifs"

    if ! docker run --rm --entrypoint sh "$IMAGE_NAME" -lc "command -v xelatex >/dev/null && command -v pdflatex >/dev/null && command -v biber >/dev/null"; then
        return 1
    fi

    local tex_file
    for tex_file in "${files[@]}"; do
        tex_file="$(echo "$tex_file" | xargs)"
        if [ -z "$tex_file" ]; then
            continue
        fi
        if ! docker run --rm --entrypoint sh "$IMAGE_NAME" -lc "kpsewhich '$tex_file' >/dev/null"; then
            log_warn "Required TeX file missing in image: $tex_file"
            return 1
        fi
    done
    return 0
}

export_image_tar() {
    if [ "$EXPORT_TAR_ON_SUCCESS" != "1" ]; then
        return 0
    fi
    mkdir -p "$(dirname "$IMAGE_TAR_PATH")"
    log_info "Exporting image tar: $IMAGE_TAR_PATH"
    docker save "$IMAGE_NAME" -o "$IMAGE_TAR_PATH"
}

if ! command -v docker >/dev/null 2>&1; then
    log_error "docker not found in PATH"
    exit 1
fi

if image_exists; then
    log_info "Image already exists: $IMAGE_NAME"
    if verify_image_runtime; then
        export_image_tar
        exit 0
    fi
    log_warn "Existing image validation failed, will rebuild: $IMAGE_NAME"
fi

if [ -f "$IMAGE_TAR_PATH" ]; then
    log_info "Loading image from tar: $IMAGE_TAR_PATH"
    docker load -i "$IMAGE_TAR_PATH" >/dev/null
    if image_exists && verify_image_runtime; then
        log_info "Loaded image successfully: $IMAGE_NAME"
        export_image_tar
        exit 0
    fi
    log_warn "Tar load completed but image validation failed: $IMAGE_NAME"
fi

if [ -f "$IMAGE_DOCKERFILE" ]; then
    log_info "Building image locally from Dockerfile: $IMAGE_DOCKERFILE"
    log_info "Using base image: $IMAGE_BASE"
    docker build \
        --build-arg "BASE_IMAGE=$IMAGE_BASE" \
        --build-arg "APT_MIRROR=$APT_MIRROR" \
        -t "$IMAGE_NAME" \
        -f "$IMAGE_DOCKERFILE" \
        "$IMAGE_BUILD_CONTEXT"
    if image_exists && verify_image_runtime; then
        log_info "Built image successfully: $IMAGE_NAME"
        export_image_tar
        exit 0
    fi
    log_warn "Build completed but image validation failed: $IMAGE_NAME"
fi

log_warn "Falling back to registry pull: $IMAGE_NAME"
docker pull "$IMAGE_NAME"

if image_exists && verify_image_runtime; then
    log_info "Pulled image successfully: $IMAGE_NAME"
    export_image_tar
    exit 0
fi

log_error "Failed to prepare validated image: $IMAGE_NAME"
exit 1

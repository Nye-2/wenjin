# Wenjin (问津) - Backend Dockerfile
# Multi-stage build for Gateway and LangGraph services

ARG PYTHON_IMAGE=python:3.13-slim
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG APT_MIRROR=
ARG APT_SECURITY_MIRROR=

# ============================================
# Base Stage - Common dependencies
# ============================================
FROM ${PYTHON_IMAGE} AS base

ARG PIP_INDEX_URL
ARG APT_MIRROR
ARG APT_SECURITY_MIRROR

# Install system dependencies
RUN set -eux; \
    if [ -n "${APT_SECURITY_MIRROR}" ]; then \
      sed -i "s|http://deb.debian.org/debian-security|${APT_SECURITY_MIRROR%/}|g" /etc/apt/sources.list /etc/apt/sources.list.d/*.sources 2>/dev/null || true; \
      sed -i "s|https://deb.debian.org/debian-security|${APT_SECURITY_MIRROR%/}|g" /etc/apt/sources.list /etc/apt/sources.list.d/*.sources 2>/dev/null || true; \
    fi; \
    if [ -n "${APT_MIRROR}" ]; then \
      sed -i "s|http://deb.debian.org/debian|${APT_MIRROR%/}|g" /etc/apt/sources.list /etc/apt/sources.list.d/*.sources 2>/dev/null || true; \
      sed -i "s|https://deb.debian.org/debian|${APT_MIRROR%/}|g" /etc/apt/sources.list /etc/apt/sources.list.d/*.sources 2>/dev/null || true; \
    fi; \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager without depending on GHCR
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    UV_INDEX_URL=${PIP_INDEX_URL}
RUN python -m pip install --no-cache-dir --upgrade pip uv

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Set working directory
WORKDIR /app

# ============================================
# Builder Stage - Install dependencies
# ============================================
FROM base AS builder

ARG PIP_INDEX_URL

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-install-project --no-dev

# ============================================
# Gateway Stage - FastAPI Service
# ============================================
FROM base AS gateway

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY src/ ./src/
COPY config.yaml ./
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY skills/public/ ./skills/public/
COPY seed/ ./seed/

# Create uploads directory
RUN mkdir -p /app/uploads

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f "http://localhost:8001/api/models?purpose=chat" || exit 1

# Default command - run gateway server
CMD ["python", "-m", "uvicorn", "src.gateway.app:app", "--host", "0.0.0.0", "--port", "8001"]

# ============================================
# LangGraph Stage - Agent Server
# ============================================
FROM base AS langgraph

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY src/ ./src/
COPY config.yaml ./
COPY langgraph.json ./
COPY skills/public/ ./skills/public/
COPY seed/ ./seed/

# Create uploads directory
RUN mkdir -p /app/uploads

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 2024

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:2024/info || exit 1

# Default command - run langgraph API server
CMD ["langgraph", "dev", "--no-browser", "--no-reload", "--host", "0.0.0.0", "--port", "2024", "--config", "langgraph.json"]

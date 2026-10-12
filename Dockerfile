# Multi-stage Dockerfile for NexusIQ Enterprise Intelligence Gateway
# Blueprint § 14: Multi-stage, non-root user, pinned dependencies, small base image

# Stage 1: Dependency builder
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast locked dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.5.15 /uv /bin/uv

COPY pyproject.toml uv.lock ./
COPY src/ ./src/

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

RUN uv sync --all-extras --locked --no-dev --no-editable

# Stage 2: Lightweight runtime image
FROM python:3.12-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security (Blueprint § 14.1)
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/bash -m appuser

# Copy virtual environment from builder
COPY --from=builder --chown=appuser:appgroup /build/.venv /app/.venv

# Copy application source and configuration
COPY --chown=appuser:appgroup src/ /app/src/
COPY --chown=appuser:appgroup config/ /app/config/
COPY --chown=appuser:appgroup apps/ /app/apps/
COPY --chown=appuser:appgroup db/ /app/db/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1

USER appuser

EXPOSE 8000

# Container liveness health check (Blueprint § 14.1 & § 15.2)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/v1/health/live || exit 1

ENTRYPOINT ["python", "-m", "nexusiq", "serve", "--api", "--host", "0.0.0.0", "--port", "8000"]

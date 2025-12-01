# Multi-stage Dockerfile for agentic-hooks-backend
# Optimized for small image size and fast builds

# ==============================================================================
# Stage 1: Build
# ==============================================================================
FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for caching
COPY pyproject.toml ./

# Create virtual environment and install dependencies
RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv pip install --no-cache .

# ==============================================================================
# Stage 2: Runtime
# ==============================================================================
FROM python:3.12-slim as runtime

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy source code
COPY src/ ./src/

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Default configuration
ENV HOST="0.0.0.0"
ENV PORT="8080"
ENV LOG_LEVEL="INFO"
ENV STORAGE_TYPE="auto"
ENV JSONL_PATH="/data/events.jsonl"

# Create data directory for JSONL storage
RUN mkdir -p /data && chown appuser:appuser /data

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Expose port
EXPOSE 8080

# Run the application
CMD ["uvicorn", "hooks_backend.main:app", "--host", "0.0.0.0", "--port", "8080"]

# Agentic Primitives: Secure Base Image
# Minimal, security-hardened base for building workspace images
#
# Build (from agentic-primitives root):
#   docker build -t agentic-base:latest -f providers/workspaces/base/Dockerfile .
#
# Features:
#   - Minimal Debian slim base
#   - Python 3.12 + uv (fast package manager)
#   - Security hardening (non-root, no setuid)
#   - No agent runtime - meant for extension
#
# See ADR-027: Provider-Based Workspace Images

FROM debian:bookworm-slim AS base

ENV DEBIAN_FRONTEND=noninteractive

# Minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    curl \
    ca-certificates \
    git \
    jq \
    procps \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/ \
    && mv /root/.local/bin/uvx /usr/local/bin/ \
    && rm -rf /root/.local

# Create non-root user
RUN groupadd --gid 1000 agent \
    && useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home agent

# Standard directories
RUN mkdir -p /workspace /opt/agentic/hooks /opt/agentic/config \
    && chown -R agent:agent /workspace /opt/agentic

# Security: Remove setuid/setgid binaries
RUN find / -perm /6000 -type f -exec chmod a-s {} \; 2>/dev/null || true

WORKDIR /workspace
USER agent

ENV HOME=/home/agent \
    WORKSPACE_DIR=/workspace \
    AGENTIC_HOOKS_DIR=/opt/agentic/hooks \
    PYTHONPATH=/opt/agentic/hooks:$PYTHONPATH

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=2 \
    CMD [ "test", "-w", "/workspace" ]

CMD ["bash"]

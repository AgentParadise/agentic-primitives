# Agentic Primitives: Claude CLI Workspace Image
# Production-ready Docker image with Claude CLI for agent execution
#
# ⚠️  BUILD VIA: scripts/build-provider.py claude-cli
#     This Dockerfile expects a staged build context, not the raw repo.
#
# Features:
#   - Node.js 22 LTS (required for Claude CLI)
#   - Python 3.12 + uv (for hooks and agentic packages)
#   - Claude CLI with JSONL event emission to stdout
#   - Pre-bundled primitive hooks with agentic_events
#   - Security hardening (non-root, no setuid)
#
# Events are emitted as JSONL to stdout, captured by the agent runner.
#
# See ADR-027: Provider-Based Workspace Images

# =============================================================================
# Stage 1: Node.js base with system dependencies
# =============================================================================
FROM node:22-slim AS base

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Python
    python3 \
    python3-venv \
    # Essentials
    curl \
    ca-certificates \
    git \
    jq \
    # Process management
    procps \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# =============================================================================
# Stage 2: Install package managers and Claude CLI
# =============================================================================
FROM base AS tooling

# Install uv (fast Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/ \
    && mv /root/.local/bin/uvx /usr/local/bin/ \
    && rm -rf /root/.local

# Install Claude CLI globally via npm
RUN npm install -g @anthropic-ai/claude-code

# =============================================================================
# Stage 3: Install Python packages from staged wheels
# =============================================================================
FROM tooling AS packages

# Copy pre-built wheels from staged build context
COPY packages/*.whl /tmp/packages/

# Install agentic packages with uv
# Using --break-system-packages since we're in a container
# pyjwt is required for Claude CLI MCP authentication
RUN uv pip install --system --break-system-packages --no-cache /tmp/packages/*.whl pyjwt \
    && rm -rf /tmp/packages

# =============================================================================
# Stage 4: Final image with hooks and security
# =============================================================================
FROM packages AS final

# Create non-root user (node:22-slim already has node:node with uid/gid 1000)
# We'll use the existing 'node' user but rename home to /home/agent for clarity
RUN usermod -l agent -d /home/agent -m node \
    && groupmod -n agent node \
    && mkdir -p /home/agent \
    && chown -R agent:agent /home/agent

# Create directories
RUN mkdir -p /workspace \
    && mkdir -p /opt/agentic/hooks \
    && mkdir -p /opt/agentic/config \
    && chown -R agent:agent /workspace \
    && chown -R agent:agent /opt/agentic

# Copy pre-staged hooks from build context
COPY hooks/ /opt/agentic/hooks/

# Set permissions on hooks
RUN chmod -R 755 /opt/agentic/hooks \
    && find /opt/agentic/hooks -name "*.py" -exec chmod 755 {} \; \
    && chown -R agent:agent /opt/agentic/hooks

# Verify installations (before security hardening)
RUN claude --version && python3 --version && node --version && uv --version

# Security: Remove setuid/setgid binaries (exclude /usr/local)
RUN find / -path /usr/local -prune -o -perm /6000 -type f -exec chmod a-s {} \; 2>/dev/null || true

# Set working directory
WORKDIR /workspace

# Switch to non-root user
USER agent

# Environment variables
ENV HOME=/home/agent \
    WORKSPACE_DIR=/workspace \
    # Hooks location
    AGENTIC_HOOKS_DIR=/opt/agentic/hooks \
    # Python path for validators
    PYTHONPATH=/opt/agentic/hooks

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=2 \
    CMD [ "test", "-w", "/workspace" ]

# Default command
CMD ["bash"]

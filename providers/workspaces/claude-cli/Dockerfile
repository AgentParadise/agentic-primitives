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
#   - LSP language servers (pyright, typescript-language-server, rust-analyzer)
#   - Security hardening (non-root, no setuid)
#
# LSP Architecture:
#   The image bundles LSP binaries and pre-enables the official Claude Code LSP
#   plugins (pyright-lsp, typescript-lsp, rust-analyzer-lsp) in settings.json.
#   LSP servers are LAZY — they only start when Claude encounters files in the
#   matching language. An agent working on a Python-only repo will NOT start
#   rust-analyzer or typescript-language-server. This means the image is safe
#   for multi-agent orchestration: only the LSP servers actually needed per-task
#   consume memory at runtime.
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
    tree \
    # Process management
    procps \
    # Required for gh CLI installation
    gnupg \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create python -> python3 symlink for compatibility
RUN ln -sf /usr/bin/python3 /usr/local/bin/python

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | gpg --dearmor -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
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
# LSP: Language Servers for code intelligence
# Plugins: pyright-lsp, typescript-lsp, rust-analyzer-lsp (claude-plugins-official)
# =============================================================================

# TypeScript + Python LSP servers (via npm, same PATH as Claude CLI)
# Provides: typescript-language-server, pyright-langserver
RUN npm install -g typescript typescript-language-server pyright

# Rust: build deps for toolchain and cargo builds at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Rust toolchain + rust-analyzer
# Installed to /usr/local (not /home) to survive tmpfs mounts at runtime
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- \
    -y \
    --default-toolchain stable \
    --profile minimal \
    --no-modify-path \
    && rustup component add rust-analyzer \
    && chmod -R a+rX /usr/local/rustup /usr/local/cargo

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
# ADR-036: Workspace structure convention
# - artifacts/input/  : Previous phase outputs (read-only, populated by framework)
# - artifacts/output/ : Current phase deliverables (agent writes here)
# - repos/            : Clone repositories here
RUN mkdir -p /workspace/artifacts/input \
    && mkdir -p /workspace/artifacts/output \
    && mkdir -p /workspace/repos \
    && mkdir -p /opt/agentic/hooks \
    && mkdir -p /opt/agentic/config \
    && mkdir -p /home/agent/.claude \
    && chown -R agent:agent /workspace \
    && chown -R agent:agent /opt/agentic \
    && chown -R agent:agent /home/agent/.claude

# NOTE: ~/.claude/settings.json is created by entrypoint.sh at runtime
# because /home/agent is a tmpfs mount that wipes anything baked into the image.

# Copy entrypoint script
COPY scripts/entrypoint.sh /opt/agentic/entrypoint.sh

# Copy pre-staged hooks from build context
COPY hooks/ /opt/agentic/hooks/

# Set permissions on hooks and entrypoint
RUN chmod -R 755 /opt/agentic/hooks \
    && find /opt/agentic/hooks -name "*.py" -exec chmod 755 {} \; \
    && chmod 755 /opt/agentic/entrypoint.sh \
    && chown -R agent:agent /opt/agentic

# Verify core installations (before security hardening)
RUN claude --version && python3 --version && node --version && uv --version && gh --version

# Verify LSP server installations
RUN typescript-language-server --version \
    && pyright-langserver --version \
    && rust-analyzer --version \
    && rustc --version \
    && cargo --version

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
    PYTHONPATH=/opt/agentic/hooks \
    # Disable Claude Code attribution in commits/PRs
    ANTHROPIC_NO_ATTRIBUTION=1 \
    # Use uv for Python execution (faster, better caching)
    UV_SYSTEM_PYTHON=1 \
    # Rust toolchain paths
    # RUSTUP_HOME: read-only toolchain installed during build
    # CARGO_HOME: writable location for agent user (registry index, git checkouts)
    # /usr/local/cargo/bin stays on PATH for pre-installed binaries (cargo, rustc, rust-analyzer)
    RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/home/agent/.cargo \
    PATH=/usr/local/cargo/bin:$PATH

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=2 \
    CMD [ "test", "-w", "/workspace" ]

# Entrypoint configures the workspace from env vars, then execs to CMD
# This runs AFTER tmpfs mounts, so configuration persists correctly
ENTRYPOINT ["/opt/agentic/entrypoint.sh"]

# Default command
CMD ["bash"]

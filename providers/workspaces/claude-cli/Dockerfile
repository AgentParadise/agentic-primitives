# Agentic Primitives: Claude CLI Workspace Image
# Production-ready Docker image with Claude CLI for agent execution
#
# ⚠️  BUILD VIA: scripts/build-provider.py claude-cli
#     This Dockerfile expects a staged build context, not the raw repo.
#
# Features:
#   - Node.js 22 LTS (required for Claude CLI)
#   - Python 3.12 + uv (for hooks and agentic packages)
#   - Claude CLI with plugin-based hook loading via --plugin-dir (ADR-033)
#   - Pre-bundled plugins (sdlc, workspace) with agentic_events for observability
#   - LSP language servers (pyright, typescript-language-server, rust-analyzer)
#   - Security hardening (non-root, no setuid)
#
# Plugin Architecture (ADR-033):
#   Plugins are baked into /opt/agentic/plugins/ and loaded at runtime via
#   --plugin-dir flags built by the entrypoint. This is the same plugin format
#   used locally, ensuring identical behavior in both environments.
#   Plugin env vars declared in requires_env are auto-forwarded by the
#   agentic-isolation orchestrator.
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
# Events are emitted as JSONL to stderr, captured by the agent runner.
#
# See ADR-027: Provider-Based Workspace Images
# See ADR-033: Plugin-Native Workspace Images

# Global build args (declared before any FROM so all stages can inherit).
# Stages that need these must re-declare `ARG <name>` without a default to
# pull the value in. Bump deliberately — controls JSONL output contract,
# tool names (Agent vs Task), stream-json event schema, hook event names.
# See ClaudeToolName in agentic_events.types.
ARG CLAUDE_CLI_VERSION=2.1.126
# Codex CLI is installed alongside claude so a phase's primary agent can
# delegate one-shot to the other harness (opt-in via agent.allow_delegation).
ARG CODEX_CLI_VERSION=0.144.6

# =============================================================================
# Stage 1: Node.js base with system dependencies
# =============================================================================
FROM node:22-slim AS base

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies (Python is provided by uv, not apt)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    jq \
    tree \
    procps \
    gnupg \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

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

# Install uv (fast Python package + interpreter manager).
# Use the official uv image as a stage to copy the binary cleanly — avoids
# curl-piped installer and gives a reproducible source for the binary.
# Pin uv to a specific version — `:latest` would silently change between
# builds and is non-reproducible. Bump deliberately.
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /usr/local/bin/

# Install Python via uv (replaces apt python3) and create a system venv
# at /opt/venv that all Python packages install into. World-readable so the
# non-root agent user can use it at runtime.
# Pin patch version so image's Python doesn't drift across rebuilds.
ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN uv python install 3.12.13 \
    && uv venv --python 3.12.13 /opt/venv \
    && chmod -R a+rX /opt/uv /opt/venv

# Install Claude CLI globally via npm. Version pinned via global ARG above.
ARG CLAUDE_CLI_VERSION
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CLI_VERSION}
# Install Codex CLI globally (delegation target). Pinned via global ARG above.
ARG CODEX_CLI_VERSION
RUN npm install -g @openai/codex@${CODEX_CLI_VERSION}
RUN claude --version && codex --version

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

# Install agentic packages into /opt/venv (uv picks it up via VIRTUAL_ENV).
# pyjwt is required for Claude CLI MCP authentication
RUN uv pip install --no-cache /tmp/packages/*.whl pyjwt \
    && rm -rf /tmp/packages

# =============================================================================
# Stage 4: Final image with plugins and security
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
    && mkdir -p /opt/agentic/plugins \
    && mkdir -p /opt/agentic/config \
    && mkdir -p /home/agent/.claude \
    && chown -R agent:agent /workspace \
    && chown -R agent:agent /opt/agentic \
    && chown -R agent:agent /home/agent/.claude

# NOTE: ~/.claude/settings.json is created by entrypoint.sh at runtime
# because /home/agent is a tmpfs mount that wipes anything baked into the image.

# Copy entrypoint script and workspace-shipped git hooks.
# git-hooks/ holds non-observability git hooks owned by the workspace itself
# (e.g. prepare-commit-msg for operator Co-authored-by attribution). These
# are NOT Claude Code plugins — the entrypoint installs them into the
# runtime git hooks directory alongside hooks contributed by plugins.
COPY scripts/entrypoint.sh /opt/agentic/entrypoint.sh
COPY scripts/git-hooks/ /opt/agentic/git-hooks/

# Copy pre-staged plugins from build context (ADR-033)
# Each plugin is a self-contained directory with .claude-plugin/plugin.json
# and hooks/hooks.json using ${CLAUDE_PLUGIN_ROOT} for path resolution.
COPY plugins/ /opt/agentic/plugins/

# Copy memory primitive adapters (ADR-036)
# The /opt/agentic/memory/ tree holds:
#   - doctor       — bash entry that exec's `python -m agentic_memory.doctor`
#   - <provider>/init.sh   — env-var translation for each supported provider
#   - <provider>/doctor.sh — provider-specific health checks (optional)
# The Python agentic_memory package itself is installed into /opt/venv via
# the wheel staging in stage 3. The audit directory /var/agentic/memory-doctor/
# is created by the entrypoint at first use; orchestrators bind-mount it for
# durable audit logs.
COPY memory/ /opt/agentic/memory/
RUN mkdir -p /var/agentic/memory-doctor \
    && chown -R agent:agent /var/agentic

# Set permissions on plugins, entrypoint, memory adapters, and workspace-shipped hooks
RUN chmod -R 755 /opt/agentic/plugins /opt/agentic/git-hooks \
    && find /opt/agentic/plugins -name "*.py" -exec chmod 755 {} \; \
    && chmod 755 /opt/agentic/entrypoint.sh \
    && chmod 755 /opt/agentic/memory/doctor \
    && find /opt/agentic/memory -name "init.sh" -exec chmod 755 {} \; \
    && find /opt/agentic/memory -name "doctor.sh" -exec chmod 755 {} \; \
    && chown -R agent:agent /opt/agentic

# Verify core installations (before security hardening)
RUN claude --version && python3 --version && node --version && uv --version && gh --version

# Verify LSP server installations
RUN typescript-language-server --version \
    && pyright --version \
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
    # Plugins location (ADR-033)
    AGENTIC_PLUGINS_DIR=/opt/agentic/plugins \
    # Disable Claude Code attribution in commits/PRs
    ANTHROPIC_NO_ATTRIBUTION=1 \
    # Python lives in /opt/venv — installed and managed by uv (not apt).
    # VIRTUAL_ENV + PATH make the venv's python/pip the default.
    VIRTUAL_ENV=/opt/venv \
    # Rust toolchain paths
    # RUSTUP_HOME: read-only toolchain installed during build
    # CARGO_HOME: writable location for agent user (registry index, git checkouts)
    # /usr/local/cargo/bin stays on PATH for pre-installed binaries (cargo, rustc, rust-analyzer)
    RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/home/agent/.cargo \
    PATH=/usr/local/cargo/bin:$PATH

# Labels for version tracking and image selection.
# Re-declare ARG (no default) to pull value from the global ARG declared
# before any FROM — build args are stage-scoped and don't carry across.
ARG CLAUDE_CLI_VERSION
LABEL agentic.claude_cli_version=${CLAUDE_CLI_VERSION}
ARG CODEX_CLI_VERSION
LABEL agentic.codex_cli_version=${CODEX_CLI_VERSION}

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=2 \
    CMD [ "test", "-w", "/workspace" ]

# Entrypoint configures the workspace from env vars, then execs to CMD
# This runs AFTER tmpfs mounts, so configuration persists correctly
ENTRYPOINT ["/opt/agentic/entrypoint.sh"]

# Default command
CMD ["bash"]

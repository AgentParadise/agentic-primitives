# Agentic Primitives: Interactive-tmux Workspace Image
#
# A single image bundling claude, codex, and gemini interactive CLIs plus
# tmux, designed to be driven from the host via:
#   docker exec <container> tmux send-keys ...
#   docker exec <container> tmux capture-pane -p ...
#
# This is the survive-the-Max-plan workspace transport — once `claude -p`
# leaves the Max plan, the interactive TUI driven over tmux gives back
# bidirectional control of agents on subscription billing. The provider
# bundles all three CLIs so a single workspace can host a small swarm.
#
# Validated against EXP-01..04 (all `go`); see experiments/EXP-05-...md
# for the design that this image implements.
#
# Build via the existing repo convention (DO NOT `docker build` directly):
#   uv run scripts/build-provider.py interactive-tmux
#   just build-provider interactive-tmux
#
# Security:
#   - Non-root user (agent:agent, uid 1000)
#   - No credentials baked in; throwaway mounts at `docker run` time
#   - Setuid binaries stripped (non-essential paths only)
#
# See ADR-027: Provider-Based Workspace Images for the broader convention.

# Pinned CLI versions — bump deliberately. These match the per-agent
# experiments that proved the protocol works.
# Match claude-cli provider for parity (EXP-01).
ARG CLAUDE_CLI_VERSION=2.1.126
# Matches EXP-02 (cod_1).
ARG CODEX_CLI_VERSION=0.139.0
# Latest at hypothesis commit time; LSB-class CLI, no per-version probe yet.
ARG GEMINI_CLI_VERSION=latest

FROM rust:1.88-slim AS itmux-builder

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    pkg-config \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /src
COPY driver-rs/ /src/
RUN cargo build --release --locked

FROM node:22-slim

ENV DEBIAN_FRONTEND=noninteractive

# System deps:
#   tmux                — the interactive transport
#   git/jq/curl/procps  — workspace basics
#   ca-certificates     — TLS for npm + agent APIs
#   python3/pip         — for plugin hooks + any container-side helpers
#   gnupg               — required by gh CLI keyring step (parity w/ claude-cli)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tmux \
    git \
    jq \
    curl \
    ca-certificates \
    procps \
    python3 \
    python3-pip \
    gnupg \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install the three agent CLIs globally.
# Re-declare ARGs because build args are stage-scoped.
ARG CLAUDE_CLI_VERSION
ARG CODEX_CLI_VERSION
ARG GEMINI_CLI_VERSION
RUN npm install -g \
        @anthropic-ai/claude-code@${CLAUDE_CLI_VERSION} \
        @openai/codex@${CODEX_CLI_VERSION} \
        @google/gemini-cli@${GEMINI_CLI_VERSION} \
        skills@1.5.14 \
    && claude --version \
    && codex --version \
    && gemini --version \
    && skills --version

# Non-root user. node:22-slim ships node:node uid/gid 1000; rename to
# agent for parity with the claude-cli provider's user model.
RUN usermod -l agent -d /home/agent -m node \
    && groupmod -n agent node \
    && mkdir -p /home/agent /workspace \
    && chown -R agent:agent /home/agent /workspace

# Entrypoint is INTENTIONALLY minimal compared to claude-cli's. The
# interactive provider's lifecycle is driven from the host (driver
# orchestrates tmux), so we do not pre-populate ~/.claude/settings.json
# (which would clobber mounted user prefs — EXP-01 FRICTION F-2).
COPY scripts/entrypoint.sh /opt/agentic/entrypoint.sh
COPY --from=itmux-builder /src/target/release/itmux /usr/local/bin/itmux
RUN chmod 755 /opt/agentic/entrypoint.sh \
    && chmod 755 /usr/local/bin/itmux \
    && mkdir -p /opt/agentic \
    && chown -R agent:agent /opt/agentic

# Observability runtime for Claude Code hooks. The driver sets
# AGENTIC_EVENTS_JSONL for `itmux run`, and observe.py appends hook JSONL there
# so the host-side fanout can normalize it without relying on TUI stderr/stdout.
COPY plugins/observability /opt/agentic/plugins/observability
COPY packages/agentic_events-*.whl /tmp/packages/
RUN python3 -m pip install --break-system-packages --no-cache-dir /tmp/packages/agentic_events-*.whl \
    && rm -rf /tmp/packages \
    && chmod -R a+rX /opt/agentic/plugins/observability \
    && chmod 755 /opt/agentic/plugins/observability/hooks/handlers/observe.py \
    && chown -R agent:agent /opt/agentic/plugins

# Security hardening: strip setuid bits outside /usr/local (which holds
# the npm-installed CLIs and the Node runtime — leave those untouched).
RUN find / -path /usr/local -prune -o -perm /6000 -type f -exec chmod a-s {} \; 2>/dev/null || true

WORKDIR /workspace
USER agent

ENV HOME=/home/agent \
    WORKSPACE_DIR=/workspace \
    TERM=xterm-256color \
    # Disable Claude attribution defaults for parity with claude-cli provider.
    ANTHROPIC_NO_ATTRIBUTION=1

# Version labels — driver can read these via `docker inspect` to confirm
# image identity and CLI versions at workspace startup.
LABEL agentic.provider=interactive-tmux
LABEL agentic.claude_cli_version=${CLAUDE_CLI_VERSION}
LABEL agentic.codex_cli_version=${CODEX_CLI_VERSION}
LABEL agentic.gemini_cli_version=${GEMINI_CLI_VERSION}

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=2 \
    CMD [ "test", "-w", "/workspace" ]

ENTRYPOINT ["/opt/agentic/entrypoint.sh"]

# The container holds open waiting for `docker exec` from the host driver.
# The driver starts tmux sessions and launches CLIs inside them via exec.
CMD ["sleep", "infinity"]

# Agentic Primitives: Omni Agent Workspace Image
# A workspace image that hosts BOTH harnesses (claude and codex) on the
# shared ADR-040 capability runtime.
#
# ⚠️  BUILD VIA: scripts/build-provider.py omni-agent
#     This Dockerfile expects a staged build context, not the raw repo.
#
# This is the SECOND implementation of the ADR-040 section 12 image contract.
# It is derived from providers/workspaces/claude-cli/Dockerfile by SUBTRACTION,
# and the four things section 12 obliges it to do are the four things it does:
#   1. ENTRYPOINT is the shared workspace/entrypoint.sh, unforked.
#   2. /opt/agentic/capabilities/ is populated from the staged shared tree.
#   3. Module scripts are made executable at exactly the depths the entrypoint
#      constructs paths at (see the chmod block near the end).
#   4. AGENTIC_CAPABILITIES is an image ENV, and /opt/venv ships the Python
#      packages the shipped `doctor` entries exec.
#
# What was deliberately NOT carried over from claude-cli, and why:
#   - LSP servers (pyright, typescript-language-server) and the whole Rust
#     toolchain + rust-analyzer. Those exist to back three Claude Code LSP
#     plugin identifiers; they are harness-specific weight, not part of the
#     capability contract. The manifest carries no capabilities.lsp_servers
#     block to match.
#   - COPY scripts/git-hooks/ -> /opt/agentic/git-hooks/. Those hooks are
#     owned by the claude-cli provider (workspace/entrypoint.sh:113-115 says
#     so explicitly) and live in that provider's directory. The entrypoint's
#     git-hooks composition loop skips a source directory that does not
#     exist, so omitting them is a supported subtraction, not a breakage.
#
# See ADR-027: Provider-Based Workspace Images
# See ADR-033: Plugin-Native Workspace Images
# See ADR-040: Workspace Capability Modules (section 12 is the contract)

# Global build args (declared before any FROM so all stages can inherit).
# Stages that need these must re-declare `ARG <name>` without a default.
# Both harnesses are pinned; bump deliberately.
ARG CLAUDE_CLI_VERSION=2.1.126
ARG CODEX_CLI_VERSION=0.144.6

# =============================================================================
# Stage 1: Node.js base with system dependencies
# =============================================================================
FROM node:22-slim AS base

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
# Stage 2: Package managers and both agent harnesses
# =============================================================================
FROM base AS tooling

# Install uv (fast Python package + interpreter manager). Pinned; `:latest`
# would silently change between builds.
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /usr/local/bin/

# Install Python via uv and create a system venv at /opt/venv that all Python
# packages install into. World-readable so the non-root agent user can use it
# at runtime. This venv is what ADR-040 s12 obligation 5 is satisfied by: the
# capability `doctor` entries prefer /opt/venv/bin/python.
ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN uv python install 3.12.13 \
    && uv venv --python 3.12.13 /opt/venv \
    && chmod -R a+rX /opt/uv /opt/venv

# Both harnesses, each pinned via the global ARGs above. Neither is "the"
# agent in this image: a caller selects one per invocation.
ARG CLAUDE_CLI_VERSION
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CLI_VERSION}
ARG CODEX_CLI_VERSION
RUN npm install -g @openai/codex@${CODEX_CLI_VERSION}
RUN claude --version && codex --version

# Install the skills CLI globally via npm. Pin exact version deliberately.
RUN npm install -g skills@1.5.14

# =============================================================================
# Stage 3: Install Python packages from staged wheels
# =============================================================================
FROM tooling AS packages

# Copy pre-built wheels from staged build context
COPY packages/*.whl /tmp/packages/

# Install agentic packages into /opt/venv (uv picks it up via VIRTUAL_ENV).
# agentic_memory and agentic_session_store are what the two capability
# doctors exec; pyjwt is required for MCP authentication.
RUN uv pip install --no-cache /tmp/packages/*.whl pyjwt \
    && rm -rf /tmp/packages

# =============================================================================
# Stage 4: Final image with plugins, capability runtime, and security
# =============================================================================
FROM packages AS final

# Create non-root user (node:22-slim already has node:node with uid/gid 1000)
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

# Copy the SHARED entrypoint (ADR-040 s12 obligation 1). The source path is
# the staged shared tree; the destination is fixed by s12.1 and must stay
# byte-identical to claude-cli's.
COPY workspace/entrypoint.sh /opt/agentic/entrypoint.sh

# Copy pre-staged plugins from build context (ADR-033)
COPY plugins/ /opt/agentic/plugins/

# Copy capability adapters (ADR-040 s12 obligation 2)
# The /opt/agentic/capabilities/ tree holds one directory per registered
# capability (memory, session-store, ...), each with:
#   - doctor               — bash entry that exec's `python -m <pkg>.doctor`
#   - <provider>/init.sh   — env-var translation for each supported provider
#   - <provider>/doctor.sh — provider-specific health checks (optional)
#   - <provider>/finalize.sh: post-agent hook (optional)
# The Python packages themselves are installed into /opt/venv in stage 3.
COPY workspace/capabilities/ /opt/agentic/capabilities/

# Session-store exporter (session-store capability).
#
# The image now SHIPS the exporter, which it previously refused to do. The
# refusal was right at the time and is no longer: the only client available then
# was named for one vendor's store, and baking it would have made a
# general-purpose multi-agent workspace image depend on that company's product.
#
# What changed is that the client was extracted, genericised, and published as
# the reference implementation of the APS-V1-0004 Exporter profile. So this
# depends on a public client of a public contract, which is the arrangement the
# standard exists to make possible. A deployment that wants a different
# conformant client still overrides it with
# AGENTIC_SESSION_STORE_EXPORTER_BIN.
#
# Copied FROM an OCI image by DIGEST rather than curled at build time. A digest
# is immutable, so the bytes cannot silently change under a rebuild.
#
# A digest guarantees WHICH bytes, not WHO published them. Those are different
# properties, and only the second answers "should this run alongside a store
# credential". Provenance is therefore established in CI, before the build:
# build-workspace-images.yml verifies this exact digest's cosign signature
# against the exporter repository's release-workflow identity, and the build
# cannot start if that fails. Reading the digest out of THIS line is what keeps
# the verified image and the copied image the same image.
#
# The source image is FROM scratch and exists only to be copied out of.
#
# GLIBC FLOOR, and the reason this only copies one binary. The exporter release
# builds on ubuntu-latest (glibc 2.39); this base is Debian 12 (glibc 2.36).
# apss-session-reconstitute already fails here with
#
#   libc.so.6: version `GLIBC_2.39' not found
#
# and apss-session-exporter runs only because it happens not to reference a 2.39
# symbol. That is luck, not compatibility: an unrelated upstream change could
# introduce one and break provisioning everywhere at once.
#
# The durable fix belongs upstream - build the release against an older glibc
# baseline, or ship musl static binaries - and is filed there. Until then, the
# RUN below is what turns that from a silent production failure into a build
# failure in this file.
#
# Bump procedure: pick a digest from
# https://github.com/AgentParadise/agentic-session-exporter/releases, verify its
# signature with cosign, and change it here in its own commit so a reviewer sees
# exactly what moved.
#
# agentic-session-exporter v0.1.1, verified 2026-08-19: this digest was pulled
# and the binary run out of it (COPY into debian:12-slim, reports
# "apss-session-exporter 0.1.1"). v0.1.2 changes only the release workflow's own
# verification step and produces identical binaries, so there is no reason to
# chase it here.
# The EXPORTER only. apss-session-reconstitute writes a stored session back to
# disk so a harness can resume it, which is something a developer does on their
# own machine, not something a short-lived workspace container ever needs. It
# also currently requires GLIBC_2.39 while this base is Debian 12 (2.36), so
# copying it would put a binary here that cannot run - see the note below.
COPY --from=ghcr.io/agentparadise/agentic-session-exporter@sha256:a403764b8c102edd872a292d95dab1a68fb60ee981688c3b4f888c79712e6a95 \
     /apss-session-exporter /usr/local/bin/

RUN chmod 755 /usr/local/bin/apss-session-exporter \
    && mkdir -p /var/agentic \
    && chown -R agent:agent /var/agentic \
    `# Execute what was just copied. Buildx runs this once PER TARGET` \
    `# PLATFORM, so it is the only check that proves the arm64 binary is` \
    `# genuinely arm64 rather than an amd64 copy from a single-platform` \
    `# index. It also catches a missing exec bit, a wrong libc, and a` \
    `# truncated copy - at BUILD time, in the layer that caused it, instead` \
    `# of at workspace provision in another repository.` \
    && /usr/local/bin/apss-session-exporter --version

# session-store spool root (ADR-040 / agentic_session_store's DEFAULT_SPOOL).
# The contract defaults AGENTIC_SESSION_STORE_SPOOL to /spool when unset;
# that default must exist and be writable by the non-root agent user.
RUN mkdir -p /spool \
    && chown -R agent:agent /spool

# Permissions on plugins, entrypoint, and capability adapters
# (ADR-040 s12 obligation 3).
#
# The two capability pins below are COPIED VERBATIM from claude-cli and must
# stay that way. They correspond exactly to the three sites where the
# entrypoint builds a module path literally: :373 (depth-3 init.sh), :404
# (depth-2 doctor), :450 (depth-3 finalize.sh). Widening either pin would set
# the executable bit on files nothing can invoke, which reads to a future
# maintainer as evidence that deeper layouts are supported when they are not.
# If the module layout ever gains a level, those three entrypoint sites and
# this block change together.
RUN chmod -R 755 /opt/agentic/plugins \
    && find /opt/agentic/plugins -name "*.py" -exec chmod 755 {} \; \
    && find /opt/agentic -maxdepth 1 -name "*.sh" -exec chmod 755 {} \; \
    && find /opt/agentic/capabilities -mindepth 2 -maxdepth 2 -name "doctor" -exec chmod 755 {} \; \
    && find /opt/agentic/capabilities -name "*.sh" -exec chmod 755 {} \; \
    && chown -R agent:agent /opt/agentic

# Verify core installations (before security hardening).
# Both harnesses are verified: an omni image with one working harness is a
# broken omni image, not a degraded one.
RUN claude --version && codex --version && python3 --version && node --version && uv --version && gh --version

# Verify the capability runtime the image claims to host: both doctors must
# be importable from the venv this image ships.
RUN /opt/venv/bin/python -c "import agentic_memory.doctor, agentic_session_store.doctor"

# Security: Remove setuid/setgid binaries (exclude /usr/local)
RUN find / -path /usr/local -prune -o -perm /6000 -type f -exec chmod a-s {} \; 2>/dev/null || true

WORKDIR /workspace

USER agent

ENV HOME=/home/agent \
    WORKSPACE_DIR=/workspace \
    # Plugins location (ADR-033)
    AGENTIC_PLUGINS_DIR=/opt/agentic/plugins \
    # Capability registry (ADR-040 s12 obligation 4): space-separated list of
    # capability names the entrypoint's 5.6/5.7 loops iterate. A listed
    # capability with no AGENTIC_<CAP>_PROVIDER set is a silent no-op.
    AGENTIC_CAPABILITIES="memory session-store" \
    # Disable Claude Code attribution in commits/PRs
    ANTHROPIC_NO_ATTRIBUTION=1 \
    # Python lives in /opt/venv — installed and managed by uv (not apt).
    VIRTUAL_ENV=/opt/venv

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

# Entrypoint configures the workspace from env vars, then runs CMD through
# the capability finalize wrapper. This runs AFTER tmpfs mounts.
ENTRYPOINT ["/opt/agentic/entrypoint.sh"]

CMD ["bash"]

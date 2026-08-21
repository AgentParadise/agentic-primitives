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
# against a GitHub Actions identity in the exporter REPOSITORY, and the build
# cannot start if that fails. Note the scope honestly: the identity regexp
# accepts any workflow in that repo, on tags or branches, so it proves the
# image came from that repository's CI - not that it came from a tagged
# release. Narrowing it to refs/tags is a worthwhile follow-up. Reading the digest out of THIS line is what keeps
# the verified image and the copied image the same image.
#
# The source image is FROM scratch and exists only to be copied out of.
#
# PRECEDENCE CHANGE FOR EXISTING DEPLOYMENTS. The capability resolves the
# exporter as: AGENTIC_SESSION_STORE_EXPORTER_BIN, then apss-session-exporter,
# then the legacy SeshMagicSessionExporter. Before this commit the image shipped
# neither of the first two, so an operator bind-mounting the legacy name was the
# only binary present and always won. Now the baked apss-session-exporter is
# found first and their mount is ignored.
#
# That is a real behaviour change for anyone doing this, which is why the
# manifest bump is a MINOR rather than a patch: same interface, new capability,
# and an existing setup that silently starts using a different binary. An
# operator who genuinely needs their own build sets
# AGENTIC_SESSION_STORE_EXPORTER_BIN, which still wins over everything.
#
# GLIBC FLOOR: RESOLVED UPSTREAM as of exporter v0.2.1. The Linux binaries are
# now statically linked against musl, so they carry no libc floor at all and
# this base's glibc version is irrelevant to them.
#
# Kept as history because the failure was subtle and could recur if anyone
# moves the release back to a gnu target. Previously the release built for
# *-unknown-linux-gnu on a runner whose glibc had moved to 2.39, above Debian
# 12's 2.36, so apss-session-reconstitute failed with
#
#   libc.so.6: version `GLIBC_2.39' not found
#
# while apss-session-exporter ran only because it happened not to reference a
# 2.39 symbol. That was luck, not compatibility.
#
# The exporter now asserts portability in CI, in its release gate, and in its
# release, all through one script that checks for absence of PT_INTERP and
# DT_NEEDED and then runs each binary inside debian:12-slim. The RUN below
# stays regardless: it is what proves the binary in THIS image works, on both
# target platforms, rather than trusting that upstream still does.
#
# Bump procedure: pick a digest from
# https://github.com/AgentParadise/agentic-session-exporter/releases, verify its
# signature with cosign, and change it here in its own commit so a reviewer sees
# exactly what moved.
#
# agentic-session-exporter v0.5.0, verified 2026-08-21:
#   - cosign verified keyless; certificate subject is
#     .github/workflows/release.yml@refs/tags/v0.5.0, source commit 35584f3
#   - pulled and run out of this exact index digest on BOTH linux/amd64 and
#     linux/arm64; each reports
#     "apss-session-exporter 0.5.0 (APS-V1-0004 SCS 1.0)"
#   - the two binaries differ in size (9708320 on amd64, 9313192 on arm64),
#     which is the cheap proof that the index carries two genuine builds rather
#     than one platform published twice under two names
#   - /apss-session-exporter and /apss-session-reconstitute are both present at
#     mode 0755. Only the exporter is copied out; see the closing note below.
#
# WHY THIS BUMP. v0.5.0 raises RESULT_SCHEMA_VERSION to 2 and adds a `sessions`
# array to the --json result: the session ids the STORE confirmed, not the ones
# the sweep merely attempted. Until now a consumer auditing a workspace learned
# only HOW MANY sessions landed, never WHICH, so a count that came up short
# named nothing and the caller had no way to say what was missing. The array is
# what turns "capture was incomplete" into "session X is absent".
#
# CONSUMER ORDERING IS ALREADY SATISFIED, and it runs the opposite way from the
# v0.4.0 bump. There the image had to move first, because an older exporter
# REJECTED the new flag. A schema bump runs consumer-first instead: a consumer
# pinned to schema 1 alone would read a schema 2 result as UNKNOWN. The
# syntropic137 parser accepts BOTH 1 and 2 and that change is already merged, so
# pinning this image cannot regress the capture probe. The field is purely
# additive - nothing removed, nothing renamed - so a caller that never reads
# `sessions` sees exactly the result v0.4.0 gave it.
#
# Previous pin, for the record:
# agentic-session-exporter v0.4.0, verified 2026-08-20:
#   - cosign verified; certificate subject is
#     .github/workflows/release.yml@refs/tags/v0.4.0
#   - pulled and run out of this exact digest on BOTH linux/amd64 and
#     linux/arm64; each reports "apss-session-exporter 0.4.0"
#   - readelf shows neither PT_INTERP nor DT_NEEDED. Checked with readelf's
#     PRESENCE asserted first and its exit status checked, because a missing
#     readelf produces the same empty output as a clean binary - that guard
#     exists in the exporter's own release checks for exactly this reason.
#     `file` agrees independently: static-pie on amd64, statically linked on
#     arm64.
#
# WHY THIS BUMP. v0.4.0 adds --ignore-state, and the syntropic137 capture
# probe cannot produce a trustworthy verdict without it. That probe runs the
# exporter to AUDIT an agent's own workspace, with the state file somewhere
# the agent can write - so a forged "already sent" entry could make a
# transcript that never reached the store report as a clean sweep. The
# exporter runs as the same uid as the audited process, so no location is
# writable by one and not the other: not READING the file is the only
# available move.
#
# NOT A BEHAVIOUR CHANGE for existing callers. The flag defaults off, and a
# caller that does not pass it is unaffected. It is additive in the other
# direction too: --ignore-state with --health or --dry-run is now a usage
# error (exit 2) rather than false assurance from the forgeable health
# sidecar, or a silent no-op.
#
# CONSUMER ORDERING. An older exporter REJECTS --ignore-state with exit 2,
# which syntropic137's parser reads as UNKNOWN and turns into a backfill
# request on every phase. So the consumer must not pass the flag until it
# pins an image built from this line. Verified against the previous image:
#   apss-session-exporter: unknown flag: --ignore-state / exit=2
#
# Previous pin, for the record:
# agentic-session-exporter v0.3.0, verified 2026-08-20:
#   - cosign verified; certificate subject is
#     .github/workflows/release.yml@refs/tags/v0.3.0
#   - pulled and run out of this exact digest on BOTH linux/amd64 and
#     linux/arm64; each reports "apss-session-exporter 0.3.0"
#   - readelf shows neither PT_INTERP nor DT_NEEDED
#
# WHY THIS BUMP MATTERS, and why finalize.sh had to change first. v0.2.1's
# uploader marked every item in a successful batch as done, REJECTIONS
# INCLUDED. So a transcript the store refused was recorded as sent, the next
# sweep skipped it as skipped_unchanged, and that sweep reported success. One
# transient rejection became permanent silent absence from the store. The solo
# retry path had the same bug, and is the likelier route since it is the
# fallback for a batch that already failed.
#
# v0.3.0 marks only what the store confirmed, counts what it did not
# (`unconfirmed`), scopes its state to the store so repointing at a new one
# does not skip everything, and exits 3 for a sweep that ran without capturing
# everything it found.
#
# EXIT 3 IS A BEHAVIOUR CHANGE for anything treating non-zero as fatal.
# workspace/capabilities/session-store/apss/finalize.sh was taught about
# it in #359, which is already merged. Do not move this pin ahead of a consumer
# that has not been.
#
# Previous pin, for the record:
# agentic-session-exporter v0.2.1, verified 2026-08-19:
#   - cosign verified; certificate subject is
#     .github/workflows/release.yml@refs/tags/v0.2.1
#   - pulled and run out of this exact digest (COPY into debian:12-slim),
#     reports "apss-session-exporter 0.2.1"
#   - readelf shows neither PT_INTERP nor DT_NEEDED, so it is genuinely
#     static (absence of an interpreter alone would not prove that)
#   - SESSION_STORE_ORIGIN_ENV=laptop is now REFUSED
#     (Error: InvalidEnvironment("laptop")) rather than written into every
#     envelope, which is the defect this bump exists to fix
#
# Why the bump matters beyond housekeeping: v0.1.1 DEFAULTED
# origin.environment to "laptop", which is not one of the four classes
# APS-V1-0004 4.2.1 defines (local, vps, container, workflow). Any session
# captured without an explicit SESSION_STORE_ORIGIN_ENV was therefore out of
# spec on a REQUIRED field. (Attribution per deployment is a separate field,
# origin.deployment, which Syntropic137 sets independently.)
# Do not pin v0.2.0: its Linux binaries require glibc 2.39 and cannot run here.
#
# The EXPORTER only. apss-session-reconstitute writes a stored session back to
# disk so a harness can resume it, which is something a developer does on their
# own machine, not something a short-lived workspace container ever needs.
# Copying it would add weight for a path no workspace takes.
COPY --from=ghcr.io/agentparadise/agentic-session-exporter@sha256:6d40917af5ccfb50de9022af4864333577919948c30d00fd53e860ed777cf98b \
     /apss-session-exporter /usr/local/bin/

RUN chmod 755 /usr/local/bin/apss-session-exporter \
    && mkdir -p /var/agentic \
    && chown -R agent:agent /var/agentic \
    `# Execute what was just copied. Buildx runs this once PER TARGET` \
    `# PLATFORM, so it is the only check that proves the arm64 binary is` \
    `# genuinely arm64 rather than an amd64 copy from a single-platform` \
    `# index. It also catches a truncated copy and a binary that cannot` \
    `# execute here - at BUILD time, in the layer that caused it, instead` \
    `# of at workspace provision in another repository. It does NOT catch a` \
    `# missing exec bit: the chmod above sets one unconditionally.` \
    `#` \
    `# ASSERT THE VERSION, do not merely print it. Running --version proves` \
    `# the binary executes; it does not prove WHICH binary was copied. A pin` \
    `# edited to a digest that is signed but older still builds green, and` \
    `# the consumer then gets a workspace whose exporter silently lacks the` \
    `# flag the pin comment promises. Grepping the output is what turns the` \
    `# comment above into something CI enforces.` \
    && /usr/local/bin/apss-session-exporter --version \
    && /usr/local/bin/apss-session-exporter --version \
       | grep -q '^apss-session-exporter 0\.5\.0 '

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

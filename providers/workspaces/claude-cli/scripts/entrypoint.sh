#!/bin/bash
# =============================================================================
# Agentic Workspace Entrypoint
# =============================================================================
#
# This script runs when the container starts (AFTER any tmpfs mounts).
# It configures the workspace from environment variables, then execs to CMD.
#
# Plugin Architecture (ADR-033):
#   Plugins are baked into /opt/agentic/plugins/ at build time. This entrypoint
#   discovers them and builds --plugin-dir flags for Claude CLI. Each plugin
#   directory contains .claude-plugin/plugin.json and hooks/hooks.json using
#   ${CLAUDE_PLUGIN_ROOT} for portable path resolution.
#
# Environment Variables (provided by orchestrator):
#   CLAUDE_CODE_OAUTH_TOKEN - OAuth token for Claude CLI (preferred, cheaper)
#   ANTHROPIC_API_KEY       - Claude API key (fallback if no OAuth token)
#   GIT_AUTHOR_NAME         - Git commit author name (required for git ops)
#   GIT_AUTHOR_EMAIL        - Git commit author email (required for git ops)
#   GITHUB_TOKEN            - GitHub token for git push (optional)
#   SYN_OPERATOR_NAME       - Operator display name for Co-authored-by trailer (optional)
#   SYN_OPERATOR_EMAIL      - Operator email matching a verified GitHub account (optional)
#
# This script is the SINGLE SOURCE OF TRUTH for workspace configuration.
# Orchestrators should NOT have hardcoded setup scripts.
#
# See: agentic-primitives/docs/adrs/033-plugin-native-workspace-images.md
# =============================================================================

set -e

# -----------------------------------------------------------------------------
# 1. Claude CLI Configuration
# -----------------------------------------------------------------------------
# Create ~/.claude/settings.json with LSP plugins enabled.
# This must be done HERE because /home/agent is a tmpfs mount that wipes
# anything baked into the Docker image.
#
# NOTE: Hooks are NO LONGER configured here. They are loaded automatically
# via --plugin-dir flags from the baked-in plugins at /opt/agentic/plugins/.
# This ensures identical hook behavior between local and Docker environments.
#
# LSP plugins (pyright-lsp, typescript-lsp, rust-analyzer-lsp) are enabled by
# default. The LSP servers are LAZY — they only start when Claude encounters
# files in the matching language, so enabling all three does not waste memory
# when only a subset of languages is present in the workspace.

mkdir -p ~/.claude

cat > ~/.claude/settings.json << 'EOF'
{
  "attribution": {
    "commit": "",
    "pr": ""
  },
  "enabledPlugins": {
    "pyright-lsp@claude-plugins-official": true,
    "typescript-lsp@claude-plugins-official": true,
    "rust-analyzer-lsp@claude-plugins-official": true
  }
}
EOF

chmod 600 ~/.claude/settings.json

# -----------------------------------------------------------------------------
# 2. Plugin Discovery (ADR-033)
# -----------------------------------------------------------------------------
# Scan /opt/agentic/plugins/ for valid plugin directories and build
# --plugin-dir flags. A valid plugin has .claude-plugin/plugin.json.
# These flags are stored in AGENTIC_PLUGIN_FLAGS for the orchestrator
# to append when invoking claude CLI.

PLUGIN_FLAGS=""
PLUGINS_DIR="${AGENTIC_PLUGINS_DIR:-/opt/agentic/plugins}"

if [ -d "$PLUGINS_DIR" ]; then
    for plugin_dir in "$PLUGINS_DIR"/*/; do
        if [ -f "${plugin_dir}.claude-plugin/plugin.json" ]; then
            plugin_name=$(basename "$plugin_dir")
            PLUGIN_FLAGS="${PLUGIN_FLAGS} --plugin-dir ${plugin_dir%/}"
            echo "[entrypoint] Discovered plugin: ${plugin_name}"
        fi
    done
fi

# Export for orchestrator use (e.g., agentic-isolation can read this)
export AGENTIC_PLUGIN_FLAGS="${PLUGIN_FLAGS}"

# Also write to a file for easy sourcing by scripts
echo "${PLUGIN_FLAGS}" > /tmp/.agentic-plugin-flags

# -----------------------------------------------------------------------------
# 3. Git Configuration
# -----------------------------------------------------------------------------
# Configure git identity from environment variables.
# These are required for any git commit/push operations.

if [ -n "${GIT_AUTHOR_NAME}" ]; then
    git config --global user.name "${GIT_AUTHOR_NAME}"
    git config --global user.email "${GIT_AUTHOR_EMAIL:-agent@agentic.local}"
    git config --global init.defaultBranch main
fi

# Install workspace git hooks globally (ADR-043).
#
# core.hooksPath is a git global config that overrides the per-repo .git/hooks/
# directory. Setting it here (at container startup) means our hooks fire for
# EVERY repo cloned or initialized inside this container — including repos
# cloned by the agent mid-task.
#
# Two contributing sources, composed into a single runtime directory:
#   1. /opt/agentic/git-hooks/                          — workspace-shipped
#      hooks. Owned by the claude-cli provider itself (this dir is baked in
#      by the Dockerfile from providers/workspaces/claude-cli/scripts/git-hooks/).
#      Currently: prepare-commit-msg for operator Co-authored-by attribution
#      (driven by SYN_OPERATOR_NAME / SYN_OPERATOR_EMAIL env vars; no-op when
#      either is unset).
#   2. /opt/agentic/plugins/observability/hooks/git/    — event-emission hooks
#      from the observability plugin (post-commit, pre-push, post-merge,
#      post-rewrite, post-checkout). These emit JSONL to stderr; the docker
#      exec stream in AgenticEventStreamAdapter merges stderr→stdout, and
#      WorkflowExecutionEngine stores the events in TimescaleDB.
#
# Workspace-shipped hooks are linked first so any future name collision
# resolves in favor of the observability event emitters (rare, but explicit).
GIT_HOOKS_DIR="${HOME}/.git-hooks"
mkdir -p "${GIT_HOOKS_DIR}"

for src_dir in \
    /opt/agentic/git-hooks \
    "${AGENTIC_PLUGINS_DIR:-/opt/agentic/plugins}/observability/hooks/git"; do
    [ -d "${src_dir}" ] || continue
    for src in "${src_dir}"/*; do
        [ -f "${src}" ] || continue
        name=$(basename "${src}")
        case "${name}" in install.py|*.md|*.txt) continue ;; esac
        ln -sf "${src}" "${GIT_HOOKS_DIR}/${name}"
    done
done

if [ -n "$(ls -A "${GIT_HOOKS_DIR}" 2>/dev/null)" ]; then
    git config --global core.hooksPath "${GIT_HOOKS_DIR}"
    echo "[entrypoint] Workspace git hooks composed at ${GIT_HOOKS_DIR}"
fi

# Also set committer identity (git uses both for commits)
if [ -n "${GIT_COMMITTER_NAME:-}" ]; then
    export GIT_COMMITTER_NAME
    export GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-${GIT_AUTHOR_EMAIL:-agent@agentic.local}}"
elif [ -n "${GIT_AUTHOR_NAME}" ]; then
    export GIT_COMMITTER_NAME="${GIT_AUTHOR_NAME}"
    export GIT_COMMITTER_EMAIL="${GIT_AUTHOR_EMAIL:-agent@agentic.local}"
fi

# -----------------------------------------------------------------------------
# 4. GitHub Credentials
# -----------------------------------------------------------------------------
# Store GitHub token in git credential helper and gh CLI config.
# This persists credentials for git push after env vars are cleared.

if [ -n "${GITHUB_TOKEN}" ]; then
    # Git credential helper
    git config --global credential.helper store
    echo "https://x-access-token:${GITHUB_TOKEN}@github.com" > ~/.git-credentials
    chmod 600 ~/.git-credentials

    # GitHub CLI config
    mkdir -p ~/.config/gh
    cat > ~/.config/gh/hosts.yml << GHEOF
github.com:
    oauth_token: ${GITHUB_TOKEN}
    user: ${GIT_AUTHOR_NAME:-agent}
    git_protocol: https
GHEOF
    chmod 600 ~/.config/gh/hosts.yml
fi

# -----------------------------------------------------------------------------
# 5. Workspace Directories
# -----------------------------------------------------------------------------
# Ensure workspace directories exist (should be pre-created in image,
# but verify in case of custom mounts)

mkdir -p /workspace/artifacts/input
mkdir -p /workspace/artifacts/output
mkdir -p /workspace/repos

# Create writable CARGO_HOME for the agent user
# The Rust toolchain binaries live in /usr/local/cargo/bin (read-only, on PATH),
# but cargo needs a writable CARGO_HOME for registry index, git checkouts, etc.
mkdir -p ~/.cargo

# -----------------------------------------------------------------------------
# 5.5 Workspace Context Composition
# -----------------------------------------------------------------------------
# Universal inbound seam — copies orchestrator-supplied context, plugins,
# and subagents from /etc/agentic/workspace/ (bind-mounted read-only) into
# the agent-visible workspace + Claude config locations. Skips silently when
# the bind-mount is absent so existing deployments stay backwards-compatible.
#
# See: docs/workspace.md and ADR-035 for the contract this implements.

# --- Configuration constants ---------------------------------------------
readonly INJECT_MOUNT="/etc/agentic/workspace"
readonly INJECT_MOUNT_PLUGINS="${INJECT_MOUNT}/plugins"
readonly INJECT_MOUNT_AGENTS="${INJECT_MOUNT}/agents"

readonly INJECT_TARGET_CONTEXT="/workspace/CLAUDE.md"
readonly INJECT_TARGET_PLUGINS="/workspace/.agentic-plugins"
readonly INJECT_TARGET_AGENTS="${HOME}/.claude/agents"

readonly INJECT_DEFAULT_CONTEXT="CLAUDE.md"
readonly INJECT_PLUGIN_MANIFEST=".claude-plugin/plugin.json"

# --- Helpers --------------------------------------------------------------
__inject_names() {
    local explicit="$1" dir="$2" strip_ext="${3:-}"
    if [ -n "${explicit}" ]; then
        printf '%s\n' "${explicit}" | tr ':' '\n'
        return
    fi
    [ -d "${dir}" ] || return
    for f in "${dir}"/*${strip_ext}; do
        [ -e "${f}" ] || continue
        local base; base="$(basename "${f}")"
        [ -n "${strip_ext}" ] && base="${base%${strip_ext}}"
        printf '%s\n' "${base}"
    done
}

# --- Actions --------------------------------------------------------------
if [ -d "${INJECT_MOUNT}" ]; then
    ctx_src="${INJECT_MOUNT}/${AGENTIC_WORKSPACE_CONTEXT:-${INJECT_DEFAULT_CONTEXT}}"
    if [ -f "${ctx_src}" ]; then
        cp "${ctx_src}" "${INJECT_TARGET_CONTEXT}"
        chmod 644 "${INJECT_TARGET_CONTEXT}"
    fi

    if [ -d "${INJECT_MOUNT_PLUGINS}" ]; then
        mkdir -p "${INJECT_TARGET_PLUGINS}"
        while IFS= read -r plugin; do
            [ -n "${plugin}" ] || continue
            src="${INJECT_MOUNT_PLUGINS}/${plugin}"
            [ -f "${src}/${INJECT_PLUGIN_MANIFEST}" ] || continue
            cp -a "${src}" "${INJECT_TARGET_PLUGINS}/${plugin}"
            AGENTIC_PLUGIN_FLAGS="${AGENTIC_PLUGIN_FLAGS} --plugin-dir ${INJECT_TARGET_PLUGINS}/${plugin}"
        done < <(__inject_names "${AGENTIC_WORKSPACE_PLUGINS:-}" "${INJECT_MOUNT_PLUGINS}")
        export AGENTIC_PLUGIN_FLAGS
    fi

    if [ -d "${INJECT_MOUNT_AGENTS}" ]; then
        mkdir -p "${INJECT_TARGET_AGENTS}"
        while IFS= read -r agent; do
            [ -n "${agent}" ] || continue
            src="${INJECT_MOUNT_AGENTS}/${agent}.md"
            [ -f "${src}" ] || continue
            cp "${src}" "${INJECT_TARGET_AGENTS}/${agent}.md"
        done < <(__inject_names "${AGENTIC_WORKSPACE_AGENTS:-}" "${INJECT_MOUNT_AGENTS}" ".md")
    fi
fi

# -----------------------------------------------------------------------------
# 6. Execute CMD
# -----------------------------------------------------------------------------
# Pass through to the original command (e.g., bash, claude, etc.)

exec "$@"

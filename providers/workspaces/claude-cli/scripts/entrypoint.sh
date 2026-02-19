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

# Install observability git hooks globally.
# Points core.hooksPath to the baked-in hook scripts so post-commit, pre-push,
# etc. fire for every repo in this container and emit JSONL to stderr.
# The hooks dir is persistent (baked into image) and scripts are already chmod 755.
GIT_HOOKS_DIR="${AGENTIC_PLUGINS_DIR:-/opt/agentic/plugins}/observability/hooks/git"
if [ -d "${GIT_HOOKS_DIR}" ]; then
    git config --global core.hooksPath "${GIT_HOOKS_DIR}"
    echo "[entrypoint] Git observability hooks installed from ${GIT_HOOKS_DIR}"
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
# 6. Execute CMD
# -----------------------------------------------------------------------------
# Pass through to the original command (e.g., bash, claude, etc.)

exec "$@"

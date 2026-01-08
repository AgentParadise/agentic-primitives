#!/bin/bash
# =============================================================================
# Agentic Workspace Entrypoint
# =============================================================================
#
# This script runs when the container starts (AFTER any tmpfs mounts).
# It configures the workspace from environment variables, then execs to CMD.
#
# Environment Variables (provided by orchestrator):
#   GIT_AUTHOR_NAME     - Git commit author name (required for git ops)
#   GIT_AUTHOR_EMAIL    - Git commit author email (required for git ops)
#   GITHUB_TOKEN        - GitHub token for git push (optional)
#   ANTHROPIC_API_KEY   - Claude API key (optional, may come via sidecar)
#
# This script is the SINGLE SOURCE OF TRUTH for workspace configuration.
# Orchestrators should NOT have hardcoded setup scripts.
#
# See: agentic-primitives/docs/workspace-contract.md
# =============================================================================

set -e

# -----------------------------------------------------------------------------
# 1. Claude CLI Configuration
# -----------------------------------------------------------------------------
# Create ~/.claude/settings.json with attribution disabled.
# This must be done HERE because /home/agent is a tmpfs mount that wipes
# anything baked into the Docker image.

mkdir -p ~/.claude

cat > ~/.claude/settings.json << 'EOF'
{
  "attribution": {
    "commit": "",
    "pr": ""
  },
  "hooks": {
    "PreToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "/opt/agentic/hooks/handlers/pre-tool-use.py",
        "timeout": 10
      }]
    }],
    "PostToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "/opt/agentic/hooks/handlers/post-tool-use.py",
        "timeout": 10
      }]
    }],
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "/opt/agentic/hooks/handlers/session-start.py",
        "timeout": 5
      }]
    }],
    "SessionEnd": [{
      "hooks": [{
        "type": "command",
        "command": "/opt/agentic/hooks/handlers/session-end.py",
        "timeout": 5
      }]
    }],
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "/opt/agentic/hooks/handlers/stop.py",
        "timeout": 5
      }]
    }],
    "SubagentStop": [{
      "hooks": [{
        "type": "command",
        "command": "/opt/agentic/hooks/handlers/subagent-stop.py",
        "timeout": 5
      }]
    }]
  }
}
EOF

chmod 600 ~/.claude/settings.json

# -----------------------------------------------------------------------------
# 2. Git Configuration
# -----------------------------------------------------------------------------
# Configure git identity from environment variables.
# These are required for any git commit/push operations.

if [ -n "${GIT_AUTHOR_NAME}" ]; then
    git config --global user.name "${GIT_AUTHOR_NAME}"
    git config --global user.email "${GIT_AUTHOR_EMAIL:-agent@agentic.local}"
    git config --global init.defaultBranch main
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
# 3. GitHub Credentials
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
# 4. Workspace Directories
# -----------------------------------------------------------------------------
# Ensure workspace directories exist (should be pre-created in image,
# but verify in case of custom mounts)

mkdir -p /workspace/artifacts/input
mkdir -p /workspace/artifacts/output
mkdir -p /workspace/repos

# -----------------------------------------------------------------------------
# 5. Execute CMD
# -----------------------------------------------------------------------------
# Pass through to the original command (e.g., bash, claude, etc.)

exec "$@"

#!/usr/bin/env bash
# Interactive-tmux workspace entrypoint.
#
# Intentionally minimal compared to providers/workspaces/claude-cli's
# entrypoint. The interactive provider's lifecycle is host-driven; the
# host driver orchestrates tmux sessions and CLI startup via
# `docker exec`. The entrypoint's only job is to:
#
#   1. Ensure writable workspace directories exist.
#   2. Set git committer identity if the orchestrator provided one.
#   3. Stay out of the way of mounted ~/.claude, ~/.codex, ~/.gemini —
#      this entrypoint MUST NOT write to those locations (key fix for
#      EXP-01 FRICTION F-2: the claude-cli entrypoint clobbers
#      ~/.claude/settings.json on every start, defeating mounted prefs).
#   4. exec to CMD (default: sleep infinity), holding the container open
#      for `docker exec` from the host driver.

set -e

# 1. Writable workspace dirs (same convention as claude-cli)
mkdir -p /workspace/artifacts/input
mkdir -p /workspace/artifacts/output
mkdir -p /workspace/repos

# 2. Optional git committer identity (passed from orchestrator)
if [ -n "${GIT_AUTHOR_NAME:-}" ]; then
    git config --global user.name "${GIT_AUTHOR_NAME}"
fi
if [ -n "${GIT_AUTHOR_EMAIL:-}" ]; then
    git config --global user.email "${GIT_AUTHOR_EMAIL}"
fi
if [ -n "${GIT_COMMITTER_NAME:-}" ]; then
    export GIT_COMMITTER_NAME
    export GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-${GIT_AUTHOR_EMAIL:-agent@agentic.local}}"
fi

# 3. (no writes to ~/.claude, ~/.codex, ~/.gemini — driver handles those
#     entirely from the host side via docker cp + bind mounts)

# 4. exec to CMD
exec "$@"

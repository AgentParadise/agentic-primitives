#!/bin/bash
# Install git hooks for observability
#
# Usage:
#   ./install.sh          # Install to current repo's .git/hooks/
#   ./install.sh --global # Install globally for all repos
#   ./install.sh --uninstall # Remove installed hooks
#
# The hooks emit JSONL events to .agentic/analytics/events.jsonl
# for tracking git operations (commits, branches, merges, etc.)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOKS="post-commit post-checkout post-merge post-rewrite pre-push"

show_help() {
  cat << EOF
Git Observability Hooks Installer

Usage:
  $(basename "$0") [options]

Options:
  --global      Install hooks globally (all repos)
  --uninstall   Remove installed hooks
  --help        Show this help message

Examples:
  # Install to current repository
  ./install.sh

  # Install globally for all git operations
  ./install.sh --global

  # Remove hooks from current repository
  ./install.sh --uninstall

Hooks installed:
  post-commit     - Track commits with token metrics
  post-checkout   - Track branch switches and creation
  post-merge      - Track merges, especially to stable branches
  post-rewrite    - Track rebases and amends
  pre-push        - Track push operations

Events are written to: \$ANALYTICS_PATH or .agentic/analytics/events.jsonl
EOF
}

uninstall_hooks() {
  local target_dir="$1"
  echo "Uninstalling hooks from $target_dir"

  for hook in $HOOKS; do
    local dst="$target_dir/$hook"
    if [[ -f "$dst" ]]; then
      # Check if it's our hook (has the analytics marker)
      if grep -q "ANALYTICS_PATH" "$dst" 2>/dev/null; then
        rm "$dst"
        echo "  Removed $hook"
      else
        echo "  Skipped $hook (not our hook)"
      fi
    fi
    # Restore backup if exists
    if [[ -f "$dst.bak" ]]; then
      mv "$dst.bak" "$dst"
      echo "  Restored $hook from backup"
    fi
  done

  echo "Done!"
}

install_hooks() {
  local target_dir="$1"
  echo "Installing hooks to $target_dir"

  for hook in $HOOKS; do
    local src="$SCRIPT_DIR/$hook"
    local dst="$target_dir/$hook"

    if [[ ! -f "$src" ]]; then
      echo "  Warning: $src not found, skipping"
      continue
    fi

    # Backup existing hook if it's not ours
    if [[ -f "$dst" ]] && [[ ! -L "$dst" ]]; then
      if ! grep -q "ANALYTICS_PATH" "$dst" 2>/dev/null; then
        echo "  Backing up existing $hook to $hook.bak"
        mv "$dst" "$dst.bak"
      fi
    fi

    cp "$src" "$dst"
    chmod +x "$dst"
    echo "  Installed $hook"
  done

  echo "Done! Git hooks installed."
  echo ""
  echo "Events will be written to: \$ANALYTICS_PATH or .agentic/analytics/events.jsonl"
}

# Parse arguments
GLOBAL=false
UNINSTALL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --global)
      GLOBAL=true
      shift
      ;;
    --uninstall)
      UNINSTALL=true
      shift
      ;;
    --help|-h)
      show_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      show_help
      exit 1
      ;;
  esac
done

# Determine target directory
if [[ "$GLOBAL" == "true" ]]; then
  TARGET_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/git/hooks"
  mkdir -p "$TARGET_DIR"

  if [[ "$UNINSTALL" == "true" ]]; then
    uninstall_hooks "$TARGET_DIR"
    git config --global --unset core.hooksPath 2>/dev/null || true
    echo "Removed global hooks path configuration"
  else
    install_hooks "$TARGET_DIR"
    git config --global core.hooksPath "$TARGET_DIR"
    echo "Configured global hooks path: $TARGET_DIR"
  fi
else
  # Find git directory
  GIT_DIR=$(git rev-parse --git-dir 2>/dev/null || echo "")

  if [[ -z "$GIT_DIR" ]]; then
    echo "Error: Not in a git repository"
    exit 1
  fi

  TARGET_DIR="$GIT_DIR/hooks"

  if [[ "$UNINSTALL" == "true" ]]; then
    uninstall_hooks "$TARGET_DIR"
  else
    install_hooks "$TARGET_DIR"
  fi
fi

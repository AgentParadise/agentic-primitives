#!/usr/bin/env bash
# first-run.sh — SessionStart hook: nudge user to configure push notifications
# Runs every session start. Silent when already configured. Always exits 0.

# macOS has native notifications out of the box — no setup needed
if command -v osascript &>/dev/null; then
  exit 0
fi

# If ntfy is configured, nothing to do
if [[ -n "${NTFY_TOPIC:-}" ]]; then
  exit 0
fi

# If pushover is configured, nothing to do
if [[ -n "${PUSHOVER_TOKEN:-}" && -n "${PUSHOVER_USER:-}" ]]; then
  exit 0
fi

# Not configured — emit a gentle nudge
PLUGIN_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
echo "🔔 Push notifications not configured yet. Run the setup wizard: ${PLUGIN_DIR}/setup.sh"

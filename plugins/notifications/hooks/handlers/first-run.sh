#!/usr/bin/env bash
# first-run.sh — SessionStart hook: onboarding status on first run
# Runs every session start. Silent when fully configured. Always exits 0.

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

# Detect capabilities
HAS_MACOS=false
HAS_NTFY=false
HAS_PUSHOVER=false

command -v osascript &>/dev/null && HAS_MACOS=true
[[ -n "${NTFY_TOPIC:-}" ]] && HAS_NTFY=true
[[ -n "${PUSHOVER_TOKEN:-}" && -n "${PUSHOVER_USER:-}" ]] && HAS_PUSHOVER=true

# If any push provider is configured, stay silent (fully set up)
if $HAS_NTFY || $HAS_PUSHOVER; then
  exit 0
fi

# If macOS only (no push), nudge for mobile push
if $HAS_MACOS; then
  echo "🔔 Notifications plugin active"
  echo "  ✅ macOS desktop notifications: enabled"
  echo "  ⚠️  Mobile push: not configured"
  echo "  → Run: ${PLUGIN_DIR}/setup.sh (30 seconds, optional)"
  exit 0
fi

# Nothing configured at all (Linux/remote)
echo "🔔 Notifications plugin installed — needs setup"
echo "  ⚠️  No notification providers configured"
echo "  → Run: ${PLUGIN_DIR}/setup.sh (30 seconds)"
echo "  This will set up push notifications to your phone via ntfy.sh"

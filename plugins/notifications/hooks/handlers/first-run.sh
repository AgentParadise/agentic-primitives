#!/usr/bin/env bash
# first-run.sh — SessionStart hook: onboarding prompt on first run
# Runs every session start. Silent when fully configured. Always exits 0.
# Output is added to Claude's context — Claude will naturally inform the user.

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

# Detect capabilities
HAS_MACOS=false
HAS_NTFY=false
HAS_PUSHOVER=false

command -v osascript &>/dev/null && HAS_MACOS=true
[[ -n "${NTFY_TOPIC:-}" ]] && HAS_NTFY=true
[[ -n "${PUSHOVER_TOKEN:-}" && -n "${PUSHOVER_USER:-}" ]] && HAS_PUSHOVER=true

# Fully configured — stay completely silent
if $HAS_NTFY || $HAS_PUSHOVER; then
  exit 0
fi

# Output JSON so Claude gets structured context
if $HAS_MACOS; then
  cat <<EOF
{"notification_plugin_status": {"macos": true, "push": false, "setup_command": "${PLUGIN_DIR}/setup.sh", "message": "The notifications plugin is active. macOS desktop notifications work automatically. Mobile push notifications are not configured yet — the user can optionally run the setup wizard to enable phone notifications via ntfy.sh. Briefly mention this to the user if relevant."}}
EOF
else
  cat <<EOF
{"notification_plugin_status": {"macos": false, "push": false, "setup_command": "${PLUGIN_DIR}/setup.sh", "message": "The notifications plugin is installed but no notification providers are configured. The user should run the setup wizard to enable push notifications to their phone via ntfy.sh. Let the user know about this."}}
EOF
fi

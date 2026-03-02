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
  cat <<'EOF'
{"notifications":{"status":"partial","macos":true,"push":false,"message":"Run /notifications:configure to set up mobile push"}}
EOF
  exit 0
fi

# Nothing configured at all (Linux/remote)
cat <<'EOF'
{"notifications":{"status":"unconfigured","macos":false,"push":false,"message":"Run /notifications:configure to set up notifications"}}
EOF

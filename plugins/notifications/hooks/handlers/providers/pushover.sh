#!/usr/bin/env bash
# pushover.sh — push notification via Pushover API
set -euo pipefail

HOOK_TYPE="${1:-Notification}"
SUMMARY="${2:-Claude Code}"
FORMATTED="${3:-$SUMMARY}"

# Map hook type to priority (-1=low, 0=normal, 1=high)
PRIORITY="0"
case "$HOOK_TYPE" in
  Notification) PRIORITY="1" ;;
  Stop|TaskCompleted) PRIORITY="0" ;;
esac

curl -sf --max-time 4 \
  --form-string "token=${PUSHOVER_TOKEN}" \
  --form-string "user=${PUSHOVER_USER}" \
  --form-string "title=Claude Code — ${HOOK_TYPE}" \
  --form-string "message=${FORMATTED}" \
  --form-string "priority=${PRIORITY}" \
  https://api.pushover.net/1/messages.json >/dev/null 2>&1 || true

#!/usr/bin/env bash
# ntfy.sh — push notification via ntfy.sh (or self-hosted ntfy)
set -euo pipefail

HOOK_TYPE="${1:-Notification}"
SUMMARY="${2:-Claude Code}"
FORMATTED="${3:-$SUMMARY}"

NTFY_SERVER="${NTFY_SERVER:-https://ntfy.sh}"

# Map hook type to priority
PRIORITY="default"
case "$HOOK_TYPE" in
  Notification) PRIORITY="high" ;;
  Stop|TaskCompleted) PRIORITY="default" ;;
esac

# Map hook type to tags
TAGS=""
case "$HOOK_TYPE" in
  Notification) TAGS="warning,claude" ;;
  Stop) TAGS="white_check_mark,claude" ;;
  TaskCompleted) TAGS="tada,claude" ;;
esac

curl -sf \
  -H "Title: Claude Code — ${HOOK_TYPE}" \
  -H "Priority: ${PRIORITY}" \
  -H "Tags: ${TAGS}" \
  -d "$FORMATTED" \
  "${NTFY_SERVER}/${NTFY_TOPIC}" >/dev/null 2>&1 || true

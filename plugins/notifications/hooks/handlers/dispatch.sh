#!/usr/bin/env bash
# dispatch.sh — reads hook JSON from stdin, formats a message, calls active providers
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROVIDERS_DIR="${SCRIPT_DIR}/providers"

# --- Read JSON from stdin ---
INPUT="$(cat)"

# --- Extract fields via lightweight JSON parsing (no jq dependency) ---
# Claude Code hook JSON has: hook_type, session_id, and event-specific fields
extract_json_string() {
  local key="$1"
  echo "$INPUT" | grep -o "\"${key}\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" | head -1 | sed "s/\"${key}\"[[:space:]]*:[[:space:]]*\"//" | sed 's/"$//'
}

HOOK_TYPE="$(extract_json_string "hook_type")"
SESSION_ID="$(extract_json_string "session_id")"

# --- Determine emoji and summary ---
MACHINE="${CLAUDE_NOTIFY_MACHINE:-$(hostname)}"
EMOJI=""
SUMMARY=""

# --- Determine notification type for per-event sounds ---
NOTIFY_TYPE=""

case "$HOOK_TYPE" in
  Notification)
    EMOJI="🟡"
    # Try to extract the notification message and type
    TITLE="$(extract_json_string "title")"
    MESSAGE="$(extract_json_string "message")"
    NOTIFICATION_TYPE="$(extract_json_string "notification_type")"
    if [[ -n "$TITLE" && -n "$MESSAGE" ]]; then
      SUMMARY="${TITLE}: ${MESSAGE}"
    elif [[ -n "$MESSAGE" ]]; then
      SUMMARY="$MESSAGE"
    elif [[ -n "$TITLE" ]]; then
      SUMMARY="$TITLE"
    else
      SUMMARY="Needs attention"
    fi
    # Classify notification sub-type
    case "$NOTIFICATION_TYPE" in
      idle_prompt)    NOTIFY_TYPE="idle" ;;
      permission_prompt) NOTIFY_TYPE="permission" ;;
      *)              NOTIFY_TYPE="idle" ;;
    esac
    ;;
  Stop)
    EMOJI="🟢"
    SUMMARY="Session stopped"
    NOTIFY_TYPE="complete"
    ;;
  TaskCompleted)
    EMOJI="🟢"
    SUMMARY="Task completed"
    NOTIFY_TYPE="complete"
    ;;
  *)
    EMOJI="🔵"
    SUMMARY="Event: ${HOOK_TYPE:-unknown}"
    NOTIFY_TYPE="complete"
    ;;
esac

# --- Format message ---
FORMATTED="${MACHINE}: ${EMOJI} ${HOOK_TYPE} — ${SUMMARY}"

# --- Dispatch to active providers ---

# macOS native notifications (auto-detect)
if command -v osascript &>/dev/null; then
  "$PROVIDERS_DIR/macos.sh" "$HOOK_TYPE" "$SUMMARY" "$FORMATTED" "$NOTIFY_TYPE" &
fi

# ntfy (if topic configured)
if [[ -n "${NTFY_TOPIC:-}" ]]; then
  "$PROVIDERS_DIR/ntfy.sh" "$HOOK_TYPE" "$SUMMARY" "$FORMATTED" &
fi

# pushover (if both token and user configured)
if [[ -n "${PUSHOVER_TOKEN:-}" && -n "${PUSHOVER_USER:-}" ]]; then
  "$PROVIDERS_DIR/pushover.sh" "$HOOK_TYPE" "$SUMMARY" "$FORMATTED" &
fi

# Wait for all background providers (within hook timeout)
wait

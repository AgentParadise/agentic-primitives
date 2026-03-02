#!/usr/bin/env bash
# macos.sh — native macOS notification via osascript
set -euo pipefail

HOOK_TYPE="${1:-Notification}"
SUMMARY="${2:-Claude Code}"
FORMATTED="${3:-$SUMMARY}"
NOTIFY_TYPE="${4:-idle}"

# --- Sound theme resolver ---
# Priority: per-event env var > theme > global sound > built-in default
_theme_sound() {
  local theme="${CLAUDE_NOTIFY_THEME:-}"
  local type="$1"
  case "$theme" in
    default)  case "$type" in idle) echo Ping;; permission) echo Basso;; complete) echo Glass;; esac ;;
    ocean)    case "$type" in idle) echo Blow;; permission) echo Sonar;; complete) echo Submarine;; esac ;;
    minimal)  case "$type" in idle) echo Tink;; permission) echo Pop;; complete) echo Purr;; esac ;;
    alert)    case "$type" in idle) echo Hero;; permission) echo Sosumi;; complete) echo Fanfare;; esac ;;
    *)        ;; # unknown or unset — fall through
  esac
}

_resolve_sound() {
  local type="$1"
  local default="$2"
  local per_event=""
  case "$type" in
    idle)       per_event="${CLAUDE_NOTIFY_SOUND_IDLE:-}" ;;
    permission) per_event="${CLAUDE_NOTIFY_SOUND_PERMISSION:-}" ;;
    complete)   per_event="${CLAUDE_NOTIFY_SOUND_COMPLETE:-}" ;;
  esac

  # 1. Per-event override
  if [[ -n "$per_event" ]]; then echo "$per_event"; return; fi
  # 2. Theme
  local themed; themed="$(_theme_sound "$type")"
  if [[ -n "$themed" ]]; then echo "$themed"; return; fi
  # 3. Global sound
  if [[ -n "${CLAUDE_NOTIFY_SOUND:-}" ]]; then echo "$CLAUDE_NOTIFY_SOUND"; return; fi
  # 4. Built-in default
  echo "$default"
}

case "$NOTIFY_TYPE" in
  idle)       SOUND="$(_resolve_sound idle Ping)" ;;
  permission) SOUND="$(_resolve_sound permission Basso)" ;;
  complete)   SOUND="$(_resolve_sound complete Glass)" ;;
  *)          SOUND="${CLAUDE_NOTIFY_SOUND:-Ping}" ;;
esac

osascript - "$SUMMARY" "$HOOK_TYPE" "$SOUND" <<'APPLESCRIPT'
on run argv
  set summary to item 1 of argv
  set hookType to item 2 of argv
  set soundName to item 3 of argv
  display notification summary with title "Claude Code" subtitle hookType sound name soundName
end run
APPLESCRIPT

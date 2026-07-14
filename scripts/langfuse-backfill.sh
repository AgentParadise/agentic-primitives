#!/usr/bin/env bash
set -euo pipefail

HARNESS="all"
LIMIT=10
MAX_TURNS=100
ORDER="newest"
APPLY=false

usage() {
  cat <<'EOF'
Usage: scripts/langfuse-backfill.sh [options]

Backfill existing local Claude Code and Codex JSONL transcripts through the
official LangFuse plugins. Preview is the default; --apply is required to
submit traces.

Options:
  --harness claude|codex|all  Harnesses to process (default: all)
  --limit N                   Source files per harness; 0 means all (default: 10)
  --max-turns N               Estimated turns per harness batch; 0 is unlimited (default: 100)
  --oldest|--newest           Process oldest or newest files first (default: newest)
  --apply                     Submit the selected source files
  -h, --help                  Show this help

Codex uses the official plugin's <rollout>.langfuse dedup ledger. Claude uses
the official plugin's per-transcript offset state. A manifest is appended to
~/.local/state/agentic-primitives/langfuse-backfill.jsonl after each accepted
source file. Do not delete either state store unless an intentional reimport is
required.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --harness)
      HARNESS="${2:-}"
      shift
      ;;
    --limit)
      LIMIT="${2:-}"
      shift
      ;;
    --max-turns)
      MAX_TURNS="${2:-}"
      shift
      ;;
    --oldest)
      ORDER="oldest"
      ;;
    --newest)
      ORDER="newest"
      ;;
    --apply)
      APPLY=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
  shift
done

case "$HARNESS" in claude|codex|all) ;; *) echo "invalid --harness: $HARNESS" >&2; exit 2;; esac
case "$LIMIT" in ''|*[!0-9]*) echo "--limit must be a non-negative integer" >&2; exit 2;; esac
case "$MAX_TURNS" in ''|*[!0-9]*) echo "--max-turns must be a non-negative integer" >&2; exit 2;; esac

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/agentic-primitives"
MANIFEST="$STATE_DIR/langfuse-backfill.jsonl"
CODEX_CONFIG="$HOME/.codex/langfuse.json"

mtime() {
  if [ "$(uname -s)" = "Darwin" ]; then
    stat -f '%m' "$1"
  else
    stat -c '%Y' "$1"
  fi
}

codex_is_exportable() {
  local file="$1"
  [ ! -f "${file}.langfuse" ] \
    && jq -se 'any(.[]; .type == "session_meta") and any(.[]; .type == "event_msg" and .payload.type == "task_started")' "$file" >/dev/null 2>&1
}

claude_state_key_for_file() {
  local file="$1"
  local session_id
  session_id="$(session_id_for_claude "$file")"
  [ -n "$session_id" ] || return 1
  if command -v shasum >/dev/null 2>&1; then
    printf '%s' "${session_id}::${file}" | shasum -a 256 | awk '{print $1}'
  else
    printf '%s' "${session_id}::${file}" | sha256sum | awk '{print $1}'
  fi
}

claude_is_pending() {
  local file="$1"
  local state_key
  state_key="$(claude_state_key_for_file "$file")" || return 1
  [ ! -f "$HOME/.claude/state/langfuse_state.json" ] \
    || ! jq -e --arg key "$state_key" 'has($key)' "$HOME/.claude/state/langfuse_state.json" >/dev/null
}

list_transcripts() {
  local harness="$1"
  local root
  case "$harness" in
    codex) root="$HOME/.codex/sessions" ;;
    claude) root="$HOME/.claude/projects" ;;
  esac
  [ -d "$root" ] || return 0
  while IFS= read -r -d '' file; do
    case "$harness" in
      codex) codex_is_exportable "$file" || continue ;;
      claude) claude_is_pending "$file" || continue ;;
    esac
    printf '%s\t%s\n' "$(mtime "$file")" "$file"
  done < <(
    if [ "$harness" = "claude" ]; then
      find "$root" -type d -name subagents -prune -o -type f -name '*.jsonl' -print0
    else
      find "$root" -type f -name '*.jsonl' -print0
    fi
  )
}

selected_files() {
  local harness="$1"
  local sort_flag='-nr'
  [ "$ORDER" = "oldest" ] && sort_flag='-n'
  if [ "$LIMIT" -eq 0 ]; then
    list_transcripts "$harness" | sort "$sort_flag" | cut -f2-
  else
    list_transcripts "$harness" | sort "$sort_flag" | head -n "$LIMIT" | cut -f2-
  fi
}

require_codex_plugin() {
  CODEX_ENTRY="$(ls -1 "$HOME"/.codex/plugins/cache/codex-observability-plugin/tracing/*/dist/index.mjs 2>/dev/null | sort | tail -1)"
  if [ -z "$CODEX_ENTRY" ]; then
    echo 'Codex LangFuse plugin entrypoint is not installed.' >&2
    exit 1
  fi
  [ -f "$CODEX_CONFIG" ] || { echo "missing $CODEX_CONFIG" >&2; exit 1; }
}

configure_claude_environment() {
  CLAUDE_HOOK="$(ls -1 "$HOME"/.claude/plugins/cache/langfuse-observability/langfuse-observability/*/hooks/langfuse_hook.py 2>/dev/null | sort | tail -1)"
  if [ -z "$CLAUDE_HOOK" ]; then
    echo 'Claude LangFuse plugin hook is not installed.' >&2
    exit 1
  fi

  if [ -f "$CODEX_CONFIG" ]; then
    export LANGFUSE_BASE_URL="${LANGFUSE_BASE_URL:-$(jq -r '.base_url // empty' "$CODEX_CONFIG")}" 
    export LANGFUSE_PUBLIC_KEY="${LANGFUSE_PUBLIC_KEY:-$(jq -r '.public_key // empty' "$CODEX_CONFIG")}" 
    export LANGFUSE_SECRET_KEY="${LANGFUSE_SECRET_KEY:-$(jq -r '.secret_key // empty' "$CODEX_CONFIG")}" 
    export LANGFUSE_USER_ID="${LANGFUSE_USER_ID:-$(jq -r '.user_id // empty' "$CODEX_CONFIG")}" 
    export LANGFUSE_TRACING_ENVIRONMENT="${LANGFUSE_TRACING_ENVIRONMENT:-$(jq -r '.environment // empty' "$CODEX_CONFIG")}" 
    host_tag="$(jq -r '.tags[]? | select(startswith("host:"))' "$CODEX_CONFIG" | head -1)"
    export CC_LANGFUSE_TAGS="${CC_LANGFUSE_TAGS:-harness:claude${host_tag:+,$host_tag}}"
  fi

  for required in LANGFUSE_BASE_URL LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY; do
    [ -n "${!required:-}" ] || { echo "missing $required for Claude backfill" >&2; exit 1; }
  done
}

session_id_for_claude() {
  local file="$1"
  jq -r 'select(.sessionId? != null) | .sessionId' "$file" 2>/dev/null | head -1
}

record_manifest() {
  local harness="$1"
  local file="$2"
  local status="${3:-submitted}"
  mkdir -p "$STATE_DIR"
  chmod 700 "$STATE_DIR"
  jq -cn --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg harness "$harness" --arg path "$file" --arg status "$status" \
    '{timestamp:$timestamp, harness:$harness, source_path:$path, status:$status}' >> "$MANIFEST"
  chmod 600 "$MANIFEST"
}

backfill_codex() {
  local file="$1"
  if ! codex_is_exportable "$file"; then
    printf 'skip unsupported Codex rollout schema: %s\n' "$file"
    return 10
  fi
  jq -cn --arg transcript_path "$file" '{transcript_path:$transcript_path}' | node "$CODEX_ENTRY"
}

estimated_turns() {
  local harness="$1"
  local file="$2"
  case "$harness" in
    codex)
      jq -r 'select(.type == "event_msg" and .payload.type == "task_started") | 1' "$file" 2>/dev/null | wc -l | tr -d ' '
      ;;
    claude)
      jq -r 'select(.type == "user") | 1' "$file" 2>/dev/null | wc -l | tr -d ' '
      ;;
  esac
}

backfill_claude() {
  local file="$1"
  local session_id
  session_id="$(session_id_for_claude "$file")"
  if [ -z "$session_id" ]; then
    echo "skip Claude transcript without sessionId: $file" >&2
    return 10
  fi
  if ! claude_is_pending "$file"; then
    printf 'skip already-recorded Claude transcript: %s\n' "$file"
    return 10
  fi
  jq -cn --arg session_id "$session_id" --arg transcript_path "$file" \
    '{hook_event_name:"Stop", session_id:$session_id, transcript_path:$transcript_path}' \
    | uv run --quiet --script "$CLAUDE_HOOK"
}

run_harness() {
  local harness="$1"
  local file
  local count=0
  local failures=0
  local skipped=0
  local estimated=0
  local exit_code
  local turns
  local -a files=()
  while IFS= read -r file; do files+=("$file"); done < <(selected_files "$harness")

  printf '%s: selected %d transcript(s), order=%s, apply=%s\n' "$harness" "${#files[@]}" "$ORDER" "$APPLY"
  for file in "${files[@]}"; do
    if [ "$APPLY" = false ]; then
      printf '  %s\n' "$file"
      continue
    fi
    turns="$(estimated_turns "$harness" "$file")"
    if [ "$MAX_TURNS" -ne 0 ] && [ "$estimated" -gt 0 ] && [ $((estimated + turns)) -gt "$MAX_TURNS" ]; then
      printf 'skip turn budget (%s + %s > %s): %s\n' "$estimated" "$turns" "$MAX_TURNS" "$file"
      skipped=$((skipped + 1))
      continue
    fi
    printf '[%s] %s\n' "$harness" "$file"
    if "backfill_$harness" "$file"; then
      if record_manifest "$harness" "$file"; then
        count=$((count + 1))
        estimated=$((estimated + turns))
      else
        printf 'could not record submission manifest: %s\n' "$file" >&2
        failures=$((failures + 1))
      fi
    else
      exit_code=$?
      if [ "$exit_code" -eq 10 ]; then
        skipped=$((skipped + 1))
      else
        printf 'backfill failed: %s\n' "$file" >&2
        failures=$((failures + 1))
      fi
    fi
  done
  printf '%s: submitted=%d estimated_turns=%d skipped=%d failures=%d\n' "$harness" "$count" "$estimated" "$skipped" "$failures"
  [ "$failures" -eq 0 ]
}

if [ "$HARNESS" = "codex" ] || [ "$HARNESS" = "all" ]; then require_codex_plugin; fi
if [ "$HARNESS" = "claude" ] || [ "$HARNESS" = "all" ]; then configure_claude_environment; fi

status=0
if [ "$HARNESS" = "codex" ] || [ "$HARNESS" = "all" ]; then run_harness codex || status=1; fi
if [ "$HARNESS" = "claude" ] || [ "$HARNESS" = "all" ]; then run_harness claude || status=1; fi
exit "$status"

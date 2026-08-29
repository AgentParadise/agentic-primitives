#!/usr/bin/env bash
set -euo pipefail

# Re-import only fully gpt-5.5 Codex rollouts after the LangFuse usage-bucket
# correction. LangFuse calculates price during ingestion, so existing traces
# cannot be repriced in place.

LIMIT=10
APPLY=false
CONFIRM=false

usage() {
  cat <<'EOF'
Usage: scripts/langfuse-repair-codex-costs.sh [--limit N] [--apply --confirm]

Preview Codex gpt-5.5 rollouts whose LangFuse traces were created before the
usage-bucket correction. Preview is the default. Applying the repair:

  1. saves each local Codex .langfuse dedup ledger under
     ~/.local/state/agentic-primitives/langfuse-cost-repair/;
  2. deletes the matching remote LangFuse trace(s); and
  3. replays the original rollout through the installed Codex plugin.

Only a rollout whose every recorded model is exactly gpt-5.5 is eligible.
Mixed-model sessions and gpt-5.3-codex-spark are intentionally excluded.
Use --apply --confirm to make changes.

Required environment:
  LANGFUSE_BASE_URL
  LANGFUSE_PUBLIC_KEY
  LANGFUSE_SECRET_KEY
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --limit) LIMIT="${2:-}"; shift ;;
    --apply) APPLY=true ;;
    --confirm) CONFIRM=true ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done

case "$LIMIT" in ''|*[!0-9]*) echo '--limit must be a non-negative integer' >&2; exit 2;; esac
if [ "$APPLY" = true ] && [ "$CONFIRM" = false ]; then
  echo '--apply requires --confirm because it deletes and re-ingests remote traces.' >&2
  exit 2
fi

for required in LANGFUSE_BASE_URL LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY; do
  [ -n "${!required:-}" ] || { echo "missing $required" >&2; exit 1; }
done
for command in curl jq node rg; do
  command -v "$command" >/dev/null 2>&1 || { echo "$command is required" >&2; exit 1; }
done

BASE_URL="${LANGFUSE_BASE_URL%/}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/agentic-primitives/langfuse-cost-repair"
MANIFEST="$STATE_DIR/manifest.jsonl"
CODEX_ROOT="$HOME/.codex/sessions"
CODEX_ENTRY="$(ls -1 "$HOME"/.codex/plugins/cache/codex-observability-plugin/tracing/*/dist/index.mjs 2>/dev/null | sort | tail -1)"

[ -n "$CODEX_ENTRY" ] || { echo 'Codex LangFuse plugin entrypoint is not installed.' >&2; exit 1; }
[ -d "$CODEX_ROOT" ] || { echo "Codex session directory does not exist: $CODEX_ROOT" >&2; exit 1; }
rg -q 'Math\.max\(usage\.input_tokens - cachedInputTokens, 0\)' "$CODEX_ENTRY" \
  && rg -q 'output_reasoning_tokens' "$CODEX_ENTRY" \
  || { echo 'Installed Codex plugin does not contain the verified usage-bucket correction.' >&2; exit 1; }

# A remote model definition is required before the script is allowed to delete
# anything. It is the contract that makes the replacement trace useful.
model_exists=false
page=1
while :; do
  response="$(curl -sSf --user "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
    "$BASE_URL/api/public/models?limit=100&page=$page")"
  if printf '%s' "$response" | jq -e '.data[] | select(.modelName == "gpt-5.5")' >/dev/null; then
    model_exists=true
    break
  fi
  [ "$(printf '%s' "$response" | jq -r '.meta.page >= .meta.totalPages')" = true ] && break
  page=$((page + 1))
done
[ "$model_exists" = true ] || { echo 'LangFuse model definition gpt-5.5 is missing; run langfuse-model-pricing.sh --apply first.' >&2; exit 1; }

models_for_file() {
  jq -r 'select(.type == "turn_context") | .payload.model // empty' "$1" | sort -u | paste -sd, -
}

session_for_file() {
  jq -r 'select(.type == "session_meta") | .payload.id // empty' "$1" | head -1
}

eligible_files() {
  find "$CODEX_ROOT" -type f -name '*.jsonl' -print0 | while IFS= read -r -d '' file; do
    [ -f "$file.langfuse" ] || continue
    [ "$(models_for_file "$file")" = 'gpt-5.5' ] || continue
    session_id="$(session_for_file "$file")"
    [ -n "$session_id" ] || continue
    printf '%s\t%s\n' "$session_id" "$file"
  done | sort
}

list_trace_ids() {
  local session_id="$1"
  local page=1
  local response
  while :; do
    response="$(curl -sSf --user "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
      "$BASE_URL/api/public/traces?sessionId=$session_id&limit=100&page=$page")"
    printf '%s' "$response" | jq -r '.data[]?.id'
    [ "$(printf '%s' "$response" | jq -r '.meta.page >= .meta.totalPages')" = true ] && break
    page=$((page + 1))
  done
}

replacement_has_priced_generation() {
  local trace_ids="$1"
  local trace_id
  while IFS= read -r trace_id; do
    [ -n "$trace_id" ] || continue
    curl -sSf --user "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
      "$BASE_URL/api/public/observations?traceId=$trace_id&limit=100&page=1" \
      | jq -e '.data[] | select(.model == "gpt-5.5" and .calculatedTotalCost > 0)' >/dev/null \
      && return 0
  done < <(printf '%s' "$trace_ids" | jq -r '.[]')
  return 1
}

record() {
  local status="$1" file="$2" session_id="$3" trace_ids="$4" backup="${5:-}"
  mkdir -p "$STATE_DIR"
  chmod 700 "$STATE_DIR"
  jq -cn \
    --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg status "$status" --arg source_path "$file" --arg session_id "$session_id" \
    --argjson trace_ids "$trace_ids" --arg backup_path "$backup" \
    '{timestamp:$timestamp,status:$status,source_path:$source_path,session_id:$session_id,trace_ids:$trace_ids,backup_path:$backup_path}' \
    >> "$MANIFEST"
  chmod 600 "$MANIFEST"
}

processed=0
while IFS=$'\t' read -r session_id file; do
  [ -n "$file" ] || continue
  trace_ids="$(list_trace_ids "$session_id" | jq -R . | jq -sc .)"
  trace_count="$(printf '%s' "$trace_ids" | jq 'length')"
  [ "$trace_count" -gt 0 ] || { echo "skip no remote traces: $file"; continue; }

  printf '%s\n' "candidate: session=$session_id traces=$trace_count source=$file"
  if [ "$APPLY" = false ]; then
    processed=$((processed + 1))
    [ "$LIMIT" -gt 0 ] && [ "$processed" -ge "$LIMIT" ] && break
    continue
  fi

  source_hash="$(printf '%s' "$file" | shasum -a 256 | awk '{print $1}')"
  backup_dir="$STATE_DIR/$(date -u +%Y%m%dT%H%M%SZ)-$source_hash"
  mkdir -p "$backup_dir"
  backup="$backup_dir/$(basename "$file").langfuse"
  cp -p "$file.langfuse" "$backup"
  chmod 600 "$backup"
  record 'backup_created' "$file" "$session_id" "$trace_ids" "$backup"

  while IFS= read -r trace_id; do
    [ -n "$trace_id" ] || continue
    curl -sSf --user "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
      -X DELETE "$BASE_URL/api/public/traces/$trace_id" >/dev/null
  done < <(printf '%s' "$trace_ids" | jq -r '.[]')
  record 'remote_deleted' "$file" "$session_id" "$trace_ids" "$backup"

  rm "$file.langfuse"
  jq -cn --arg transcript_path "$file" '{transcript_path:$transcript_path}' | node "$CODEX_ENTRY"
  record 'reimport_submitted' "$file" "$session_id" "$trace_ids" "$backup"

  replacement_ids="$(list_trace_ids "$session_id" | jq -R . | jq -sc .)"
  [ "$(printf '%s' "$replacement_ids" | jq 'length')" -gt 0 ] || {
    echo "replacement trace did not appear for $session_id; ledger backup is at $backup" >&2
    exit 1
  }
  replacement_has_priced_generation "$replacement_ids" || {
    echo "replacement trace has no priced gpt-5.5 generation; ledger backup is at $backup" >&2
    exit 1
  }
  record 'replacement_verified' "$file" "$session_id" "$replacement_ids" "$backup"
  printf '%s\n' "repaired: session=$session_id replacement_traces=$(printf '%s' "$replacement_ids" | jq 'length')"

  processed=$((processed + 1))
  [ "$LIMIT" -gt 0 ] && [ "$processed" -ge "$LIMIT" ] && break
done < <(eligible_files)

[ "$processed" -gt 0 ] || echo 'No eligible historical gpt-5.5 Codex rollouts found.'

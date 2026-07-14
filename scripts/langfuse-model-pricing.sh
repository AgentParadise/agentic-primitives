#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELS_DIR="$ROOT/infra/langfuse/model-definitions"
APPLY=false

usage() {
  cat <<'EOF'
Usage: scripts/langfuse-model-pricing.sh [--apply]

Preview or create tracked LangFuse model definitions. The command never
updates or deletes an existing definition: review an existing model in the
LangFuse UI/API before changing its tracked JSON definition.

Required environment:
  LANGFUSE_BASE_URL
  LANGFUSE_PUBLIC_KEY
  LANGFUSE_SECRET_KEY

Use --apply to create definitions that are not already present. Preview is the
default. Configure a model only after its client plugin emits mutually
exclusive LangFuse usage-detail buckets.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --apply) APPLY=true ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done

for required in LANGFUSE_BASE_URL LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY; do
  [ -n "${!required:-}" ] || { echo "missing $required" >&2; exit 1; }
done

command -v curl >/dev/null 2>&1 || { echo 'curl is required' >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo 'jq is required' >&2; exit 1; }

base_url="${LANGFUSE_BASE_URL%/}"

find_model() {
  local model_name="$1"
  local page=1
  local response
  local match
  while :; do
    response="$(curl -sSf --user "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
      "$base_url/api/public/models?limit=100&page=$page")"
    match="$(printf '%s' "$response" | jq -c --arg name "$model_name" \
      '[.data[] | select(.modelName == $name)] | first // empty')"
    if [ -n "$match" ]; then
      printf '%s' "$match"
      return
    fi
    if [ "$(printf '%s' "$response" | jq -r '.meta.page >= .meta.totalPages')" = true ]; then
      return
    fi
    page=$((page + 1))
  done
}

for definition in "$MODELS_DIR"/*.json; do
  [ -f "$definition" ] || continue
  model_name="$(jq -r '.modelName' "$definition")"
  existing="$(find_model "$model_name")"
  if [ -n "$existing" ]; then
    printf 'exists: %s (%s)\n' "$model_name" "$(printf '%s' "$existing" | jq -r '.id')"
    continue
  fi

  if [ "$APPLY" = false ]; then
    printf 'would create: %s\n' "$model_name"
    continue
  fi

  curl -sSf --user "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
    -H 'Content-Type: application/json' \
    -X POST "$base_url/api/public/models" \
    --data-binary "@$definition" \
    | jq -r '"created: " + .modelName + " (" + .id + ")"'
done

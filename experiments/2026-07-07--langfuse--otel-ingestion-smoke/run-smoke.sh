#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXPERIMENT_DIR="$ROOT/experiments/2026-07-07--langfuse--otel-ingestion-smoke"
RUN_DIR="${RUN_DIR:-$EXPERIMENT_DIR/runs/real-backend-smoke}"
ITMUX_BIN="${ITMUX_BIN:-$ROOT/providers/workspaces/interactive-tmux/driver-rs/target/debug/itmux}"
FAKE_CODEX_BIN="$ROOT/experiments/2026-07-07--langfuse--cli-runtime-failfast/fixtures/fake-codex-success.sh"

required_env=(
  LANGFUSE_BASE_URL
  LANGFUSE_PUBLIC_KEY
  LANGFUSE_SECRET_KEY
  LANGFUSE_TRACING_ENVIRONMENT
)

keychain_services=(
  agentic-primitives/langfuse/base-url
  agentic-primitives/langfuse/public-key
  agentic-primitives/langfuse/secret-key
  agentic-primitives/langfuse/tracing-environment
)

mkdir -p "$RUN_DIR"

redacted_env="$RUN_DIR/otel-exporter-env.redacted.txt"
keychain_check="$RUN_DIR/keychain-check.redacted.txt"
response="$RUN_DIR/langfuse-ingest-response.txt"
stdout_jsonl="$RUN_DIR/stdout.jsonl"
events_jsonl="$RUN_DIR/events.jsonl"
result_json="$RUN_DIR/result.json"
trace_query_v2="$RUN_DIR/langfuse-trace-query-v2.json"
trace_query_legacy="$RUN_DIR/langfuse-trace-query-legacy.json"
trace_ui_response="$RUN_DIR/trace-ui-response.txt"
trace_ui_html="$RUN_DIR/trace-ui.html"
summary="$RUN_DIR/summary.txt"

: >"$redacted_env"
missing=()
for name in "${required_env[@]}"; do
  if [ -n "${!name:-}" ]; then
    printf '%s=<set>\n' "$name" >>"$redacted_env"
  else
    printf '%s=<missing>\n' "$name" >>"$redacted_env"
    missing+=("$name")
  fi
done
if [ -n "${LANGFUSE_PROJECT_ID:-}" ]; then
  printf 'LANGFUSE_PROJECT_ID=<set>\n' >>"$redacted_env"
else
  printf 'LANGFUSE_PROJECT_ID=<missing>\n' >>"$redacted_env"
fi

: >"$keychain_check"
if command -v security >/dev/null 2>&1; then
  for service in "${keychain_services[@]}"; do
    if security find-generic-password -a "$USER" -s "$service" -w >/dev/null 2>&1; then
      printf '%s=<set>\n' "$service" >>"$keychain_check"
    else
      printf '%s=<missing>\n' "$service" >>"$keychain_check"
    fi
  done
else
  printf 'security=<unavailable>\n' >>"$keychain_check"
fi

if [ "${#missing[@]}" -gt 0 ]; then
  {
    printf 'not attempted: missing required LangFuse configuration: '
    local_joined=""
    for name in "${missing[@]}"; do
      if [ -n "$local_joined" ]; then
        local_joined="$local_joined, "
      fi
      local_joined="$local_joined$name"
    done
    printf '%s\n' "$local_joined"
  } | tee "$response" >"$summary"
  exit 78
fi

if [ ! -x "$ITMUX_BIN" ]; then
  printf 'not attempted: itmux binary is not executable: %s\n' "$ITMUX_BIN" | tee "$response" >"$summary"
  exit 78
fi

if [ ! -x "$FAKE_CODEX_BIN" ]; then
  printf 'not attempted: fake codex fixture is not executable: %s\n' "$FAKE_CODEX_BIN" | tee "$response" >"$summary"
  exit 78
fi

rm -f \
  "$stdout_jsonl" \
  "$events_jsonl" \
  "$result_json" \
  "$trace_query_v2" \
  "$trace_query_legacy" \
  "$trace_ui_response" \
  "$trace_ui_html"

set +e
"$ITMUX_BIN" codex-exec \
  --codex-bin "$FAKE_CODEX_BIN" \
  --prompt "Reply exactly: LANGFUSE_SMOKE_OK" \
  --observability-file "$events_jsonl" \
  --observability-langfuse \
  --result-file "$result_json" \
  >"$stdout_jsonl" 2>"$RUN_DIR/stderr.txt"
exit_code=$?
set -e

{
  printf 'exit_code=%s\n' "$exit_code"
  if [ -f "$result_json" ] && command -v jq >/dev/null 2>&1; then
    jq -r '
      .observability.exporters[]
      | select(.kind == "langfuse_otlp")
      | "langfuse_status=\(.status)\nlangfuse_events_exported=\(.events_exported)\nlangfuse_target=\(.target // "")\nlangfuse_links=\((.links // []) | length)\nlangfuse_error=\(.error // "")"
    ' "$result_json"
  else
    printf 'langfuse_status=<unknown>\n'
  fi
} | tee "$summary"

if [ "$exit_code" -eq 0 ] && [ -f "$result_json" ] && [ -s "$events_jsonl" ] && command -v jq >/dev/null 2>&1; then
  run_id="$(head -n 1 "$events_jsonl" | jq -r '.run_id // ""')"
  trace_url="$(jq -r '.observability.exporters[] | select(.kind == "langfuse_otlp") | .links[0].uri // ""' "$result_json")"
  trace_id="${trace_url##*/}"
  query_from="${LANGFUSE_QUERY_FROM_START_TIME:-2020-01-01T00:00:00Z}"
  query_to="${LANGFUSE_QUERY_TO_START_TIME:-2100-01-01T00:00:00Z}"

  {
    printf 'run_id=%s\n' "$run_id"
    printf 'trace_id=%s\n' "$trace_id"
    printf 'trace_url=%s\n' "$trace_url"
  } >>"$summary"

  set +e
  "$ITMUX_BIN" langfuse-trace \
    --run-id "$run_id" \
    --from-start-time "$query_from" \
    --to-start-time "$query_to" \
    --limit 20 \
    >"$trace_query_v2"
  trace_query_v2_exit=$?

  trace_query_legacy_exit=1
  trace_query_legacy_attempts=0
  for attempt in $(seq 1 10); do
    trace_query_legacy_attempts="$attempt"
    "$ITMUX_BIN" langfuse-trace \
      --api legacy-trace \
      --run-id "$run_id" \
      --from-start-time "$query_from" \
      --to-start-time "$query_to" \
      --limit 20 \
      >"$trace_query_legacy"
    trace_query_legacy_exit=$?
    if [ "$trace_query_legacy_exit" -eq 0 ]; then
      break
    fi
    sleep 2
  done

  trace_ui_status="$(curl -sS -L -o "$trace_ui_html" -w '%{http_code} %{url_effective}' "$trace_url" 2>"$RUN_DIR/trace-ui-stderr.txt")"
  trace_ui_exit=$?
  set -e

  printf '%s\n' "$trace_ui_status" >"$trace_ui_response"
  observation_count="<unknown>"
  root_start_time="<unknown>"
  if [ "$trace_query_legacy_exit" -eq 0 ]; then
    observation_count="$(jq -r '(.response.observations // []) | length' "$trace_query_legacy")"
    root_start_time="$(jq -r '.response.observations[] | select(.name == "agentic_primitives.run") | .startTime' "$trace_query_legacy" | head -n 1)"
  fi

  {
    printf 'langfuse_trace_query_v2_exit=%s\n' "$trace_query_v2_exit"
    printf 'langfuse_trace_query_legacy_exit=%s\n' "$trace_query_legacy_exit"
    printf 'langfuse_trace_query_legacy_attempts=%s\n' "$trace_query_legacy_attempts"
    printf 'langfuse_observation_count=%s\n' "$observation_count"
    printf 'langfuse_root_start_time=%s\n' "$root_start_time"
    printf 'langfuse_trace_ui_exit=%s\n' "$trace_ui_exit"
    printf 'langfuse_trace_ui_status=%s\n' "$trace_ui_status"
  } >>"$summary"

  if [ "$trace_query_legacy_exit" -ne 0 ] || [ "$trace_ui_exit" -ne 0 ]; then
    cp "$summary" "$response"
    exit 1
  fi
fi

cp "$summary" "$response"
exit "$exit_code"

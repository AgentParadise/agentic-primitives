#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT="text"
RUN_TESTS="true"

usage() {
  cat <<'EOF'
Usage: scripts/langfuse-observability-doctor.sh [--json] [--no-tests]

Secret-safe preflight for agentic-primitives LangFuse observability setup.
It does not install plugins, mutate config, or print LangFuse credential
values. It reports set/missing state and runs the focused runtime guard test
when cargo is available unless --no-tests is passed.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --json)
      OUTPUT="json"
      ;;
    --no-tests)
      RUN_TESTS="false"
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

command_path() {
  command -v "$1" 2>/dev/null || true
}

status_for_env() {
  local name="$1"
  if [ -n "${!name:-}" ]; then
    printf 'set'
  else
    printf 'missing'
  fi
}

json_string() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/\\n}"
  printf '"%s"' "$value"
}

json_bool() {
  if [ "$1" = "true" ]; then
    printf 'true'
  else
    printf 'false'
  fi
}

version_line() {
  local cmd="$1"
  if command -v "$cmd" >/dev/null 2>&1; then
    "$cmd" --version 2>/dev/null | head -1 || true
  fi
}

node_major() {
  local version
  version="$(version_line node)"
  version="${version#v}"
  version="${version%%.*}"
  case "$version" in
    ''|*[!0-9]*) printf '0' ;;
    *) printf '%s' "$version" ;;
  esac
}

contains_pattern() {
  local pattern="$1"
  shift
  grep -Eq "$pattern" "$@" 2>/dev/null
}

file_contains() {
  local file="$1"
  local pattern="$2"
  if [ -f "$file" ] && contains_pattern "$pattern" "$file"; then
    printf 'true'
  else
    printf 'false'
  fi
}

codex_config_paths() {
  printf '%s\n' "$HOME/.codex/config.toml"
  printf '%s\n' "$ROOT/.codex/config.toml"
}

codex_plugin_hooks_enabled() {
  local path
  while IFS= read -r path; do
    if [ -f "$path" ] && contains_pattern 'plugin_hooks[[:space:]]*=[[:space:]]*true' "$path"; then
      printf 'true'
      return
    fi
  done < <(codex_config_paths)
  printf 'false'
}

codex_tracing_plugin_enabled() {
  local path
  while IFS= read -r path; do
    if [ -f "$path" ] && contains_pattern 'tracing@codex-observability-plugin|codex-observability-plugin' "$path"; then
      printf 'true'
      return
    fi
  done < <(codex_config_paths)
  printf 'false'
}

repo_has_file() {
  if [ -f "$ROOT/$1" ]; then
    printf 'true'
  else
    printf 'false'
  fi
}

repo_has_text() {
  local pattern="$1"
  shift
  if contains_pattern "$pattern" "$@"; then
    printf 'true'
  else
    printf 'false'
  fi
}

guard_test_status="skipped"
guard_test_detail="cargo not found"
if [ "$RUN_TESTS" = "false" ]; then
  guard_test_detail="tests disabled by --no-tests"
elif command -v cargo >/dev/null 2>&1; then
  guard_output="$(mktemp "${TMPDIR:-/tmp}/agentic-langfuse-guard.XXXXXX")"
  if (
    cd "$ROOT"
    cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml cli_exporters -- --nocapture
  ) >"$guard_output" 2>&1; then
    guard_test_status="pass"
    guard_test_detail="cli_exporters tests passed"
  else
    guard_test_status="fail"
    guard_test_detail="cli_exporters tests failed"
  fi
  rm -f "$guard_output"
fi

generated_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
claude_path="$(command_path claude)"
codex_path="$(command_path codex)"
node_path="$(command_path node)"
uv_path="$(command_path uv)"
python_path="$(command_path python3)"
cargo_path="$(command_path cargo)"
node_major_value="$(node_major)"
node22_plus="false"
if [ "$node_major_value" -ge 22 ] 2>/dev/null; then
  node22_plus="true"
fi
claude_runtime_ok="false"
if [ -n "$uv_path" ] || [ -n "$python_path" ]; then
  claude_runtime_ok="true"
fi
codex_hooks_enabled="$(codex_plugin_hooks_enabled)"
codex_plugin_enabled="$(codex_tracing_plugin_enabled)"
runtime_ready="true"
for required in LANGFUSE_BASE_URL LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY; do
  if [ "$(status_for_env "$required")" != "set" ]; then
    runtime_ready="false"
  fi
done
trace_to_langfuse="${TRACE_TO_LANGFUSE:-missing}"
trace_to_langfuse_active="false"
if [ "$trace_to_langfuse" = "true" ]; then
  trace_to_langfuse_active="true"
fi

file_fanout_supported="$(repo_has_text 'observability-file' "$ROOT/providers/workspaces/interactive-tmux/driver-rs/src/main.rs" "$ROOT/providers/workspaces/interactive-tmux/driver-rs/README.md")"
syntropic_fanout_supported="$(repo_has_text 'observability-syntropic-file|SyntropicJsonl|syntropic_jsonl' "$ROOT/providers/workspaces/interactive-tmux/driver-rs/src/main.rs" "$ROOT/providers/workspaces/interactive-tmux/driver-rs/README.md")"
force_flag_supported="$(repo_has_text 'observability-langfuse-force' "$ROOT/providers/workspaces/interactive-tmux/driver-rs/src/main.rs" "$ROOT/providers/workspaces/interactive-tmux/driver-rs/README.md")"
mcp_server_present="$(repo_has_file 'plugins/observability/mcp/langfuse_server.py')"

if [ "$OUTPUT" = "json" ]; then
  cat <<EOF
{
  "generated_at": $(json_string "$generated_at"),
  "repo_root": $(json_string "$ROOT"),
  "tools": {
    "claude": {"present": $(json_bool "$([ -n "$claude_path" ] && printf true || printf false)"), "path": $(json_string "$claude_path")},
    "codex": {"present": $(json_bool "$([ -n "$codex_path" ] && printf true || printf false)"), "path": $(json_string "$codex_path")},
    "node": {"present": $(json_bool "$([ -n "$node_path" ] && printf true || printf false)"), "path": $(json_string "$node_path"), "major": $node_major_value, "node22_plus": $(json_bool "$node22_plus")},
    "uv": {"present": $(json_bool "$([ -n "$uv_path" ] && printf true || printf false)"), "path": $(json_string "$uv_path")},
    "python3": {"present": $(json_bool "$([ -n "$python_path" ] && printf true || printf false)"), "path": $(json_string "$python_path")},
    "cargo": {"present": $(json_bool "$([ -n "$cargo_path" ] && printf true || printf false)"), "path": $(json_string "$cargo_path")}
  },
  "official_plugins": {
    "claude": {
      "command_present": $(json_bool "$([ -n "$claude_path" ] && printf true || printf false)"),
      "runtime_ok": $(json_bool "$claude_runtime_ok"),
      "expected_plugin": "langfuse/Claude-Observability-Plugin",
      "config_note": "use claude plugin install/configure; secrets are not inspected by this doctor"
    },
    "codex": {
      "command_present": $(json_bool "$([ -n "$codex_path" ] && printf true || printf false)"),
      "node22_plus": $(json_bool "$node22_plus"),
      "plugin_hooks_enabled": $(json_bool "$codex_hooks_enabled"),
      "tracing_plugin_configured": $(json_bool "$codex_plugin_enabled"),
      "expected_plugin": "langfuse/codex-observability-plugin"
    }
  },
  "runtime_env": {
    "LANGFUSE_BASE_URL": $(json_string "$(status_for_env LANGFUSE_BASE_URL)"),
    "LANGFUSE_PUBLIC_KEY": $(json_string "$(status_for_env LANGFUSE_PUBLIC_KEY)"),
    "LANGFUSE_SECRET_KEY": $(json_string "$(status_for_env LANGFUSE_SECRET_KEY)"),
    "LANGFUSE_TRACING_ENVIRONMENT": $(json_string "$(status_for_env LANGFUSE_TRACING_ENVIRONMENT)"),
    "LANGFUSE_PROJECT_ID": $(json_string "$(status_for_env LANGFUSE_PROJECT_ID)"),
    "TRACE_TO_LANGFUSE": $(json_string "$trace_to_langfuse"),
    "required_ready": $(json_bool "$runtime_ready"),
    "official_plugin_active": $(json_bool "$trace_to_langfuse_active")
  },
  "fanout": {
    "file_jsonl_supported": $(json_bool "$file_fanout_supported"),
    "syntropic_jsonl_supported": $(json_bool "$syntropic_fanout_supported"),
    "mcp_server_present": $(json_bool "$mcp_server_present")
  },
  "otlp_noise_guard": {
    "trace_to_langfuse_suppression_supported": $(json_bool "$force_flag_supported"),
    "force_flag_supported": $(json_bool "$force_flag_supported"),
    "focused_test_status": $(json_string "$guard_test_status"),
    "focused_test_detail": $(json_string "$guard_test_detail")
  }
}
EOF
  exit 0
fi

cat <<EOF
LangFuse observability doctor
generated_at: $generated_at
repo: $ROOT

Official rich trace path:
  Claude command: $([ -n "$claude_path" ] && printf 'present' || printf 'missing')
  Claude runtime: $([ "$claude_runtime_ok" = "true" ] && printf 'ok' || printf 'missing uv/python3')
  Codex command: $([ -n "$codex_path" ] && printf 'present' || printf 'missing')
  Codex Node 22+: $([ "$node22_plus" = "true" ] && printf 'ok' || printf 'missing')
  Codex plugin_hooks: $codex_hooks_enabled
  Codex tracing plugin configured: $codex_plugin_enabled

Runtime LangFuse env:
  LANGFUSE_BASE_URL=$(status_for_env LANGFUSE_BASE_URL)
  LANGFUSE_PUBLIC_KEY=$(status_for_env LANGFUSE_PUBLIC_KEY)
  LANGFUSE_SECRET_KEY=$(status_for_env LANGFUSE_SECRET_KEY)
  LANGFUSE_TRACING_ENVIRONMENT=$(status_for_env LANGFUSE_TRACING_ENVIRONMENT)
  LANGFUSE_PROJECT_ID=$(status_for_env LANGFUSE_PROJECT_ID)
  TRACE_TO_LANGFUSE=$trace_to_langfuse

Fanout:
  file JSONL supported: $file_fanout_supported
  Syntropic137 JSONL supported: $syntropic_fanout_supported
  MCP server present: $mcp_server_present

OTLP noise guard:
  fallback suppression/force flag supported: $force_flag_supported
  focused cli_exporters test: $guard_test_status ($guard_test_detail)
EOF

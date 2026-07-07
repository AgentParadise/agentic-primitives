#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LANGFUSE_HOME="${LANGFUSE_HOME:-$ROOT/.agentic/langfuse/langfuse}"
LANGFUSE_REPO="${LANGFUSE_REPO:-https://github.com/langfuse/langfuse.git}"
LANGFUSE_BASE_URL="${LANGFUSE_BASE_URL:-http://localhost:3000}"

usage() {
  cat <<'EOF'
Usage: scripts/langfuse-local.sh <command>

Commands:
  init      Clone the official LangFuse repository under .agentic/langfuse/
  start     Run docker compose up -d from the cloned LangFuse repository
  stop      Run docker compose down from the cloned LangFuse repository
  status    Run docker compose ps from the cloned LangFuse repository
  smoke     Run the agentic-primitives LangFuse smoke against LANGFUSE_BASE_URL

Environment:
  LANGFUSE_HOME      Defaults to .agentic/langfuse/langfuse
  LANGFUSE_REPO      Defaults to https://github.com/langfuse/langfuse.git
  LANGFUSE_BASE_URL  Defaults to http://localhost:3000

Secrets:
  Do not commit LangFuse secrets. Create project API keys in the LangFuse UI,
  then export LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and
  LANGFUSE_TRACING_ENVIRONMENT in your shell or load them from macOS Keychain.
EOF
}

require_compose_dir() {
  if [ ! -d "$LANGFUSE_HOME/.git" ]; then
    printf 'LangFuse repository not found at %s\n' "$LANGFUSE_HOME" >&2
    printf 'Run: scripts/langfuse-local.sh init\n' >&2
    exit 78
  fi
}

case "${1:-}" in
  init)
    if [ -d "$LANGFUSE_HOME/.git" ]; then
      printf 'LangFuse repository already exists at %s\n' "$LANGFUSE_HOME"
      exit 0
    fi
    mkdir -p "$(dirname "$LANGFUSE_HOME")"
    git clone --depth 1 "$LANGFUSE_REPO" "$LANGFUSE_HOME"
    cat <<EOF
LangFuse repository cloned to:
  $LANGFUSE_HOME

Next:
  1. Review the official docker-compose.yml and secret settings there.
  2. Run: scripts/langfuse-local.sh start
  3. Open: $LANGFUSE_BASE_URL
  4. Create a project and API keys in the LangFuse UI.
  5. Export LANGFUSE_BASE_URL, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY,
     LANGFUSE_TRACING_ENVIRONMENT, and optional LANGFUSE_PROJECT_ID.
  6. Run: scripts/langfuse-local.sh smoke
EOF
    ;;
  start)
    require_compose_dir
    (cd "$LANGFUSE_HOME" && docker compose up -d)
    printf 'LangFuse starting at %s. Wait for the web container to become ready.\n' "$LANGFUSE_BASE_URL"
    ;;
  stop)
    require_compose_dir
    (cd "$LANGFUSE_HOME" && docker compose down)
    ;;
  status)
    require_compose_dir
    (cd "$LANGFUSE_HOME" && docker compose ps)
    ;;
  smoke)
    export LANGFUSE_BASE_URL
    "$ROOT/experiments/2026-07-07--langfuse--otel-ingestion-smoke/run-smoke.sh"
    ;;
  ""|-h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

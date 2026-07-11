#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LANGFUSE_HOME="${LANGFUSE_HOME:-$ROOT/.agentic/langfuse/langfuse}"
LANGFUSE_REPO="${LANGFUSE_REPO:-https://github.com/langfuse/langfuse.git}"
LANGFUSE_BASE_URL="${LANGFUSE_BASE_URL:-http://localhost:3000}"
LANGFUSE_COMPOSE_OVERRIDE="${LANGFUSE_COMPOSE_OVERRIDE:-$LANGFUSE_HOME/docker-compose.agentic-local.yml}"
LANGFUSE_ENV_FILE="${LANGFUSE_ENV_FILE:-$LANGFUSE_HOME/.env}"

usage() {
  cat <<'EOF'
Usage: scripts/langfuse-local.sh <command>

Commands:
  init      Clone the official LangFuse repository under .agentic/langfuse/
  start|up  Run docker compose up -d from the cloned LangFuse repository
  stop|down Run docker compose down from the cloned LangFuse repository
  status    Run docker compose ps from the cloned LangFuse repository
  health    Check the configured LangFuse public health endpoint
  smoke     Run the official-plugin setup/readiness check against local env

Environment:
  LANGFUSE_HOME      Defaults to .agentic/langfuse/langfuse
  LANGFUSE_REPO      Defaults to https://github.com/langfuse/langfuse.git
  LANGFUSE_BASE_URL  Defaults to http://localhost:3000
  LANGFUSE_ENV_FILE  Defaults to .agentic/langfuse/langfuse/.env

Secrets:
  Do not commit LangFuse secrets. The local bootstrap writes an ignored .env
  with a provisioned local project and API keys for smoke testing.
EOF
}

require_compose_dir() {
  if [ ! -d "$LANGFUSE_HOME/.git" ]; then
    printf 'LangFuse repository not found at %s\n' "$LANGFUSE_HOME" >&2
    printf 'Run: scripts/langfuse-local.sh init\n' >&2
    exit 78
  fi
}

compose_args() {
  printf '%s\n' -f docker-compose.yml
  if [ -f "$LANGFUSE_COMPOSE_OVERRIDE" ]; then
    printf '%s\n' -f "$(basename "$LANGFUSE_COMPOSE_OVERRIDE")"
  fi
}

compose_run() {
  require_compose_dir
  local args=()
  while IFS= read -r arg; do
    args+=("$arg")
  done < <(compose_args)
  (cd "$LANGFUSE_HOME" && docker compose "${args[@]}" "$@")
}

ensure_local_files() {
  require_compose_dir
  if [ ! -f "$LANGFUSE_COMPOSE_OVERRIDE" ]; then
    cat >"$LANGFUSE_COMPOSE_OVERRIDE" <<'EOF'
services:
  langfuse-worker:
    ports: !reset []

  clickhouse:
    ports: !reset []

  minio:
    ports: !reset []

  redis:
    ports: !reset []

  postgres:
    ports: !reset []
EOF
  fi

  if [ ! -f "$LANGFUSE_ENV_FILE" ]; then
    local nextauth_secret salt encryption_key public_key secret_key user_password
    nextauth_secret="$(random_hex 32)"
    salt="$(random_hex 16)"
    encryption_key="$(random_hex 32)"
    public_key="pk-lf-$(random_hex 16)"
    secret_key="sk-lf-$(random_hex 16)"
    user_password="$(random_hex 18)"
    umask 077
    cat >"$LANGFUSE_ENV_FILE" <<EOF
NEXTAUTH_URL=$LANGFUSE_BASE_URL
NEXTAUTH_SECRET=$nextauth_secret
SALT=$salt
ENCRYPTION_KEY=$encryption_key
TELEMETRY_ENABLED=false

LANGFUSE_INIT_ORG_ID=agentic-primitives-local-org
LANGFUSE_INIT_ORG_NAME=Agentic-Primitives-Local
LANGFUSE_INIT_PROJECT_ID=agentic-primitives-local-project
LANGFUSE_INIT_PROJECT_NAME=Agentic-Primitives-E2E
LANGFUSE_INIT_PROJECT_PUBLIC_KEY=$public_key
LANGFUSE_INIT_PROJECT_SECRET_KEY=$secret_key
LANGFUSE_INIT_USER_EMAIL=agentic-local@example.invalid
LANGFUSE_INIT_USER_NAME=Agentic-Local
LANGFUSE_INIT_USER_PASSWORD=$user_password
EOF
  fi
}

random_hex() {
  local bytes="$1"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$bytes"
  else
    LC_ALL=C tr -dc 'a-f0-9' </dev/urandom | head -c $((bytes * 2))
  fi
}

load_local_env() {
  if [ -f "$LANGFUSE_ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$LANGFUSE_ENV_FILE"
    set +a
  fi
  export LANGFUSE_BASE_URL
  export LANGFUSE_PUBLIC_KEY="${LANGFUSE_PUBLIC_KEY:-${LANGFUSE_INIT_PROJECT_PUBLIC_KEY:-}}"
  export LANGFUSE_SECRET_KEY="${LANGFUSE_SECRET_KEY:-${LANGFUSE_INIT_PROJECT_SECRET_KEY:-}}"
  export LANGFUSE_PROJECT_ID="${LANGFUSE_PROJECT_ID:-${LANGFUSE_INIT_PROJECT_ID:-}}"
  export LANGFUSE_TRACING_ENVIRONMENT="${LANGFUSE_TRACING_ENVIRONMENT:-local-macbook}"
}

case "${1:-}" in
  init)
    if [ -d "$LANGFUSE_HOME/.git" ]; then
      printf 'LangFuse repository already exists at %s\n' "$LANGFUSE_HOME"
      ensure_local_files
      exit 0
    fi
    mkdir -p "$(dirname "$LANGFUSE_HOME")"
    git clone --depth 1 "$LANGFUSE_REPO" "$LANGFUSE_HOME"
    ensure_local_files
    cat <<EOF
LangFuse repository cloned to:
  $LANGFUSE_HOME

Next:
  1. Review the official docker-compose.yml and generated ignored .env there.
  2. Run: scripts/langfuse-local.sh start
  3. Open: $LANGFUSE_BASE_URL
  4. Export local keys from $LANGFUSE_ENV_FILE or your secret store.
  5. Run: scripts/langfuse-local.sh smoke
EOF
    ;;
  start|up)
    ensure_local_files
    compose_run up -d
    printf 'LangFuse starting at %s. Wait for the web container to become ready.\n' "$LANGFUSE_BASE_URL"
    ;;
  stop|down)
    compose_run down
    ;;
  status)
    compose_run ps
    ;;
  health)
    load_local_env
    curl -fsS "$LANGFUSE_BASE_URL/api/public/health"
    printf '\nLangFuse health check passed for %s\n' "$LANGFUSE_BASE_URL"
    ;;
  smoke)
    ensure_local_files
    load_local_env
    "$ROOT/scripts/langfuse-observability-doctor.sh" --json
    ;;
  ""|-h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

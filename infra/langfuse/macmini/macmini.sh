#!/usr/bin/env bash
set -euo pipefail

# Operator entrypoint for a private, durable LangFuse server on a Mac mini.
# Upstream LangFuse Compose is pinned by scripts/langfuse-local.sh; this file
# supplies only host policy, not credentials.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DEPLOY_DIR="$ROOT/infra/langfuse/macmini"
LANGFUSE_HOME="${LANGFUSE_HOME:-/opt/agentic-primitives/langfuse}"
LANGFUSE_TAILSCALE_HOST="${LANGFUSE_TAILSCALE_HOST:-}"
LANGFUSE_BASE_URL="${LANGFUSE_BASE_URL:-}"
LANGFUSE_COMPOSE_OVERRIDE="$DEPLOY_DIR/compose.macmini.yaml"
LANGFUSE_REF="${LANGFUSE_REF:-9b9cb4a1853082fd89ea46b6fe25a3df50fa8391}"

usage() {
  cat <<'EOF'
Usage: infra/langfuse/macmini/macmini.sh <init|up|down|status|health|serve|backup>

Required for init/up/serve:
  LANGFUSE_TAILSCALE_HOST=mac-mini.tailnet-name.ts.net

Optional:
  LANGFUSE_HOME=/opt/agentic-primitives/langfuse
  LANGFUSE_BASE_URL=https://mac-mini.tailnet-name.ts.net
  LANGFUSE_REF=reviewed-upstream-git-ref
  LANGFUSE_BACKUP_DIR=/Volumes/Backup/langfuse

The script never writes credentials into this repository. init creates the
ignored $LANGFUSE_HOME/.env through the shared bootstrap.
EOF
}

require_host() {
  if [ -z "$LANGFUSE_TAILSCALE_HOST" ]; then
    printf 'LANGFUSE_TAILSCALE_HOST is required (for example mac-mini.tailnet-name.ts.net)\n' >&2
    exit 64
  fi
  if [ -z "$LANGFUSE_BASE_URL" ]; then
    LANGFUSE_BASE_URL="https://$LANGFUSE_TAILSCALE_HOST"
  fi
  export LANGFUSE_HOME LANGFUSE_BASE_URL LANGFUSE_COMPOSE_OVERRIDE LANGFUSE_REF
}

shared() {
  "$ROOT/scripts/langfuse-local.sh" "$@"
}

case "${1:-}" in
  init)
    require_host
    shared init
    git -C "$LANGFUSE_HOME" fetch --depth 1 origin "$LANGFUSE_REF"
    git -C "$LANGFUSE_HOME" checkout --detach FETCH_HEAD
    ;;
  up)
    require_host
    shared up
    ;;
  down|status|health)
    require_host
    shared "$1"
    ;;
  serve)
    require_host
    command -v tailscale >/dev/null || { echo 'tailscale is required' >&2; exit 69; }
    sudo tailscale up --advertise-tags=tag:langfuse
    sudo tailscale serve --https=443 http://127.0.0.1:3000
    printf 'LangFuse is served privately at %s\n' "$LANGFUSE_BASE_URL"
    ;;
  backup)
    require_host
    backup_dir="${LANGFUSE_BACKUP_DIR:-$HOME/langfuse-backups}/$(date -u +%Y%m%dT%H%M%SZ)"
    mkdir -p "$backup_dir"
    docker compose -f "$LANGFUSE_HOME/docker-compose.yml" -f "$LANGFUSE_COMPOSE_OVERRIDE" \
      exec -T postgres pg_dump -U "${POSTGRES_USER:-postgres}" "${POSTGRES_DB:-postgres}" \
      >"$backup_dir/postgres.sql"
    docker volume ls --format '{{.Name}}' | grep '^langfuse_' >"$backup_dir/volume-manifest.txt"
    printf 'Wrote Postgres dump and volume manifest to %s\n' "$backup_dir"
    printf 'Snapshot the listed Docker volumes with the host backup system before upgrades.\n'
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac

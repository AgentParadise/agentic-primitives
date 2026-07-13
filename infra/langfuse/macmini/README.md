# Mac Mini LangFuse IaC

This package deploys the canonical, self-hosted LangFuse backend for Agentic
Primitives. The server is intentionally private: Docker binds the LangFuse web
service to `127.0.0.1:3000`, and Tailscale Serve publishes HTTPS on the
tailnet. Claude, Codex, VPS hosts, and isolated workspaces use that HTTPS URL
as `LANGFUSE_BASE_URL`.

## What Is Tracked

- `compose.macmini.yaml`: the host-security overlay for upstream LangFuse
- `macmini.sh`: deployment, lifecycle, Tailscale Serve, and backup entrypoint
- `tailscale/langfuse-acl-snippet.jsonc`: policy additions to paste into the
  canonical tailnet policy
- the upstream LangFuse revision in `scripts/langfuse-local.sh`

The script creates the upstream checkout and its `.env` at
`/opt/agentic-primitives/langfuse` by default. That location is deliberately
outside this checkout and contains generated credentials and state.

## First Deployment

On the Mac mini, clone this repository, then set the real MagicDNS name:

```bash
export LANGFUSE_TAILSCALE_HOST=mac-mini.tailnet-name.ts.net
infra/langfuse/macmini/macmini.sh init
infra/langfuse/macmini/macmini.sh up
infra/langfuse/macmini/macmini.sh serve
infra/langfuse/macmini/macmini.sh health
```

Before `serve`, add the reviewed snippet in
`tailscale/langfuse-acl-snippet.jsonc` to the tailnet's canonical policy. The
Mac mini needs `tag:langfuse`; agent hosts need `tag:agents` only when they are
not operator-admin devices.

Use `https://$LANGFUSE_TAILSCALE_HOST` for `LANGFUSE_BASE_URL`. Do not send
clients to Docker port 3000 and do not expose it on the public internet.

## Backup and Upgrade

Run a logical Postgres backup before upgrades:

```bash
export LANGFUSE_TAILSCALE_HOST=mac-mini.tailnet-name.ts.net
export LANGFUSE_BACKUP_DIR=/Volumes/Backups/langfuse
infra/langfuse/macmini/macmini.sh backup
```

The command writes a Postgres dump and volume manifest. Snapshot the listed
Docker volumes with the Mac mini's durable host backup system; ClickHouse and
MinIO data live in those volumes. To deliberately move off the pinned upstream
revision, set `LANGFUSE_REF`, review the upstream change, rerun `init`, and
redeploy in a maintenance window.

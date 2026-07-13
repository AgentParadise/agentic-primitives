# Self-Hosted LangFuse IaC

This package deploys the canonical LangFuse backend for Agentic Primitives on
any Docker-capable host. The initial target is the Mac mini, but no file or
runtime contract is tied to that machine. The server is intentionally private:
Docker binds the LangFuse web service to `127.0.0.1:3000`, and Tailscale Serve
publishes HTTPS on the tailnet. Claude, Codex, VPS hosts, and isolated
workspaces use that HTTPS URL as `LANGFUSE_BASE_URL`.

## What Is Tracked

- `compose.private.yaml`: the host-security overlay for upstream LangFuse
- `deploy.sh`: deployment, lifecycle, Tailscale Serve, and backup entrypoint
- `tailscale/langfuse-acl-snippet.jsonc`: policy additions to paste into the
  canonical tailnet policy
- the upstream LangFuse revision in `scripts/langfuse-local.sh`

The script creates the upstream checkout and its `.env` at
`/opt/agentic-primitives/langfuse` by default. That location is deliberately
outside this checkout and contains generated credentials and state.

## First Deployment

On the chosen host, clone this repository, then set the real MagicDNS name.
For a Mac mini, this is the Mac mini's name; for a VPS, it is the VPS name:

```bash
export LANGFUSE_TAILSCALE_HOST=mac-mini.tailnet-name.ts.net
infra/langfuse/self-hosted/deploy.sh init
infra/langfuse/self-hosted/deploy.sh up
infra/langfuse/self-hosted/deploy.sh serve
infra/langfuse/self-hosted/deploy.sh health
```

Before `serve`, add the reviewed snippet in
`tailscale/langfuse-acl-snippet.jsonc` to the tailnet's canonical policy. The
LangFuse host needs `tag:langfuse`; agent hosts need `tag:agents` only when
they are not operator-admin devices.

On a new host, set the tag explicitly before serving:

```bash
export TAILSCALE_ADVERTISE_TAGS=tag:langfuse
```

On a host already carrying service tags, provide the complete desired list,
for example `tag:hindsight,tag:seshmagic,tag:langfuse`. The wrapper leaves tags
unchanged when this variable is omitted, so it cannot accidentally remove
existing service identity.

Use `https://$LANGFUSE_TAILSCALE_HOST` for `LANGFUSE_BASE_URL`. Do not send
clients to Docker port 3000 and do not expose it on the public internet.

## Backup and Upgrade

Run a logical Postgres backup before upgrades:

```bash
export LANGFUSE_TAILSCALE_HOST=mac-mini.tailnet-name.ts.net
export LANGFUSE_BACKUP_DIR=/Volumes/Backups/langfuse
infra/langfuse/self-hosted/deploy.sh backup
```

The command writes a Postgres dump and volume manifest. Snapshot the listed
Docker volumes with the host's durable backup system; ClickHouse and MinIO data
live in those volumes. To deliberately move off the pinned upstream
revision, set `LANGFUSE_REF`, review the upstream change, rerun `init`, and
redeploy in a maintenance window.

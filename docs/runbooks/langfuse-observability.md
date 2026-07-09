# LangFuse Observability Runbook

This runbook describes the supported ways to run LangFuse for Agentic
Primitives and point Claude Code, Codex, VPS hosts, and isolated Docker
workspaces at the same trace backend.

Use the setup guide for the short install path:

- `docs/guides/langfuse-observability-setup.md`

Use this runbook when deciding where LangFuse should live, how clients should
reach it, and how to verify that traces are useful.

## Current Contract

LangFuse traces for Claude Code and Codex come from LangFuse's official
plugins:

- Claude Code: `langfuse/Claude-Observability-Plugin`
- Codex: `langfuse/codex-observability-plugin`

Agentic Primitives keeps these local pieces:

- `scripts/langfuse-local.sh` to bootstrap and operate an official LangFuse
  Docker Compose stack under `.agentic/langfuse/`
- `scripts/langfuse-observability-doctor.sh` to check local readiness without
  printing secret values
- `itmux --observability-file` and `--observability-syntropic-file` for local
  JSONL evidence
- `itmux langfuse-*` commands and the `agentic-langfuse` MCP server for
  querying traces and writing feedback scores

The direct Rust OTLP writer is intentionally out of the active run path. It
created low-value spans compared with the official Claude and Codex plugins.

## Topologies

### Single-Machine Setup

Use this when experimenting on one MacBook or Mac mini.

Everything runs on the same machine:

- LangFuse Docker Compose stack
- Claude Code
- Codex
- Agentic Primitives checkout
- optional isolated local Docker workspaces

The default URL is:

```text
http://localhost:3000
```

Bootstrap and start:

```bash
scripts/langfuse-local.sh init
scripts/langfuse-local.sh up
scripts/langfuse-local.sh smoke
```

The bootstrap writes an ignored LangFuse `.env` file here:

```text
.agentic/langfuse/langfuse/.env
```

To retrieve the local login identity and generated password on your own
machine:

```bash
grep -E 'LANGFUSE_INIT_USER_EMAIL|LANGFUSE_INIT_USER_PASSWORD' \
  .agentic/langfuse/langfuse/.env
```

Do not commit or paste that file. Treat it as a local secret file.

### Centralized Server

Use this when one LangFuse instance should collect traces from many machines.

Recommended first centralized target:

- LangFuse runs on the Mac mini
- MacBook sends traces to the Mac mini
- VPS hosts send traces to the Mac mini
- isolated Docker workspaces send traces to the Mac mini

This gives one project history for learning loops, trace review, scores, and
cross-harness comparison.

Recommended initial project layout:

- one LangFuse organization
- one LangFuse project for Agentic Primitives
- separate `LANGFUSE_TRACING_ENVIRONMENT` values per source, for example
  `local-macbook`, `mac-mini`, `vps`, and `docker-workspace`
- tags or metadata for harness names such as `claude` and `codex`

Split into multiple LangFuse projects only when access control, retention, or
production/staging separation requires it.

## Server Setup

These steps work for a Mac mini or VPS with Docker installed.

Choose the URL that clients will use before the first `init`. For a Mac mini
reachable over Tailscale, that can be the MagicDNS name or the Tailscale IP:

```bash
export LANGFUSE_BASE_URL=http://mac-mini.tailnet-name.ts.net:3000
# or:
export LANGFUSE_BASE_URL=http://100.x.y.z:3000
```

Then bootstrap and start:

```bash
scripts/langfuse-local.sh init
scripts/langfuse-local.sh up
scripts/langfuse-local.sh status
```

`scripts/langfuse-local.sh init` writes `NEXTAUTH_URL=$LANGFUSE_BASE_URL` into
the generated `.env` on first creation. Set `LANGFUSE_BASE_URL` first so login
links, callbacks, and absolute URLs match the address used by clients.

If the `.env` already existed before changing the URL, edit only the
`NEXTAUTH_URL` value in:

```text
.agentic/langfuse/langfuse/.env
```

Then restart:

```bash
scripts/langfuse-local.sh down
scripts/langfuse-local.sh up
```

If the database was already initialized, changing `LANGFUSE_INIT_*` values does
not recreate users, orgs, projects, or keys. Use the LangFuse UI for existing
instances, or intentionally rebuild the local data volumes only when you are
sure there is nothing to preserve.

## Tailscale Access

Tailscale is the preferred private transport for a Mac mini LangFuse server.

Server side:

```bash
tailscale up
tailscale status
```

Pick one stable address for `LANGFUSE_BASE_URL`:

- MagicDNS name, for example `http://mac-mini.tailnet-name.ts.net:3000`
- Tailscale IP, for example `http://100.x.y.z:3000`

Use the MagicDNS name when it resolves reliably from every client. Use the
Tailscale IP when Docker or a VPS cannot resolve the MagicDNS name.

Do not expose port `3000` publicly without a reverse proxy, TLS, and a clear
auth story. For public internet access, put LangFuse behind a normal HTTPS
reverse proxy and use:

```bash
export LANGFUSE_BASE_URL=https://langfuse.example.com
```

## Client Setup

Run these steps on every MacBook, Mac mini shell, VPS, or long-lived workspace
host that should emit traces.

Export the shared server URL and project keys:

```bash
export LANGFUSE_BASE_URL=http://mac-mini.tailnet-name.ts.net:3000
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_TRACING_ENVIRONMENT=local-macbook
export TRACE_TO_LANGFUSE=true
```

Use a different `LANGFUSE_TRACING_ENVIRONMENT` on each source:

```bash
export LANGFUSE_TRACING_ENVIRONMENT=mac-mini
export LANGFUSE_TRACING_ENVIRONMENT=vps
export LANGFUSE_TRACING_ENVIRONMENT=docker-workspace
```

Check readiness:

```bash
scripts/langfuse-observability-doctor.sh --json
```

On minimal VPS images or containers without Rust:

```bash
scripts/langfuse-observability-doctor.sh --json --no-tests
```

## Claude Code

Install the official plugin:

```bash
claude plugin install langfuse/Claude-Observability-Plugin
```

Configure the plugin using Claude's plugin flow or secret store. For
deterministic shell and workspace runs, also make the shared `LANGFUSE_*`
environment available to the process that launches Claude.

Expected trace shape:

- named Claude turns and generations
- native tool observations such as `Tool: Read`
- model, usage, and cost metadata when available
- session grouping
- `telemetry.sdk.language=python`, because the official Claude plugin exports
  through LangFuse's Python SDK path

## Codex

Enable plugin hooks and the official tracing plugin:

```toml
[features]
plugin_hooks = true

[plugins."tracing@codex-observability-plugin"]
enabled = true
```

Place that in `~/.codex/config.toml` or a project `.codex/config.toml`, then
make sure the Codex process can read the shared `LANGFUSE_*` environment.

Expected trace shape:

- `Codex Turn` observations
- tool observations such as `exec_command`
- model, usage, and cost metadata when available
- session grouping
- `telemetry.sdk.language=nodejs`, because the official Codex plugin exports
  through LangFuse's Node.js SDK path

## Docker Workspace Isolation

Do not bake LangFuse keys into Docker images.

Pass the shared values at launch time:

```bash
docker run --rm \
  -e LANGFUSE_BASE_URL=http://mac-mini.tailnet-name.ts.net:3000 \
  -e LANGFUSE_PUBLIC_KEY \
  -e LANGFUSE_SECRET_KEY \
  -e LANGFUSE_TRACING_ENVIRONMENT=docker-workspace \
  -e TRACE_TO_LANGFUSE=true \
  agentic-workspace:local
```

If the workspace is launched by an Agentic Primitives provider, pass the same
values through that provider's mounted secret/config surface rather than
putting them in the image.

Network checks from inside the workspace:

```bash
curl -fsS "$LANGFUSE_BASE_URL/api/public/health"
scripts/langfuse-observability-doctor.sh --json --no-tests
```

If the container cannot resolve the Tailscale MagicDNS name:

- use the Mac mini's `100.x.y.z` Tailscale IP in `LANGFUSE_BASE_URL`
- or expose LangFuse through a host-level reverse proxy that containers can
  reach
- or configure the workspace network so Tailscale DNS/routes are visible inside
  the container

Keep local JSONL evidence mounted to a durable path when running isolated
agent jobs:

```bash
itmux run \
  --recipe /workspace/recipe.json \
  --task "Run the task" \
  --observability-file /workspace/.agentic/events.jsonl \
  --observability-syntropic-file /workspace/.agentic/syntropic-events.jsonl \
  --result-file /workspace/.agentic/result.json
```

## Verification

After any setup change, prove both harnesses.

1. Run the doctor:

   ```bash
   scripts/langfuse-observability-doctor.sh --json
   ```

2. Run one Claude session that calls at least one tool.

3. Run one Codex session that calls at least one tool.

4. Open LangFuse and confirm each trace has:

   - a useful trace name
   - native turn/generation observations
   - named tool observations
   - input/output or metadata sufficient to understand the run
   - model, usage, and cost data when the provider reports it
   - the expected `Environment`

5. Query the traces from Agentic Primitives:

   ```bash
   itmux langfuse-traces --limit 20 --output summary
   itmux langfuse-traces --harness codex --environment local-macbook
   itmux langfuse-trace --trace-id <trace-id> --include-scores --output summary
   ```

6. Write one feedback score:

   ```bash
   itmux langfuse-score \
     --trace-id <trace-id> \
     --name learning-loop-quality \
     --value 1 \
     --comment "usable trace for review"
   ```

7. Read it back:

   ```bash
   itmux langfuse-scores --trace-id <trace-id>
   ```

## Operations

Back up the LangFuse server like a stateful service. The official compose stack
contains Postgres, ClickHouse, Redis, and object storage services. Preserve the
volumes for Postgres, ClickHouse, and object storage before upgrades or host
migration.

Upgrade flow:

```bash
cd .agentic/langfuse/langfuse
git pull --ff-only
docker compose -f docker-compose.yml -f docker-compose.agentic-local.yml pull
docker compose -f docker-compose.yml -f docker-compose.agentic-local.yml up -d
```

Before a serious upgrade, read the LangFuse release notes for migrations or
environment changes.

Security rules:

- keep `.agentic/langfuse/langfuse/.env` ignored and permissioned as a secret
  file
- prefer Tailscale/private networking for Mac mini access
- rotate LangFuse project keys if they are pasted into chat, logs, or commits
- do not store keys in Docker images
- prefer one central project first, then split projects when operational needs
  are clear

## Troubleshooting

Cannot log in:

- read the generated `LANGFUSE_INIT_USER_EMAIL` and
  `LANGFUSE_INIT_USER_PASSWORD` from the local `.env`
- confirm those values existed before the first database initialization
- for an already initialized database, use LangFuse account recovery or the UI
  rather than editing `LANGFUSE_INIT_*` values

No traces:

- confirm `TRACE_TO_LANGFUSE=true`
- confirm the official Claude or Codex plugin is installed and enabled
- confirm the process can read `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, and
  `LANGFUSE_SECRET_KEY`
- run `curl -fsS "$LANGFUSE_BASE_URL/api/public/health"` from the same shell or
  container
- run the doctor from the same shell or container

Poor trace quality:

- confirm the trace came from the official Claude or Codex plugin
- do not use the removed direct Rust OTLP path for Claude/Codex harness traces
- verify that the run actually called tools and completed a turn

No costs:

- confirm the official plugin is producing generation observations, not only
  generic spans
- confirm the model/provider reports usage data
- inspect the trace for token usage first; cost breakdown depends on usage and
  model price mapping

Docker cannot reach LangFuse:

- use the Mac mini's Tailscale IP instead of MagicDNS
- test from inside the container with `curl`
- expose a host-local reverse proxy reachable by the container
- avoid depending on host shell exports unless the workspace launcher passes
  those variables through

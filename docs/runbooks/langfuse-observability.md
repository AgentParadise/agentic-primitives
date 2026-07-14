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
- one stable trace identity for every host and harness, defined below

Split into multiple LangFuse projects only when access control, retention, or
production/staging separation requires it.

## Trace Identity Contract

Every trace emitted to the shared project must carry an environment and two
tags. This makes host and harness filtering reliable without creating a project
per machine.

| Field | Required value | Purpose |
| --- | --- | --- |
| Environment | A stable deployment identifier | Filters all activity from one machine or workspace class. |
| `harness:<name>` | `harness:claude` or `harness:codex` | Separates the agent harnesses. |
| `host:<name>` | A stable host identifier | Separates machines sharing an environment class. |

Use lowercase, hyphenated identifiers. Do not use a personal email address or
other personal identifier in an environment, tag, user ID, trace name, or
metadata field.

The initial fleet uses this exact mapping:

| Emitter | Environment | Required tags |
| --- | --- | --- |
| MacBook Claude | `local-macbook` | `harness:claude`, `host:macbook` |
| MacBook Codex | `local-macbook` | `harness:codex`, `host:macbook` |
| Flywheel VPS Claude | `flywheel-vps` | `harness:claude`, `host:flywheel-vps` |
| Flywheel VPS Codex | `flywheel-vps` | `harness:codex`, `host:flywheel-vps` |
| Isolated Docker workspace | `docker-workspace` | harness tag plus `host:<launcher-host>` |

For a new machine, choose a new environment such as `build-vps` or
`mac-mini`, and use the same suffix in its `host:` tag. Keep this mapping in
the machine's deployment configuration and do not reuse an existing host
identifier.

## Server Setup

These steps work for a Mac mini or VPS with Docker installed.

For a centralized host, use the tracked self-hosted IaC package. It pins the
upstream LangFuse revision, limits Docker ingress to loopback, and uses
Tailscale HTTP Serve for private WireGuard-encrypted transport without issuing
a public HTTPS certificate. The Mac mini is the initial deployment target, but
the package also supports a VPS or another Docker host. Choose the MagicDNS name
clients will use before the first `init`:

```bash
export LANGFUSE_TAILSCALE_HOST=mac-mini.tailnet-name.ts.net
just langfuse-self-hosted-init
just langfuse-self-hosted-up
just langfuse-self-hosted-serve
just langfuse-self-hosted-health
```

The package lives at:

```text
infra/langfuse/self-hosted/
```

It writes `NEXTAUTH_URL=http://$LANGFUSE_TAILSCALE_HOST:19431` into
the generated `.env` on first creation. Set `LANGFUSE_BASE_URL` first so login
links, callbacks, and absolute URLs match the address used by clients.

If the `.env` already existed before changing the URL, edit only the
`NEXTAUTH_URL` value in:

```text
.agentic/langfuse/langfuse/.env
```

Then restart:

```bash
infra/langfuse/self-hosted/deploy.sh down
infra/langfuse/self-hosted/deploy.sh up
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

Recommended tailnet policy pattern, matching the HomeLab per-service tag
convention:

```jsonc
{
  "tagOwners": {
    "tag:langfuse": ["autogroup:owner"],
    "tag:agents": ["autogroup:owner"]
  },
  "grants": [
    {
      "src": ["tag:agents"],
      "dst": ["tag:langfuse"],
      "ip": ["tcp:19431"]
    },
    {
      "src": ["autogroup:admin"],
      "dst": ["tag:langfuse"],
      "ip": ["tcp:19431"]
    }
  ]
}
```

If the host already wears other service tags, add `tag:langfuse` to the same
device. `tailscale up --advertise-tags` replaces its full tag set, so pass the
complete desired list rather than only the new tag:

```bash
export TAILSCALE_ADVERTISE_TAGS=tag:existing-service,tag:langfuse
infra/langfuse/self-hosted/deploy.sh serve
```

Agent VPSs or long-lived agent hosts should wear `tag:agents` if they are not
operator-admin devices. That keeps LangFuse reachable to agent infrastructure
without opening the rest of the Mac mini.

Use the stable HTTPS MagicDNS address and the reserved LangFuse port for
`LANGFUSE_BASE_URL`, for example `http://mac-mini.tailnet-name.ts.net:19431`.
The Docker port remains loopback-only; clients reach Tailscale Serve on TCP
19431. If MagicDNS does not resolve from a client, fix that client DNS
configuration rather than bypassing the private ingress with port 3000.

Do not expose port `3000` publicly without a reverse proxy, TLS, and a clear
auth story. For public internet access, put LangFuse behind a normal HTTPS
reverse proxy and use:

```bash
export LANGFUSE_BASE_URL=https://langfuse.example.com
```

Reachability check from each client:

```bash
LANGFUSE_BASE_URL=http://mac-mini.tailnet-name.ts.net:19431 \
  scripts/langfuse-local.sh health
```

## Client Setup

Run these steps on every MacBook, Mac mini shell, VPS, or long-lived workspace
host that should emit traces.

Export the shared server URL and project keys:

```bash
export LANGFUSE_BASE_URL=http://mac-mini.tailnet-name.ts.net:19431
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_TRACING_ENVIRONMENT=local-macbook
export TRACE_TO_LANGFUSE=true
```

Set a unique environment per host or workspace class. Follow the trace identity
contract above rather than generic values such as `vps`:

```bash
export LANGFUSE_TRACING_ENVIRONMENT=flywheel-vps
export LANGFUSE_TRACING_ENVIRONMENT=docker-workspace
```

The official plugins use harness-specific variables for tags. A wrapper can
set them for a one-off invocation, but do not make wrappers the primary
installation mechanism: agents launched from tmux, a scheduler, or another
agent commonly invoke `codex` or `claude` directly. Configure each official
plugin persistently as described below.

```bash
# Codex
export LANGFUSE_CODEX_ENVIRONMENT="$LANGFUSE_TRACING_ENVIRONMENT"
export LANGFUSE_CODEX_TAGS="harness:codex,host:flywheel-vps"

# Claude Code
export CC_LANGFUSE_TAGS="harness:claude,host:flywheel-vps"
```

Set `LANGFUSE_USER_ID` only when it is needed for a non-personal, stable actor
identifier. The initial local setup uses `neuralempowerment`, not an email
address.

Check readiness:

```bash
scripts/langfuse-observability-doctor.sh --json
```

On minimal VPS images or containers without Rust:

```bash
scripts/langfuse-observability-doctor.sh --json --no-tests
```

## Claude Code

Install the official plugin at **user** scope, not a project or local scope.
Project/local installation observes only sessions in that project and leaves
the rest of the machine uninstrumented:

```bash
claude plugin marketplace add langfuse/Claude-Observability-Plugin
claude plugin install langfuse-observability@langfuse-observability --scope user \
  --config LANGFUSE_SECRET_KEY=sk-lf-... \
  --config LANGFUSE_PUBLIC_KEY=pk-lf-... \
  --config LANGFUSE_BASE_URL=http://mac-mini.tailnet-name.ts.net:19431 \
  --config LANGFUSE_USER_ID=neuralempowerment
```

Use Claude's plugin configuration flow for the key material. Set the
non-secret machine identity in the user settings environment so all new Claude
sessions receive it:

```json
{
  "env": {
    "LANGFUSE_TRACING_ENVIRONMENT": "flywheel-vps",
    "CC_LANGFUSE_TAGS": "harness:claude,host:flywheel-vps"
  }
}
```

Existing Claude sessions cannot load a plugin installed later. Start a new
session after installing or changing the configuration. A launcher wrapper may
still override these values for an isolated workspace, but it is not required
for ordinary terminal, tmux, or delegated sessions.

For a host-specific wrapper, set `LANGFUSE_BASE_URL`,
`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_USER_ID`,
`LANGFUSE_TRACING_ENVIRONMENT`, and `CC_LANGFUSE_TAGS`. The wrapper's explicit
environment must take precedence over stale plugin defaults so a machine does
not accidentally send traces to a previous LangFuse server.

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
persist the tracing plugin's configuration in `~/.codex/langfuse.json`. The
official plugin reads this file on every Stop hook, so direct Codex invocations
do not depend on a shell wrapper:

```json
{
  "enabled": true,
  "public_key": "pk-lf-...",
  "secret_key": "sk-lf-...",
  "base_url": "http://mac-mini.tailnet-name.ts.net:19431",
  "environment": "flywheel-vps",
  "user_id": "neuralempowerment",
  "tags": ["harness:codex", "host:flywheel-vps"],
  "metadata": {"host": "flywheel-vps", "deployment": "flywheel-vps"},
  "fail_on_error": false
}
```

Restrict the file to its owner (`chmod 600 ~/.codex/langfuse.json`). This
plugin configuration format stores project credentials, so on macOS generate
it from Keychain and on a VPS generate it from the protected host secret file.
Do not commit it or put it in a workspace image.

On the first install, Codex requires the Stop hook to be trusted. Confirm the
hook through the normal Codex prompt, then verify a state entry exists in
`~/.codex/config.toml` for
`tracing@codex-observability-plugin:hooks/hooks.json:stop:0:0`. An installed
plugin without that trusted hook state produces no traces. Keep
`plugin_hooks = true` under `[features]`; a root-level `plugin_hooks` setting
is ignored by current Codex releases.

Like Claude, an already-running Codex session does not gain tracing
retroactively. Start a new session after enabling the plugin or changing its
configuration.

## Historical Backfill

LangFuse cannot reconstruct traces that were never emitted, but the original
Claude and Codex JSONL files can be imported after observability is installed.
Use the backfill command rather than copying data into LangFuse directly: it
invokes the official plugins and preserves their trace, tool, usage, and
session semantics.

Preview a bounded batch first:

```bash
scripts/langfuse-backfill.sh --harness all --limit 10 --newest
```

Submit that batch only after reviewing the paths:

```bash
scripts/langfuse-backfill.sh --harness all --limit 10 --newest --apply
```

For an older archive, use `--oldest`; use `--limit 0 --apply` only after a
small batch has been verified in LangFuse. The default `--max-turns 100`
prevents a small number of long conversations from unexpectedly creating a
large import; increase it deliberately or use `0` for no turn cap. Codex
backfill supports rollout files containing both a `session_meta` record and a
`task_started` event; older Codex rollout schemas are skipped and need a
format adapter before they can be imported. Preview also excludes sources
already recorded by the official plugin state. Codex records completed source turns in a neighbouring
`.langfuse` ledger and Claude records per-transcript offsets. The command also
appends a local submission manifest at
`~/.local/state/agentic-primitives/langfuse-backfill.jsonl`. Preserve those
files to make repeated runs resumable rather than duplicate historical traces.

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
  -e LANGFUSE_BASE_URL=http://mac-mini.tailnet-name.ts.net:19431 \
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
   - the expected `Environment`, `harness:<name>`, and `host:<name>` tags

5. Query the traces from Agentic Primitives:

   ```bash
   itmux langfuse-traces --limit 20 --output summary
   itmux langfuse-traces --harness codex --environment local-macbook
   itmux langfuse-trace --trace-id <trace-id> --include-scores --output summary
   itmux langfuse-sessions --harness codex --environment local-macbook
   ```

   `langfuse-sessions` groups the per-turn traces emitted by the official
   plugins using LangFuse `session_id` and returns turn, token, cost, tool, and
   score rollups. `session_id` is the bridge to the separate raw session-log
   and replay store; it is not a replacement for those artifacts, and it is
   not assumed to equal an `itmux` run id.

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

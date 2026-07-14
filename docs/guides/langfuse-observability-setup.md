# LangFuse Observability Setup

This guide is the packaged setup path for LangFuse-backed agent observability
on MacBooks, Mac Mini/VPS hosts, and isolated Docker workspaces.

For topology and operations details, including centralized Mac mini/VPS
hosting and Tailscale access, see
`docs/runbooks/langfuse-observability.md`.

For Claude Code and Codex, rich traces come from LangFuse's official plugins:

- Claude Code: `langfuse/Claude-Observability-Plugin`
- Codex: `langfuse/codex-observability-plugin`

`itmux` keeps the local observability primitive: `--observability-file` for
canonical `AgentRunEvent` JSONL, `--observability-syntropic-file` for
Syntropic137 HookWatcher-compatible JSONL, and `itmux langfuse-*` commands for
agent-readable LangFuse query and score loops.

## Decision Context

ADR-039 is the source of truth for why official plugins are canonical. The
short version:

- The direct Rust OTLP writer produced valid but low-value LangFuse traces with
  generic spans and missing native harness context.
- The official Claude and Codex plugins produced useful traces with real
  turns/generations, tool calls, usage, costs, and session grouping.
- The direct LangFuse writer has been removed from the public `itmux` run
  contract and CLI surface.
- Local JSONL and Syntropic137 JSONL fanout remain backend-independent evidence
  channels.

## Runtime Environment

Do not put LangFuse credentials in recipes, specs, Docker images, committed
files, or experiment artifacts.

Required values for query tools and official plugin setup:

- `LANGFUSE_BASE_URL`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

Recommended values:

- `LANGFUSE_TRACING_ENVIRONMENT`, for example `local-macbook`, `mac-mini`,
  `flywheel-vps`, or `docker-workspace`
- `LANGFUSE_PROJECT_ID`, useful for dashboard URLs and operator references
- `TRACE_TO_LANGFUSE=true`, used by official plugins to opt into tracing

`LANGFUSE_BASE_URL` should be the LangFuse origin, for example
`http://localhost:3000` for the local Docker Compose stack.

## Setup Doctor

Run the doctor on every fresh MacBook, VPS, or Docker workspace:

```bash
scripts/langfuse-observability-doctor.sh
scripts/langfuse-observability-doctor.sh --json
```

The doctor is read-only and secret-safe. It reports:

- Claude/Codex command availability
- Claude plugin runtime prerequisites, installation, hook files, non-sensitive
  config presence, and whether a secret is available through env for smoke
  runs
- Codex Node 22+ and plugin hook readiness
- `LANGFUSE_*` set/missing state without printing values
- JSONL and Syntropic137 fanout support
- `agentic-langfuse` MCP server presence
- focused `itmux` packaging tests when Cargo is available

Claude sensitive config may live in Claude's own secret store. The doctor does
not read secret values from that store; it reports `secret_key_available_via_env`
for deterministic MacBook/VPS/Docker smoke runs. A final Claude trace smoke is
the proof that the configured secret path works.

On minimal hosts without Rust:

```bash
scripts/langfuse-observability-doctor.sh --json --no-tests
```

## Platform Recipes

### MacBook

Use the local Docker Compose stack for a self-contained backend, install the
official Claude/Codex plugins on the host, and keep secrets in the OS secret
store or an ignored shell environment:

```bash
scripts/langfuse-local.sh init
scripts/langfuse-local.sh up
scripts/langfuse-local.sh smoke
```

`smoke` loads the ignored local LangFuse `.env` produced by the bootstrap and
runs the doctor without printing key values.

### Mac Mini or VPS

Use the same repository commands, but point `LANGFUSE_BASE_URL` at the deployed
LangFuse origin and provide keys through the host secret manager or service
environment:

```bash
export LANGFUSE_BASE_URL=https://langfuse.example.com
export LANGFUSE_PUBLIC_KEY=...
export LANGFUSE_SECRET_KEY=...
export LANGFUSE_TRACING_ENVIRONMENT=vps
export TRACE_TO_LANGFUSE=true
scripts/langfuse-observability-doctor.sh --json --no-tests
```

Then run the full doctor on hosts with Rust/Cargo available.

### Isolated Docker Workspace

Do not bake LangFuse secrets into the image. Pass the same `LANGFUSE_*` values
at workspace launch time or through the workspace's mounted secret/config
surface, then run:

```bash
scripts/langfuse-observability-doctor.sh --json --no-tests
```

Docker workspaces should show JSONL/Syntropic fanout and MCP server presence.
Official Claude/Codex plugin readiness still depends on the harness config
mounted into that workspace.

## Local LangFuse Backend

Use the same Docker Compose stack for local MacBook experiments and future
portable workspace setup:

```bash
scripts/langfuse-local.sh up
```

Open:

```text
http://localhost:3000
```

Then create a project and API keys in LangFuse, export the runtime environment,
and run the doctor again.

## Claude Code

Install and configure LangFuse's official Claude Code plugin using Claude's
plugin flow:

```bash
claude plugin marketplace add langfuse/Claude-Observability-Plugin
claude plugin install langfuse-observability@langfuse-observability
```

Use Claude's plugin configuration flow for the secret key so credentials live
in the OS secret store rather than the repo. For local shell-driven runs, also
export the shared `LANGFUSE_*` values so query tools and the doctor can verify
readiness.

## Agent Learning-Loop Access

Install Agentic Primitives' observability plugin when Claude agents need trace
discovery, session reports, aggregate learning-loop reports, and feedback
scores through the `agentic-langfuse` MCP server:

```bash
claude plugin marketplace add AgentParadise/agentic-primitives
claude plugin install observability@agentic-primitives --scope user
```

The MCP server is launched through `uv run --script`, so `uv` is required on
each client host. It uses the same protected `LANGFUSE_*` configuration as the
harness plugins. Codex and other MCP clients can use the `uv` configuration in
`plugins/observability/README.md`.

Expected LangFuse trace shape:

- Claude turn / generation observations
- native tool observations such as `Tool: Read`
- model, usage, and cost metadata
- session/environment grouping
- `telemetry.sdk.language=python`, because the official Claude plugin exports
  through LangFuse's Python SDK path

## Codex

Install and enable LangFuse's official Codex plugin:

```toml
[features]
plugin_hooks = true

[plugins."tracing@codex-observability-plugin"]
enabled = true
```

Place this in `~/.codex/config.toml` or a project `.codex/config.toml`, then
ensure the Codex plugin can read the shared `LANGFUSE_*` environment or its
own LangFuse config file.

Expected LangFuse trace shape:

- `Codex Turn` observations
- tool observations such as `exec_command`
- model, usage, and cost metadata
- session/environment grouping
- `telemetry.sdk.language=nodejs`, because the official Codex plugin exports
  through LangFuse's Node.js SDK path

## Local JSONL Fanout

Use JSONL fanout for durable local evidence and Syntropic137 ingestion:

```bash
itmux run \
  --recipe /path/to/recipe \
  --task "Implement the change" \
  --observability-file /tmp/agentic-events.jsonl \
  --observability-syntropic-file /tmp/syntropic-events.jsonl \
  --result-file /tmp/agentic-result.json
```

For Codex structured local events:

```bash
itmux codex-exec \
  --prompt "Reply exactly: OK" \
  --observability-file /tmp/codex-events.jsonl \
  --observability-syntropic-file /tmp/codex-syntropic-events.jsonl \
  --result-file /tmp/codex-result.json
```

These local files are not a replacement for official LangFuse traces. They are
the backend-independent audit trail and Syntropic137 bridge.

## Agent Query Tools

After official plugins export traces, agents can query LangFuse through CLI or
MCP.

Discover traces:

```bash
itmux langfuse-traces --limit 20 --output summary
itmux langfuse-traces --harness codex --environment local-macbook
```

Inspect one trace:

```bash
itmux langfuse-trace --trace-id <trace-id> --include-scores --output summary
```

Write/read score feedback:

```bash
itmux langfuse-score --trace-id <trace-id> --name learning-loop-quality --value 1 --comment "usable"
itmux langfuse-scores --trace-id <trace-id>
```

The `agentic-langfuse` MCP server wraps the same query and score flows for
Claude, Codex, or other MCP clients. It is launched through `uv run --script`;
install `uv` on every host that uses the observability plugin.

## Final Smoke

After setup changes, validate only the current packaged path:

1. Run `scripts/langfuse-observability-doctor.sh --json`.
2. Produce one Claude trace through the official Claude plugin.
3. Produce one Codex trace through the official Codex plugin.
4. Verify both traces show native turns/tools plus usage/cost in LangFuse.
5. Query both traces with `itmux langfuse-trace`.
6. Run one JSONL/Syntropic fanout command and verify both local files receive
   events.

Do not use removed direct LangFuse writer flags as an acceptance gate.

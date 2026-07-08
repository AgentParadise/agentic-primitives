# LangFuse Observability Setup

This guide documents the secret-safe setup path for LangFuse-backed agent
observability. It applies to MacBooks, Mac Minis, VPS hosts, and isolated
Docker workspaces.

For Claude Code and Codex, the canonical rich-trace path is LangFuse's
official marketplace plugins. Those plugins read each harness' native
transcript or rollout and export LangFuse-native turns, generations, tool
calls, token usage, costs, timings, and session grouping. The `itmux`
`--observability-langfuse` OTLP exporter remains useful for local backend
smoke tests, generic OTEL collectors, Syntropic137 ingestion, and harnesses
without an official LangFuse plugin, but it should not be enabled for the same
Claude/Codex run that is already traced by an official LangFuse plugin.

## Runtime Environment

Do not put LangFuse credentials in recipes, specs, Docker images, committed
files, or experiment artifacts.

There are two credential paths:

1. **Official Claude/Codex plugin config**, used for canonical rich traces.
2. **agentic-primitives runtime env**, used by the fallback Rust OTLP exporter,
   `itmux langfuse-*` query commands, MCP learning-loop tools, and local smoke
   scripts.

For the agentic-primitives runtime env, required values are:

- `LANGFUSE_BASE_URL`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

Recommended values are:

- `LANGFUSE_TRACING_ENVIRONMENT`, used by local tooling and the official Codex
  plugin to label traces by environment, for example `local-macbook`,
  `mac-mini`, `vps`, or `docker-workspace`.

- `LANGFUSE_PROJECT_ID`, used only to report human-facing trace links in the
  final observability bundle.
- `TRACE_TO_LANGFUSE=true`, used by the official Claude and Codex plugins to
  opt into exporting a session or project.

`LANGFUSE_BASE_URL` should be the LangFuse origin, for example
`https://langfuse.example.com` or `http://localhost:3000` for the local Docker
Compose stack.

## Canonical Rich Tracing

Official references:

- Claude Code:
  <https://langfuse.com/integrations/developer-tools/claude-code>
- Codex: <https://langfuse.com/integrations/developer-tools/codex>

### Claude Code

Use LangFuse's maintained Claude Code marketplace plugin for real Claude
sessions:

```bash
claude plugin marketplace add langfuse/Claude-Observability-Plugin
claude plugin install langfuse-observability@langfuse-observability
```

Restart Claude Code after installation. The plugin prompts for
`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL`; the
secret key is stored in the OS keychain by the plugin. Reconfigure later with:

```text
/plugin configure langfuse-observability@langfuse-observability
```

You can also pass plugin config during install:

```bash
claude plugin install langfuse-observability@langfuse-observability \
  --config LANGFUSE_PUBLIC_KEY=pk-lf-... \
  --config LANGFUSE_SECRET_KEY=sk-lf-... \
  --config LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

The official Claude plugin requires either `uv` on `PATH` or Python 3.10+ with
`langfuse>=4.0,<5` available. It also accepts optional controls such as
`LANGFUSE_USER_ID`, `CC_LANGFUSE_DEBUG`, `CC_LANGFUSE_MAX_CHARS`,
`CC_LANGFUSE_SKILL_TAGS`, and `CC_LANGFUSE_CAPTURE_SKILL_CONTENT`. Treat those
as plugin configuration, not as requirements for the Rust fallback exporter.

The expected trace shape is one Claude turn per trace, generation observations
for assistant messages, `Tool: <name>` observations with inputs and outputs,
session grouping, usage, and costs when the transcript carries usage values.

### Codex

Use LangFuse's maintained Codex marketplace plugin for real Codex sessions:

```bash
codex plugin marketplace add langfuse/codex-observability-plugin
```

The official Codex plugin currently requires Node.js 22+ and a Codex build with
plugin hook support.

Enable Codex plugin hooks globally in `~/.codex/config.toml`, or per project in
`<project>/.codex/config.toml`:

```toml
[features]
plugin_hooks = true

[plugins."tracing@codex-observability-plugin"]
enabled = true
```

Run Codex with tracing env enabled:

```bash
export TRACE_TO_LANGFUSE=true
export LANGFUSE_BASE_URL=http://localhost:3000
export LANGFUSE_PUBLIC_KEY=...
export LANGFUSE_SECRET_KEY=...
export LANGFUSE_TRACING_ENVIRONMENT=local-macbook
codex
```

Codex can also read `~/.codex/langfuse.json` or
`<project>/.codex/langfuse.json`. Configuration precedence is defaults, then
global JSON config, then project JSON config, then environment variables.
`LANGFUSE_CODEX_*` variables override matching standard `LANGFUSE_*` variables
for Codex only, which is useful when Claude and Codex should write to separate
projects or environments on the same machine.

For durable machines, load the same variables from Keychain, a systemd
environment file owned by the operator, or the workspace orchestrator's secret
injection. The expected trace shape is one Codex turn per trace, generation
observations with model/usage/cost, tool observations such as `exec_command` or
MCP calls, subagent grouping where present, and sidecar deduplication.

### Exporter Ownership

Use only one rich LangFuse writer per run by default:

| Path | Default role |
|---|---|
| Official Claude plugin | Canonical rich LangFuse traces for Claude Code |
| Official Codex plugin | Canonical rich LangFuse traces for Codex |
| `--observability-file` JSONL | Durable local evidence and Syntropic137/source-of-truth fanout |
| `--observability-syntropic-file` JSONL | Syntropic137 HookWatcher-compatible session/tool JSONL |
| `--observability-langfuse` Rust OTLP | Explicit fallback, collector, backend smoke, or unsupported harness path |

It is safe to keep JSONL fanout enabled alongside an official plugin. It is not
the default to send the same Claude/Codex run through both the official plugin
and the Rust OTLP writer, because that creates duplicate or less-useful
LangFuse traces.

The `itmux` CLI enforces that default for human-facing runs: when
`TRACE_TO_LANGFUSE=true` indicates an official LangFuse plugin is active,
`--observability-langfuse` suppresses the Rust OTLP writer while preserving
`--observability-file` JSONL fanout. Use `--observability-langfuse-force` only
when deliberately testing fallback OTLP or sending the same normalized events
to a collector/Syntropic137 path.

For Syntropic137, prefer `--observability-syntropic-file` alongside the
canonical `--observability-file`. The canonical file remains the full
`AgentRunEvent` artifact for replay and debugging. The Syntropic file emits
top-level `event_type`, `session_id`, and `timestamp` records compatible with
Syntropic137's existing HookWatcher for session and tool timeline ingestion.
It also emits `token_usage` rows for forward compatibility, but the current
Syntropic137 HookWatcher does not parse those rows until its hook event map
adds `token_usage`; Syntropic137's transcript/OTLP lanes remain the token/cost
source meanwhile.

## macOS Keychain Setup

On MacBooks and Mac Minis, store the values in Keychain and export them only for
the shell that runs the smoke test. Use `-w` as the last `security` argument so
Keychain prompts for each value instead of receiving it through shell history or
process arguments:

```bash
# Prompt value: https://langfuse.example.com
security add-generic-password -U -a "$USER" \
  -s agentic-primitives/langfuse/base-url \
  -w

# Prompt value: pk-lf-...
security add-generic-password -U -a "$USER" \
  -s agentic-primitives/langfuse/public-key \
  -w

# Prompt value: sk-lf-...
security add-generic-password -U -a "$USER" \
  -s agentic-primitives/langfuse/secret-key \
  -w

# Prompt value: local
security add-generic-password -U -a "$USER" \
  -s agentic-primitives/langfuse/tracing-environment \
  -w

# Optional. Set this when trace links should point directly into the project UI.
# Prompt value: project id
security add-generic-password -U -a "$USER" \
  -s agentic-primitives/langfuse/project-id \
  -w
```

Load the environment without printing secret values:

```bash
export LANGFUSE_BASE_URL="$(
  security find-generic-password -a "$USER" \
    -s agentic-primitives/langfuse/base-url -w
)"
export LANGFUSE_PUBLIC_KEY="$(
  security find-generic-password -a "$USER" \
    -s agentic-primitives/langfuse/public-key -w
)"
export LANGFUSE_SECRET_KEY="$(
  security find-generic-password -a "$USER" \
    -s agentic-primitives/langfuse/secret-key -w
)"
export LANGFUSE_TRACING_ENVIRONMENT="$(
  security find-generic-password -a "$USER" \
    -s agentic-primitives/langfuse/tracing-environment -w
)"
export LANGFUSE_PROJECT_ID="$(
  security find-generic-password -a "$USER" \
    -s agentic-primitives/langfuse/project-id -w 2>/dev/null || true
)"
```

Confirm only set/missing state:

```bash
for name in \
  LANGFUSE_BASE_URL \
  LANGFUSE_PUBLIC_KEY \
  LANGFUSE_SECRET_KEY \
  LANGFUSE_TRACING_ENVIRONMENT \
  LANGFUSE_PROJECT_ID
do
  if [ -n "${!name:-}" ]; then
    printf '%s=set\n' "$name"
  else
    printf '%s=missing\n' "$name"
  fi
done
```

## VPS and Docker Setup

On a VPS, inject these variables through the host's secret manager, systemd
environment, or the operator's shell. Keep secrets out of unit files that are
committed to source control.

For Docker workspaces, pass environment variables into the container at runtime
instead of baking them into the image:

```bash
docker run --rm \
  -e LANGFUSE_BASE_URL \
  -e LANGFUSE_PUBLIC_KEY \
  -e LANGFUSE_SECRET_KEY \
  -e LANGFUSE_TRACING_ENVIRONMENT \
  -e LANGFUSE_PROJECT_ID \
  agentic-primitives-workspace:local
```

When an orchestrator launches the workspace, the same rule applies: the contract
is the environment variable names, not a committed secret file.

## Local LangFuse Bootstrap

For local integration work, use the repo wrapper around LangFuse's official
Docker Compose deployment:

```bash
scripts/langfuse-local.sh init
scripts/langfuse-local.sh start
scripts/langfuse-local.sh status
```

The wrapper clones the official LangFuse repository into `.agentic/langfuse/`,
which is ignored by git. It does not vendor LangFuse's compose file into this
repository and does not commit secrets. For local smoke testing, it writes an
ignored Compose override and `.env` into the cloned LangFuse checkout. The
override exposes only LangFuse web on host port `3000`; Postgres, ClickHouse,
Redis, MinIO, and the worker stay internal to the Compose network to avoid
MacBook/VPS port conflicts.

After startup, run:

```bash
scripts/langfuse-local.sh smoke
```

The smoke uses the provisioned local project/API keys, exports a minimal
fallback OTLP run through `itmux codex-exec --observability-langfuse`, polls
LangFuse for discoverability through `itmux langfuse-trace --api legacy-trace`,
and checks that the emitted trace URL resolves. This proves local LangFuse
ingestion and the fallback exporter. It is not the canonical rich trace test
for Claude or Codex.

For rich local validation, install or directly invoke the official LangFuse
Claude/Codex plugins against the same local project. The local E2E experiment
that proves this path is:

```text
experiments/2026-07-08--langfuse--official-plugin-e2e-local
```

Known-good local traces from that experiment:

- Claude official plugin:
  `76a54f7c977ae138c22ebae34b05e047`
- Codex official plugin:
  `6905cfb7d1b969a0214e613383748ce7`

The follow-up real-session experiment that proves marketplace-installed
plugins against local LangFuse is:

```text
experiments/2026-07-08--langfuse--official-plugin-real-session
```

Known-good local real-session traces from that experiment:

- Claude official plugin:
  `0e553fc833c71639acd03be9807eb616`
- Codex official plugin:
  `b3d2561d7c0557c12fd427c02a16e2f3`

One setup caveat remains: in that run, Claude local plugin installation
succeeded, but install-time `--config` reported the userConfig values still
unset. The successful trace used the official hook's plain environment
fallback. For durable setup, prefer `/plugin configure` or re-test install-time
config on the target machine before relying on stored plugin config alone.

This local bootstrap is for development and smoke testing. For production or
durable Mac Mini hosting, review LangFuse's current self-hosting guidance and
set persistent secrets, storage, backups, and upgrade policy explicitly.

## Fallback OTLP Smoke

Use this section when validating the reusable Rust OTLP exporter, a generic
collector, Syntropic137 fanout, or an unsupported harness. Do not use this as
the primary proof of rich Claude/Codex LangFuse UX when the official plugins
are available.

After the environment is loaded, run a smoke against the fallback exporter
path:

```bash
mkdir -p /tmp/agentic-langfuse-smoke

itmux codex-exec \
  --prompt "Reply exactly: LANGFUSE_SMOKE_OK" \
  --observability-file /tmp/agentic-langfuse-smoke/events.jsonl \
  --observability-syntropic-file /tmp/agentic-langfuse-smoke/syntropic-events.jsonl \
  --observability-langfuse \
  --result-file /tmp/agentic-langfuse-smoke/result.json
```

For a Codex recipe that should use the same normalized event fanout through the
standard run surface, use `--codex-mode exec`:

```bash
itmux run \
  --recipe /path/to/codex-recipe \
  --task "Reply exactly: LANGFUSE_CODEX_RUN_OK" \
  --codex-mode exec \
  --observability-file /tmp/agentic-langfuse-smoke/codex-run-events.jsonl \
  --observability-langfuse \
  --result-file /tmp/agentic-langfuse-smoke/codex-run-result.json
```

This mode is only valid when the recipe default agent is Codex. The default
Codex `tui` mode preserves the interactive Docker workspace path and currently
has only coarse lifecycle observability. The `exec` mode runs `codex exec
--json`, normalizes its structured event stream, and fans those events out
through the same file and fallback OTLP exporters used by Claude workspace
runs.

For Claude transcript evidence, normalize a Claude JSONL transcript through the
same exporter fanout:

```bash
itmux claude-transcript \
  --transcript /path/to/claude-transcript.jsonl \
  --run-id run-claude-smoke \
  --observability-file /tmp/agentic-langfuse-smoke/claude-events.jsonl \
  --observability-langfuse \
  --result-file /tmp/agentic-langfuse-smoke/claude-result.json
```

This fallback path maps Claude `tool_use`/`tool_result` transcript items to normalized
tool spans and `result.modelUsage` entries to shared `token_usage` events with
`harness=claude`, `provider=anthropic`, model names, token counts, cached-token
counts, and cost data. Transcript-derived tool input values and result content
are redacted before export; tool input spans preserve only shape metadata such
as object key names. The result `session_log` records a summary, not the raw
transcript. This is the current reusable export path for Claude-shaped
telemetry. For production-quality LangFuse UX, prefer the official Claude
plugin because it reconstructs LangFuse-native turns, generations, and tools
from the Claude transcript directly.

For `itmux run` with Claude, the workspace executor also drains the Claude
observability hook sink while the await loop is still polling. When the hook
stream includes a Claude `transcript_path`, `itmux run` incrementally reads new
transcript bytes from the workspace and normalizes them through the same
redacted Claude transcript observer before fanout. Terminalization performs a
final delta drain as a safety net. This gives completed interactive Claude
workspace runs token, cost, tool, and hook telemetry in the same file/LangFuse
exporters, and hook/message-usage events can arrive before the `await` phase
ends. If the transcript contains aggregate `result.modelUsage`, that aggregate
is used by the replay path. If an interactive transcript only contains
assistant message usage, the workspace-run drain emits deduplicated
message-level token usage so LangFuse still receives a native generation row.

Also follow the dedicated ingestion experiment at
`experiments/2026-07-07--langfuse--otel-ingestion-smoke/eval-pack.md` against
the same reachable backend.

Passing fallback exporter criteria:

- the command exits successfully;
- `/tmp/agentic-langfuse-smoke/events.jsonl` contains normalized run events;
- `/tmp/agentic-langfuse-smoke/result.json` contains a `langfuse_otlp` exporter
  report with `status` set to `ok`;
- `events_exported` is greater than zero;
- when `LANGFUSE_PROJECT_ID` is set, the report includes a LangFuse trace link.
- `itmux langfuse-trace` can query the trace. For LangFuse v3 Docker Compose,
  use `--api legacy-trace`; Observations API v2 requires LangFuse v4 write mode.
- the emitted trace link resolves in the LangFuse UI.
- token usage appears as native LangFuse generation data when the fallback
  harness path provides model/usage metadata. If the LangFuse UI shows generic
  `tool_start`, `tool_end`, or `token_usage` observations without meaningful
  root input/output, that is a fallback exporter limitation, not a passing
  rich Claude/Codex trace.
- `itmux langfuse-score` can attach a trace-scoped score for evaluator or
  operator feedback, and `itmux langfuse-scores` can read that score back for
  the next agent loop.

## Agent Trace and Feedback Queries

Use compact trace summaries when an agent needs to inspect a run without
loading the full LangFuse response:

```bash
itmux langfuse-trace \
  --api legacy-trace \
  --output summary \
  --run-id run-f7ae62c8
```

Include trace-scoped feedback scores in the same payload for a one-call
retrospective:

```bash
itmux langfuse-trace \
  --api legacy-trace \
  --output summary \
  --include-scores \
  --run-id run-f7ae62c8
```

Use trace discovery before drilling into a specific run:

```bash
itmux langfuse-traces --limit 10 --harness codex
itmux langfuse-traces --limit 10 --harness claude
```

Use scores to write durable learning-loop feedback back onto a trace. Supplying
`--score-id` makes retries idempotent:

```bash
itmux langfuse-score \
  --run-id run-f7ae62c8 \
  --score-id agentic-learning-loop-probe-run-f7ae62c8 \
  --name agentic.learning_loop_probe \
  --value 1 \
  --data-type boolean \
  --comment "local evaluator accepted trace"
```

Read the feedback back through the same primitive:

```bash
itmux langfuse-scores \
  --run-id run-f7ae62c8 \
  --score-ids agentic-learning-loop-probe-run-f7ae62c8 \
  --name agentic.learning_loop_probe \
  --data-type boolean
```

## MCP Trace Tools

The `observability` Claude plugin registers an `agentic-langfuse` MCP server for
agents that should query traces as tools instead of shelling out. Codex or other
MCP clients can launch the same stdio server directly. It prefers the same
`itmux langfuse-*` commands documented above when `itmux` is available, and
falls back to direct LangFuse public API calls when packaged without the binary.
Setup is the same: load `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, and
`LANGFUSE_SECRET_KEY`, and set `ITMUX_BIN` if the `itmux` binary is not on
`PATH` and you want the richer CLI-shaped summary path.

MCP tools:

- `agentic_langfuse_trace_discovery`: list recent traces with
  harness/provider/model/environment filters.
- `agentic_langfuse_trace_summary`: fetch the compact summary for one run or
  trace, optionally with scores.
- `agentic_langfuse_scores`: read trace-scoped feedback.
- `agentic_langfuse_score_feedback`: write idempotent evaluator feedback.
- `agentic_langfuse_learning_loop_report`: discover recent traces, summarize
  the top rows, and return aggregate cost, token, generation, tool, and score
  rollups plus default learning-loop recommendations for retrospective agents.

Codex MCP config example:

```toml
[mcp_servers.agentic-langfuse]
command = "python3"
args = ["/path/to/agentic-primitives/plugins/observability/mcp/langfuse_server.py"]
env = { ITMUX_BIN = "/path/to/agentic-primitives/providers/workspaces/interactive-tmux/driver-rs/target/release/itmux" }
```

For an agent loop that needs a compact retrospective across recent runs, call
`agentic_langfuse_learning_loop_report` with optional filters such as
`harness=codex`, `harness=claude`, `provider`, `model`, or `environment`. The
tool first uses trace discovery, then drills into the selected traces with
score inclusion enabled by default. The returned summary includes aggregate
token count, calculated cost, generation count, agent-tool success/failure
counts, per-trace generation details, and trace-scoped feedback scores.
`include_insights` defaults to true and adds cost/token hotspots, missing
token/cost/model coverage, unscored traces, and failed agent-tool
recommendations. Pass `include_insights=false` when a consumer needs a raw
rollup without heuristic guidance.

Passing rich backend criteria:

- LangFuse receives traces from the official Claude and Codex plugins;
- the trace is visible and queryable in the LangFuse UI;
- `itmux langfuse-trace --output summary --run-id <run_id>` returns the
  learning-loop summary for the exported trace after the expected ingestion
  delay;
- the trace has at least three child observations;
- the trace has at least one `GENERATION` observation for usage-bearing model
  calls, with nonzero native token fields and calculated cost when the model is
  known to LangFuse;
- root trace input/output and observation input/output are populated for real
  harness turns;
- `summary.generations.by_model` and `summary.generations.sequence` expose
  model ids, harness/provider, input/output/total tokens, cached-token details,
  split input/output costs, total costs, pricing tier, and unit for Codex and
  Claude traces;
- Codex recipes that run with `--codex-mode exec` and Claude recipes that run
  through the interactive workspace both query back through
  `itmux langfuse-trace --output summary` with harness/provider/model,
  generation cost, and split `agent_tools`/`harness_tools` where applicable;
- the reported trace link resolves when project id metadata is available.

`okrs-51p.9` remains open until the official-plugin setup is proven for real
Claude and Codex sessions against LangFuse Cloud or the planned self-hosted Mac
Mini deployment. The fallback OTLP smoke alone is not sufficient to close it.

## Agent Trace Query

Use the same secret injection model as export:

```bash
itmux langfuse-traces --limit 10 --harness claude
```

`itmux langfuse-traces` lists recent traces from `/api/public/traces` and
returns a compact summary by default. Each row includes the trace id, run id,
session id, timestamp, environment, harness, provider, model, total cost,
latency, observation count, and LangFuse UI path. Use `--harness codex` or
`--harness claude` to split Codex and Claude traces before selecting a run for
deeper inspection. Additional filters are available for provider, model, and
environment.

```bash
itmux langfuse-trace \
  --run-id <itmux-run-id> \
  --api legacy-trace \
  --output summary
```

The command derives the deterministic LangFuse trace id from the run id and
queries LangFuse with default bounded `fromStartTime` and `toStartTime` values.
You can also pass `--trace-id <32-hex-trace-id>` directly. For self-hosted
LangFuse deployments that do not expose the v2 observations endpoint, pass
`--api legacy-trace` to query `/api/public/traces/{traceId}`.

`--output summary` returns only `{ok, request, summary}`. That is the preferred
shape for agents because it avoids pulling the raw backend response into the
prompt context. The summary includes observation names/types, environment,
harnesses, providers, model names, model ids, token totals, calculated total
cost, operation/tool counts, agent-visible tool calls, harness plumbing, and a
compact event sequence ordered by `agentic.event.seq` when available. Use
`--output full` when debugging backend payload shape.

LangFuse documentation says newly ingested data is typically queryable after
about 15-30 seconds, so backend smoke runs should wait before checking
discoverability.

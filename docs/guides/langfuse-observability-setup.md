# LangFuse Observability Setup

This guide documents the secret-safe setup path for running the reusable
observability exporter against a real LangFuse backend. It applies to MacBooks,
Mac Minis, VPS hosts, and isolated Docker workspaces.

## Required Runtime Environment

The exporter reads credentials from environment variables at runtime. Do not put
these values in recipes, specs, CLI arguments, Docker images, committed files,
or experiment artifacts.

Required:

- `LANGFUSE_BASE_URL`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_TRACING_ENVIRONMENT`

Optional:

- `LANGFUSE_PROJECT_ID`, used only to report human-facing trace links in the
  final observability bundle.

`LANGFUSE_BASE_URL` should be the LangFuse origin, for example
`https://langfuse.example.com`. The exporter derives the OTLP traces endpoint
from that origin.

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

The smoke uses the provisioned local project/API keys, exports a current
`itmux codex-exec --observability-langfuse` run, polls LangFuse for
discoverability through `itmux langfuse-trace --api legacy-trace`, and checks
that the emitted trace URL resolves.

This local bootstrap is for development and smoke testing. For production or
durable Mac Mini hosting, review LangFuse's current self-hosting guidance and
set persistent secrets, storage, backups, and upgrade policy explicitly.

## Real Backend Smoke

After the environment is loaded, run a smoke against the current exporter path:

```bash
mkdir -p /tmp/agentic-langfuse-smoke

itmux codex-exec \
  --prompt "Reply exactly: LANGFUSE_SMOKE_OK" \
  --observability-file /tmp/agentic-langfuse-smoke/events.jsonl \
  --observability-langfuse \
  --result-file /tmp/agentic-langfuse-smoke/result.json
```

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

This path maps Claude `tool_use`/`tool_result` transcript items to normalized
tool spans and `result.modelUsage` entries to shared `token_usage` events with
`harness=claude`, `provider=anthropic`, model names, token counts, cached-token
counts, and cost data. Transcript-derived tool input values and result content
are redacted before export; tool input spans preserve only shape metadata such
as object key names. The result `session_log` records a summary, not the raw
transcript. This is the current reusable export path for Claude-shaped
telemetry.

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

Passing local criteria:

- the command exits successfully;
- `/tmp/agentic-langfuse-smoke/events.jsonl` contains normalized run events;
- `/tmp/agentic-langfuse-smoke/result.json` contains a `langfuse_otlp` exporter
  report with `status` set to `ok`;
- `events_exported` is greater than zero;
- when `LANGFUSE_PROJECT_ID` is set, the report includes a LangFuse trace link.
- `itmux langfuse-trace` can query the trace. For LangFuse v3 Docker Compose,
  use `--api legacy-trace`; Observations API v2 requires LangFuse v4 write mode.
- the emitted trace link resolves in the LangFuse UI.
- token usage appears as native LangFuse generation data when the harness
  provides model/usage metadata: model name, prompt/completion/total tokens,
  calculated cost, environment, and harness tags should be visible in the trace
  API and dashboard.
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

Passing backend criteria:

- LangFuse accepts the OTLP payload;
- the trace is visible and queryable in the LangFuse UI;
- `itmux langfuse-trace --output summary --run-id <run_id>` returns the
  learning-loop summary for the exported trace after the expected ingestion
  delay;
- the trace has at least three child observations;
- the trace has at least one `GENERATION` observation for usage-bearing model
  calls, with nonzero native token fields and calculated cost when the model is
  known to LangFuse;
- the reported trace link resolves when project id metadata is available.

`okrs-51p.9` remains open until both the local and backend criteria pass against
LangFuse Cloud or the planned self-hosted Mac Mini deployment.

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

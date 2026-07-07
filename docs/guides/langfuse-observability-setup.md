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
repository and does not commit secrets. After startup, open
`http://localhost:3000`, create a project and API keys, load those keys into the
environment or macOS Keychain, then run:

```bash
scripts/langfuse-local.sh smoke
```

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

Passing backend criteria:

- LangFuse accepts the OTLP payload;
- the trace is visible and queryable in the LangFuse UI;
- `itmux langfuse-trace --run-id <run_id> --from-start-time <start> --to-start-time <end>`
  returns observation rows for the exported trace after the expected ingestion
  delay;
- the trace has at least three child observations;
- the reported trace link resolves when project id metadata is available.

`okrs-51p.9` remains open until both the local and backend criteria pass against
LangFuse Cloud or the planned self-hosted Mac Mini deployment.

## Agent Trace Query

Use the same secret injection model as export:

```bash
itmux langfuse-trace \
  --run-id <itmux-run-id> \
  --from-start-time 2026-07-07T20:00:00Z \
  --to-start-time 2026-07-07T21:00:00Z
```

The command derives the deterministic LangFuse trace id from the run id and
queries `/api/public/v2/observations` with bounded `fromStartTime` and
`toStartTime`. You can also pass `--trace-id <32-hex-trace-id>` directly.
For self-hosted LangFuse deployments that do not expose the v2 observations
endpoint, pass `--api legacy-trace` to query `/api/public/traces/{traceId}`.

LangFuse documentation says newly ingested data is typically queryable after
about 15-30 seconds, so backend smoke runs should wait before checking
discoverability.

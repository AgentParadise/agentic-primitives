# Eval Pack

## Probe A: Baseline

Capture:

```bash
scripts/langfuse-observability-doctor.sh --json --no-tests
itmux langfuse-traces --output summary --harness codex \
  --environment local-macbook --limit 10
```

## Probe B: Hook-Trust Treatment

Load local LangFuse values from the ignored local stack `.env`, then run:

```bash
TRACE_TO_LANGFUSE=true \
LANGFUSE_CODEX_DEBUG=true \
LANGFUSE_CODEX_FAIL_ON_ERROR=true \
LANGFUSE_BASE_URL=http://localhost:3000 \
LANGFUSE_PUBLIC_KEY=<from ignored local env> \
LANGFUSE_SECRET_KEY=<from ignored local env> \
LANGFUSE_TRACING_ENVIRONMENT=local-macbook \
codex exec --json --sandbox read-only --dangerously-bypass-hook-trust \
  "Run a harmless shell command that prints <marker>, then reply exactly: <marker>"
```

Record stdout, stderr, exit status, marker, rollout path, and sidecar state.

## Probe C: Trace Query

Poll recent Codex traces and identify the fresh trace created after the
treatment start. Query:

```bash
itmux langfuse-trace --api legacy-trace --output summary --trace-id <trace-id>
```

Pass requires:

- automatic sidecar exists;
- summary `ok=true`;
- trace name `Codex Turn`;
- `observation_types` includes `GENERATION` and `TOOL`;
- `models` includes `gpt-5.5`;
- `usage.total_tokens > 0`;
- `cost.total_usd > 0`;
- `agent_tools.names` includes `exec_command`.

## Probe D: Hygiene

Run key scan, fallback-flag scan, and `git diff --check`.

## Verdict Rules

Use `go` if hook trust bypass produces an automatic rich official-plugin trace.

Use `no-go` if the run completes but no automatic trace/sidecar appears.

Use `inconclusive` if Codex rejects the trust-bypass command or the run cannot
complete for unrelated auth/rate/network reasons.

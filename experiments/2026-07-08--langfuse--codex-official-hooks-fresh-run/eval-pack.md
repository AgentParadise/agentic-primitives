# Eval Pack

## Probe A: Baseline

Capture:

```bash
scripts/langfuse-observability-doctor.sh --json --no-tests
scripts/langfuse-local.sh status
awk 'NR>=45 && NR<=56 {print NR ":" $0}' "$HOME/.codex/config.toml"
env-with-local-langfuse ./providers/workspaces/interactive-tmux/driver-rs/target/debug/itmux \
  langfuse-traces --output summary --harness codex --environment local-macbook --limit 10
```

Store outputs under `runs/baseline-*`.

## Probe B: Fresh Codex Run

Load local LangFuse values from the ignored local stack `.env`, export only the
runtime names needed by the official plugin, and run:

```bash
TRACE_TO_LANGFUSE=true \
LANGFUSE_BASE_URL=http://localhost:3000 \
LANGFUSE_PUBLIC_KEY=<from ignored local env> \
LANGFUSE_SECRET_KEY=<from ignored local env> \
LANGFUSE_TRACING_ENVIRONMENT=local-macbook \
codex exec --json --sandbox read-only --ask-for-approval never \
  "Reply exactly with the marker after issuing one harmless shell command that prints it."
```

Record stdout/stderr/exit status. Do not use `itmux --observability-langfuse`
or `--observability-langfuse-force`.

## Probe C: Trace Query

Poll recent Codex traces with:

```bash
itmux langfuse-traces --output summary --harness codex \
  --environment local-macbook --limit 10
```

Identify the fresh trace, then query:

```bash
itmux langfuse-trace --api legacy-trace --output summary --trace-id <trace-id>
itmux langfuse-trace --api legacy-trace --output full --trace-id <trace-id>
```

Pass requires:

- summary `ok=true`;
- trace name `Codex Turn`;
- `observation_types` includes `GENERATION` and `TOOL`;
- `models` includes `gpt-5.5`;
- `usage.total_tokens > 0`;
- `cost.total_usd > 0`;
- `agent_tools.names` includes `exec_command`.

## Probe D: Noise And Hygiene

Run:

```bash
rg -n -- '--observability-langfuse|--observability-langfuse-force' \
  experiments/2026-07-08--langfuse--codex-official-hooks-fresh-run/runs
rg -n 'pk-lf-[A-Za-z0-9_-]+|sk-lf-[A-Za-z0-9_-]+' \
  experiments/2026-07-08--langfuse--codex-official-hooks-fresh-run/runs
git diff --check
```

Pass requires no fallback export flags in run commands, no raw LangFuse key
matches, and no whitespace errors.

## Verdict Rules

Use `go` if a fresh post-remediation Codex run writes a new rich trace through
the official plugin and the hygiene probes pass.

Use `no-go` if Codex completes but no new official-plugin trace appears or the
trace lacks rich generation/tool/cost data.

Use `inconclusive` if local LangFuse, Codex auth, or plugin runtime availability
prevents the run from executing.

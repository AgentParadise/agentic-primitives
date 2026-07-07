# Experiment: LangFuse CLI Runtime Fail-Fast

## Question

When LangFuse is enabled through the actual `itmux codex-exec` CLI path but
required `LANGFUSE_*` env vars are absent, does the run stay usable while
reporting a clear failed LangFuse exporter?

## Hypothesis

1. A synthetic successful `codex exec --json` run exits successfully through
   `itmux codex-exec`.
2. With `--observability-langfuse` and no `LANGFUSE_*` env, the final
   `AgentRunResult.observability.exporters[]` contains one `langfuse_otlp`
   report with `status = failed`.
3. The failure names the missing required env var and does not include secret
   values.
4. Stdout remains valid `AgentRunEvent` JSONL; the exporter failure appears in
   the result payload, not as a stray stdout line.

## Setup

- Branch: `feat/observability-exporter-primitive`.
- Builds on `experiments/2026-07-07--langfuse--cli-setup-path`.
- Harness: `fixtures/fake-codex-success.sh`, a tiny executable that emits
  representative `codex exec --json` events.
- Real LangFuse credentials are intentionally absent.

## Expected Signals

- `itmux codex-exec --observability-langfuse` exits 0 with the fake harness.
- Result file reports run success and failed LangFuse observability status.
- Stdout lines all parse as `AgentRunEvent`.
- Full driver tests, fmt, and clippy pass.

## Out of Scope

- Real LangFuse ingestion or trace visibility.
- Validating the real Codex binary.
- Secret/keychain setup.

# Verdict

## no-go

The automatic Codex official-plugin path did not create a new LangFuse trace
for a fresh `codex exec --json --sandbox read-only` run, even though the doctor
reported static Codex config readiness.

This is not a LangFuse credential or plugin-export failure: direct invocation
of the official plugin bundle against the same fresh rollout uploaded rich trace
`b928a86e0c44784896a2224778c339c4` with `Codex Turn`, `GENERATION`, `TOOL`,
model `gpt-5.5`, non-zero usage/cost, and `exec_command`.

## Hypothesis scorecard

| Prediction | Observed | Score | Notes |
|---|---|---|---|
| A fresh valid `codex exec --json --sandbox read-only` run with `TRACE_TO_LANGFUSE=true` will create a new trace automatically. | The Codex run succeeded, but no new trace appeared and no `.langfuse` sidecar was created automatically. | wrong | Static doctor readiness is insufficient proof of automatic Stop-hook invocation. |
| The new trace will be discoverable through `itmux langfuse-traces`. | No automatic trace was present to discover. | wrong | Direct manual hook upload was discoverable later. |
| The trace summary will report rich official-plugin shape. | The manually invoked official plugin produced the expected rich shape. | partial | Plugin/export/query path works, but automatic hook path did not. |
| The run will not use Rust OTLP fallback exporter. | No fallback exporter flags appeared in run artifacts. | correct | The no-go is isolated to official Codex hook invocation, not fallback noise. |
| Artifacts will not contain raw LangFuse keys. | Secret scan found no raw key matches. | correct | Credentials were loaded only from ignored local env. |

## Follow-up

The next remediation probe should test whether non-interactive `codex exec`
requires hook trust bypass or explicit hook trust setup, for example by running
the same fresh trace probe with Codex's `--dangerously-bypass-hook-trust` option
and debug/fail-on-error environment enabled.

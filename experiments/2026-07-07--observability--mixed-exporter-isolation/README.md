# Experiment: Mixed Exporter Isolation

## Question

When one observability exporter is misconfigured, do other exporters still
receive and report the normalized event stream?

## Hypothesis

1. `itmux codex-exec` can run with both `--observability-file` and
   `--observability-langfuse`.
2. With no `LANGFUSE_*` env, the LangFuse exporter reports `status = failed`.
3. The file exporter still writes every normalized event and reports
   `status = ok`.
4. Stdout remains valid `AgentRunEvent` JSONL and matches the file exporter.

## Setup

- Branch: `feat/observability-exporter-primitive`.
- Builds on `experiments/2026-07-07--langfuse--cli-runtime-failfast`.
- Harness: reuse
  `experiments/2026-07-07--langfuse--cli-runtime-failfast/fixtures/fake-codex-success.sh`.
- Real LangFuse credentials are intentionally absent.

## Expected Signals

- Runtime command exits 0.
- Result has two exporter reports:
  - file: `status = ok`, `events_exported = 6`
  - LangFuse: `status = failed`, missing `LANGFUSE_BASE_URL`
- `runs/events.jsonl` and `runs/stdout.jsonl` contain the same six event types
  and sequence numbers.
- Full driver tests, fmt, and clippy pass.

## Out of Scope

- Real LangFuse ingestion.
- Real Codex binary behavior.
- File exporter failure modes.

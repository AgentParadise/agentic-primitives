# Observability Primitive Implementation Plan

Status: proposed
Date: 2026-07-07
OKRs: `okrs-51p.6` blocks `okrs-51p.9`
ADR: `docs/adrs/038-modular-agent-observability.md`

## Empirical Inputs

- `experiments/2026-07-07--observability--claude-hook-file-fanout`
- `experiments/2026-07-07--observability--codex-token-cost-surface`
- `experiments/2026-07-07--langfuse--otel-ingestion-smoke`
- `experiments/2026-07-07--observability--langfuse-otel-export`

## Current Facts

- File fanout works for normalized driver events: stdout and exported JSONL
  counts matched in Claude and Codex probes.
- Claude plugin launch can be requested through recipe `skills`, producing
  `claude --plugin-dir /workspace/plugins/observability`.
- Claude hook observability is not validated yet because the workspace run hits
  Anthropic `API Error: 401`.
- Codex TUI does not expose token/cost in the current `itmux run` stream.
- `codex exec --json` exposes structured lifecycle events and
  `turn.completed.usage`.
- First implementation slice landed a `harness_observer` module with
  `CodexExecJsonObserver`; it parses `codex exec --json` lifecycle/failure
  events and maps `turn.completed.usage` to `token_usage`.
- LangFuse OTLP export is not validated because no LangFuse env/credentials are
  present, and the current Rust exporter enum supports only `file`.

## `.6` Implementation Sequence

1. Keep the existing `file` exporter and `ObservabilityBundle` reports as the
   first backend-independent primitive.
2. Add a harness observer boundary: **done for first parser slice**.
   - `HarnessObserver` trait or equivalent module boundary.
   - observer output is normalized `AgentRunEvent`.
   - observer diagnostics go to stderr or exporter reports, never stdout.
3. Implement `codex_exec_json` observer: **parser done, runtime wiring next**.
   - parse `thread.started`, `turn.started`, `item.completed`,
     `turn.completed`, and `turn.failed`.
   - map `turn.completed.usage` to `AgentRunEventPayload::TokenUsage`.
   - preserve failure lifecycle for rejected model/account configurations.
4. Wire `codex_exec_json` into a runnable execution path:
   - add a non-interactive Codex execution mode or adapter entry point.
   - attach run id, sequence, and timestamps to observed payloads.
   - feed resulting `AgentRunEvent`s through the existing exporter fanout.
   - add an acceptance test using captured `codex exec --json` fixtures.
5. Revalidate Claude interactive credentials:
   - reproduce the 401 failure with a targeted credential-transfer probe.
   - fix credential staging or image behavior if the failure reproduces.
   - rerun the Claude hook fanout experiment after the fix.
6. Implement `claude_hooks` observer only after credential health is proven:
   - load `plugins/observability` through recipe/plugin-dir path.
   - parse hook JSONL/stderr output into normalized lifecycle/tool events.
   - resolve the plugin README stdout/stderr mismatch while preserving
     `itmux run` stdout purity.
7. Add acceptance coverage:
   - file exporter success count and report status.
   - file exporter failure report.
   - relative path vs absolute path link behavior.
   - `codex_exec_json` token usage mapping.
   - Claude hook event mapping once credentials are healthy.

## `.6` Exit Criteria

- At least one harness observer produces normalized events end to end.
- At least one backend-independent exporter succeeds and reports failures
  cleanly.
- Codex token usage parity is scoped to `codex_exec_json`; TUI parity is not
  claimed.
- Claude hook support has an empirical pass, or the OKR explicitly scopes it as
  a follow-up blocker with evidence.

## `.9` Implementation Sequence

1. Provide LangFuse env through secure setup:
   - `LANGFUSE_BASE_URL`
   - `LANGFUSE_PUBLIC_KEY`
   - `LANGFUSE_SECRET_KEY`
   - `LANGFUSE_TRACING_ENVIRONMENT`
2. Rerun `experiments/2026-07-07--langfuse--otel-ingestion-smoke`.
3. Add typed exporter config after the smoke passes:
   - `ObservabilityExporter::Otlp` or `ObservabilityExporter::LangFuse`.
   - explicit config validation and redacted error reporting.
   - OTLP HTTP/protobuf, not gRPC, for first LangFuse path.
4. Map normalized run events to spans:
   - one root trace per run.
   - child observations for provision, launch, submit, await, capture.
   - resource/span attributes for `session.id`, `service.name`,
     `langfuse.environment`, `langfuse.session.id`, `langfuse.trace.name`.
5. Emit a trace link in `ObservabilityBundle`.
6. Rerun `experiments/2026-07-07--observability--langfuse-otel-export` and
   score the verdict before closing `.9`.

## `.9` Exit Criteria

- OTLP smoke passes against a reachable LangFuse deployment.
- Run-event mapping creates a discoverable trace with at least three child
  observations.
- Final result includes a human-usable trace link.
- Missing or invalid credentials produce a failed exporter report, not silent
  success and not stdout corruption.

# Observability Primitive Implementation Plan

Status: proposed
Date: 2026-07-07
OKRs: `okrs-51p.6` blocks `okrs-51p.9`
ADR: `docs/adrs/038-modular-agent-observability.md`

## Empirical Inputs

- `experiments/2026-07-07--observability--claude-hook-file-fanout`
- `experiments/2026-07-07--observability--codex-token-cost-surface`
- `experiments/2026-07-07--langfuse--otel-ingestion-smoke`
- `experiments/2026-07-07--langfuse--otel-preflight-mock`
- `experiments/2026-07-07--langfuse--exporter-config-failfast`
- `experiments/2026-07-07--langfuse--otlp-transport-mock`
- `experiments/2026-07-07--observability--langfuse-otel-export`
- `experiments/2026-07-07--observability--codex-exec-observer-wiring`
- `experiments/2026-07-07--observability--claude-credential-health`
- `experiments/2026-07-07--observability--claude-env-token-passthrough`
- `experiments/2026-07-07--observability--claude-hook-fanout-after-auth`
- `experiments/2026-07-07--observability--baked-claude-hook-runtime`
- `experiments/2026-07-07--observability--claude-hook-sink-capture`
- `experiments/2026-07-07--observability--stock-itmux-hook-sink`

## Current Facts

- File fanout works for normalized driver events: stdout and exported JSONL
  counts matched in Claude and Codex probes.
- Claude plugin launch can be requested through recipe `skills`, producing
  `claude --plugin-dir /workspace/plugins/observability`.
- Claude hook observability is validated through explicit sink capture and stock
  provider packaging.
- Codex TUI does not expose token/cost in the current `itmux run` stream.
- `codex exec --json` exposes structured lifecycle events and
  `turn.completed.usage`.
- First implementation slice landed a `harness_observer` module with
  `CodexExecJsonObserver`; it parses `codex exec --json` lifecycle/failure
  events and maps `turn.completed.usage` to `token_usage`.
- Second implementation slice added the `itmux codex-exec` command, which runs
  `codex exec --json`, envelopes observed payloads with run id/sequence/time,
  and sends them through the same file fanout/report path.
- `experiments/2026-07-07--observability--codex-exec-observer-wiring` passed:
  six normalized stdout events, six exported events, one `token_usage` event,
  result success true, exporter status `ok`.
- `experiments/2026-07-07--observability--claude-credential-health` classified
  the Claude 401: host Claude succeeds via `CLAUDE_CODE_OAUTH_TOKEN`, but the
  Docker workspace does not receive that env token and its staged disk
  credentials cannot refresh.
- `experiments/2026-07-07--observability--claude-env-token-passthrough` passed:
  recipe-driven Claude in Docker exited 0, returned `CLAUDE_ENV_TOKEN_OK`, and
  preserved 11 stdout events / 11 exported events with exporter status `ok`.
- `experiments/2026-07-07--observability--claude-hook-fanout-after-auth`
  passed for auth and plugin launch, but no hook `event_type` JSONL appeared in
  stdout, exporter, stderr, or session log. Current fanout is still driver
  events only.
- `experiments/2026-07-07--observability--baked-claude-hook-runtime` proved the
  plugin runtime can emit hook JSONL when run directly, but Claude TUI does not
  surface that output to the current `itmux run` capture path.
- `experiments/2026-07-07--observability--claude-hook-sink-capture` passed:
  explicit `AGENTIC_EVENTS_JSONL` sink capture produced 3 normalized
  `hook_event` records in stdout and exporter output, with `session_end` still
  last.
- `experiments/2026-07-07--observability--stock-itmux-hook-sink` passed:
  the stock interactive-tmux provider image now contains the observability
  plugin/runtime and emits the same normalized hook events.
- LangFuse OTLP export is not validated because no LangFuse env/credentials are
  present, and the current `.9` implementation still needs a LangFuse/OTLP
  exporter variant.
- `experiments/2026-07-07--langfuse--otel-preflight-mock` passed locally:
  endpoint/auth/header/attribute construction is proven against a mock receiver,
  but real LangFuse ingestion remains unproven.
- `experiments/2026-07-07--langfuse--exporter-config-failfast` passed:
  `ObservabilityExporter::LangFuseOtlp` config round-trips, the schema includes
  `langfuse_otlp`, and missing env produces a failed exporter report.
- `experiments/2026-07-07--langfuse--otlp-transport-mock` passed:
  the actual Rust exporter sends OTLP HTTP/protobuf to a mock receiver and
  reports `ok` on a 2xx response.

## `.6` Implementation Sequence

1. Keep the existing `file` exporter and `ObservabilityBundle` reports as the
   first backend-independent primitive.
2. Add a harness observer boundary: **done for first parser slice**.
   - `HarnessObserver` trait or equivalent module boundary.
   - observer output is normalized `AgentRunEvent`.
   - observer diagnostics go to stderr or exporter reports, never stdout.
3. Implement `codex_exec_json` observer: **done**.
   - parse `thread.started`, `turn.started`, `item.completed`,
     `turn.completed`, and `turn.failed`.
   - map `turn.completed.usage` to `AgentRunEventPayload::TokenUsage`.
   - preserve failure lifecycle for rejected model/account configurations.
4. Wire `codex_exec_json` into a runnable execution path: **done and
   experiment-passed**.
   - add a non-interactive Codex execution mode or adapter entry point.
   - attach run id, sequence, and timestamps to observed payloads.
   - feed resulting `AgentRunEvent`s through the existing exporter fanout.
   - add an acceptance test using captured `codex exec --json` fixtures.
5. Revalidate Claude hook fanout with credential health fixed:
   - **done for auth/plugin launch; no-go for hook visibility**.
   - **done for baked runtime; direct handler emits, TUI capture still no-go**.
   - **done for explicit hook sink; live run emitted normalized hook events**.
   - **done for stock provider packaging; live run emitted normalized hook
     events without a temporary image**.
   - preserve the narrow `CLAUDE_CODE_OAUTH_TOKEN` Docker env passthrough and
     do not put token values in argv/stdout.
6. Implement `claude_hooks` observer after hook output shape is proven:
   **done through explicit sink/drain normalization**.
   - load `plugins/observability` through recipe/plugin-dir path.
   - parse hook JSONL/stderr output into normalized lifecycle/tool events.
   - document stderr plus `AGENTIC_EVENTS_JSONL` sink behavior while preserving
     `itmux run` stdout purity.
7. Add acceptance coverage:
   - file exporter success count and report status.
   - file exporter failure report.
   - relative path vs absolute path link behavior.
   - `codex_exec_json` token usage mapping.
   - Claude hook event mapping once credentials are healthy.

## `.6` Exit Criteria

- At least one harness observer produces normalized events end to end:
  **satisfied by `itmux codex-exec`**.
- At least one backend-independent exporter succeeds and reports status cleanly:
  **satisfied by file fanout in `itmux codex-exec`**.
- Codex token usage parity is scoped to `codex_exec_json`; TUI parity is not
  claimed.
- Claude hook support has an empirical pass:
  **satisfied by hook-sink-capture and stock-itmux-hook-sink**.

## `.9` Implementation Sequence

1. Provide LangFuse env through secure setup:
   - `LANGFUSE_BASE_URL`
   - `LANGFUSE_PUBLIC_KEY`
   - `LANGFUSE_SECRET_KEY`
   - `LANGFUSE_TRACING_ENVIRONMENT`
2. Use `experiments/2026-07-07--langfuse--otel-preflight-mock` as local
   regression coverage for endpoint/auth/header/attribute construction.
3. Add typed exporter config: **done for config/fail-fast slice**.
   - `ObservabilityExporter::Otlp` or `ObservabilityExporter::LangFuse`.
   - explicit config validation and redacted error reporting.
   - OTLP HTTP/protobuf, not gRPC, for first LangFuse path.
4. Implement real OTLP transport and semantic span encoding:
   **mock-proven for transport/root span/event spans**.
5. Rerun `experiments/2026-07-07--langfuse--otel-ingestion-smoke` against a
   reachable LangFuse deployment.
6. Map normalized run events to spans:
   - one root trace per run.
   - child observations for provision, launch, submit, await, capture.
   - resource/span attributes for `session.id`, `service.name`,
     `langfuse.environment`, `langfuse.session.id`, `langfuse.trace.name`.
7. Emit a trace link in `ObservabilityBundle`.
8. Rerun `experiments/2026-07-07--observability--langfuse-otel-export` and
   score the verdict before closing `.9`.

## `.9` Exit Criteria

- OTLP smoke passes against a reachable LangFuse deployment.
- Run-event mapping creates a discoverable trace with at least three child
  observations.
- Final result includes a human-usable trace link.
- Missing or invalid credentials produce a failed exporter report, not silent
  success and not stdout corruption.

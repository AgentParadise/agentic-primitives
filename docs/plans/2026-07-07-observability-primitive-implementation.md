# Observability Primitive Implementation Plan

Status: proposed
Date: 2026-07-07
OKRs: `okrs-51p.6` blocks `okrs-51p.9`
ADR: `docs/adrs/038-modular-agent-observability.md`
Completion audit:
`docs/plans/2026-07-07-observability-primitive-completion-audit.md`

## Empirical Inputs

- `experiments/2026-07-07--observability--claude-hook-file-fanout`
- `experiments/2026-07-07--observability--codex-token-cost-surface`
- `experiments/2026-07-07--langfuse--otel-ingestion-smoke`
- `experiments/2026-07-07--langfuse--otel-preflight-local-receiver`
- `experiments/2026-07-07--langfuse--exporter-config-failfast`
- `experiments/2026-07-07--langfuse--otlp-transport-local-receiver`
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
- Real LangFuse backend export is now validated against the local Docker
  Compose stack on this MacBook. The `.9` implementation has the typed
  `langfuse_otlp` exporter, fail-fast config validation, local-receiver-proven
  HTTP/protobuf transport, real-backend trace-query evidence, trace-link
  reporting, and CLI setup flags.
- The refreshed
  `experiments/2026-07-07--langfuse--otel-ingestion-smoke` protocol now tests
  both minimal OTLP ingestion and the current
  `itmux codex-exec --observability-langfuse` exporter path. Current evidence
  shows `scripts/langfuse-local.sh smoke` exporting to local LangFuse v3,
  querying it back via `itmux langfuse-trace --api legacy-trace`, and resolving
  the emitted trace URL.
- `docs/guides/langfuse-observability-setup.md` documents the secret-safe setup
  path for MacBooks, Mac Minis, VPS hosts, and Docker workspaces, plus the real
  backend smoke criteria for `.9`.
- `experiments/2026-07-07--langfuse--otel-preflight-local-receiver` passed locally:
  endpoint/auth/header/attribute construction is proven against a local receiver,
  and the later real-backend smoke validated LangFuse ingestion.
- `experiments/2026-07-07--langfuse--exporter-config-failfast` passed:
  `ObservabilityExporter::LangFuseOtlp` config round-trips, the schema includes
  `langfuse_otlp`, and missing env produces a failed exporter report.
- `experiments/2026-07-07--langfuse--otlp-transport-local-receiver` passed:
  the actual Rust exporter sends OTLP HTTP/protobuf to a local receiver and
  reports `ok` on a 2xx response.
- `experiments/2026-07-07--langfuse--trace-link-reporting` passed:
  the LangFuse exporter accepts optional project id metadata and reports a
  human-facing `/project/<project_id>/traces/<32_hex_trace_id>` link after a
  successful local receiver export.
- `experiments/2026-07-07--langfuse--cli-setup-path` passed:
  `itmux run` and `itmux codex-exec` both expose `--observability-langfuse`
  plus base-url, project-id, and label flags, and the shared CLI builder maps
  them to the typed LangFuse exporter with env-only secret references.
- `experiments/2026-07-07--langfuse--cli-runtime-failfast` passed:
  with real LangFuse env absent, `itmux codex-exec --observability-langfuse`
  still completed a synthetic successful run, kept stdout as valid
  `AgentRunEvent` JSONL, and reported `langfuse_otlp` as a failed exporter in
  the final result with a clear missing `LANGFUSE_BASE_URL` error.
- `experiments/2026-07-07--observability--mixed-exporter-isolation` passed:
  with both file and LangFuse exporters enabled and real LangFuse env absent,
  `itmux codex-exec` reported the file exporter as `ok` with all 6 events while
  reporting LangFuse as `failed`, and stdout/file event types plus seq values
  matched exactly.
- `experiments/2026-07-07--observability--langfuse-otel-export` was rerun
  against the current CLI/exporter path: the old "no exporter exists" result is
  superseded. The final real-backend smoke now proves LangFuse exporter `ok`,
  trace discoverability, and trace-link resolution against local Docker Compose.

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
- Exporter failures are isolated:
  **satisfied by mixed file+LangFuse fanout where file stayed `ok` while
  LangFuse failed on missing env**.
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
   - optional `LANGFUSE_PROJECT_ID` for trace links
   - setup/smoke protocol:
     `docs/guides/langfuse-observability-setup.md`
2. Use `experiments/2026-07-07--langfuse--otel-preflight-local-receiver` as local
   regression coverage for endpoint/auth/header/attribute construction.
3. Add typed exporter config: **done for config/fail-fast slice**.
   - `ObservabilityExporter::LangFuseOtlp`.
   - explicit config validation and redacted error reporting.
   - OTLP HTTP/protobuf, not gRPC, for first LangFuse path.
4. Implement OTLP HTTP/protobuf transport and semantic span encoding:
   **local-receiver-proven and real-backend-proven against local Docker Compose**.
5. Rerun `experiments/2026-07-07--langfuse--otel-ingestion-smoke` against a
   reachable LangFuse deployment: **done against local Docker Compose**.
6. Map normalized run events to spans:
   - one root trace per run.
   - child observations for provision, launch, submit, await, capture.
   - resource/span attributes for `session.id`, `service.name`,
     `langfuse.environment`, `langfuse.session.id`, `langfuse.trace.name`.
7. Emit a trace link in `ObservabilityBundle`:
   **proven with optional `LANGFUSE_PROJECT_ID`; URL returned HTTP 200 against
   local Docker Compose**.
8. Expose setup through CLI flags:
   **done for `itmux run --observability-langfuse` and
   `itmux codex-exec --observability-langfuse`**.
9. Validate CLI runtime fail-fast for missing LangFuse setup:
   **done for `itmux codex-exec --observability-langfuse` with absent env**.
10. Validate mixed exporter isolation:
   **done for file exporter ok plus LangFuse failed in one `itmux codex-exec`
   run**.
11. Rerun `experiments/2026-07-07--observability--langfuse-otel-export`:
   **done against current CLI/exporter path; real backend proof captured in the
   LangFuse ingestion smoke**.

## `.9` Exit Criteria

- OTLP smoke passes against a reachable LangFuse deployment.
- Run-event mapping creates a discoverable trace with at least three child
  observations.
- Final result includes a human-usable trace link.
- Missing or invalid credentials produce a failed exporter report, not silent
  success and not stdout corruption.
- Mixed file+LangFuse export preserves local JSONL observability when LangFuse
  is absent or misconfigured.

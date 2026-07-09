# Observability Primitive Implementation Plan

Status: proposed
Date: 2026-07-07
OKRs: `okrs-51p.6` blocks `okrs-51p.9`
ADR: `docs/adrs/038-modular-agent-observability.md`
Completion audit:
`docs/plans/2026-07-07-observability-primitive-completion-audit.md`

Historical note (2026-07-08): ADR-039 supersedes this plan's direct
Rust OTLP-to-LangFuse implementation path. The current implementation removes
that public writer path and packages official Claude/Codex LangFuse plugins as
the rich-trace producers, with JSONL/Syntropic fanout retained locally.

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
- `experiments/2026-07-08--langfuse--official-plugin-trace-shape`
- `experiments/2026-07-08--langfuse--official-plugin-e2e-local`

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
- Third implementation slice added `itmux run --codex-mode exec`, which lets
  Codex recipes use the same structured `codex exec --json` observer and
  file/LangFuse fanout from the standard recipe-driven run surface.
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
- Real LangFuse backend access is now validated against the local Docker
  Compose stack on this MacBook. The historical `.9` Rust OTLP implementation
  had typed exporter config, fail-fast validation, local-receiver-proven
  HTTP/protobuf transport, real-backend trace-query evidence, trace-link
  reporting, and CLI setup flags; ADR-039 superseded that public writer path in
  favor of official Claude/Codex plugins for rich traces.
- Agent-facing trace query is now available through both CLI and MCP. The
  `observability` plugin's `agentic-langfuse` MCP server delegates to the
  proven `itmux langfuse-*` commands and has local-backend proof for compact
  trace summaries.
- The 2026-07-08 official-plugin trace-shape experiment changed the LangFuse
  product boundary. Official LangFuse Claude/Codex marketplace plugins are the
  canonical rich trace integrations for those harnesses. JSONL fanout remains
  the durable local/source-of-truth path. The direct Rust OTLP writer is
  historical evidence only and has been removed from the active public run
  contract because its trace shape was noisy in LangFuse: generic event spans,
  missing root input/output, unpaired tool start/end spans, and token usage as
  a generic event rather than a generation observation.
- The official-plugin E2E local experiment passed against the local LangFuse
  stack. The official Claude hook exported root input/output, two generation
  observations, and `Tool: Read`. The official Codex hook exported a
  `Codex Turn` agent observation, two generation observations with usage, an
  `exec_command` tool observation, total cost, and sidecar dedup state. No Rust
  OTLP writer path ran during the experiment.
- The official-plugin real-session experiment passed against the local
  LangFuse stack with marketplace-installed plugins. Claude trace
  `0e553fc833c71639acd03be9807eb616` and Codex trace
  `b3d2561d7c0557c12fd427c02a16e2f3` were created by real harness sessions,
  had root input/output, generation observations, tool observations, usage/cost,
  and `local-macbook` environment, without the Rust OTLP writer. Caveat:
  Claude install-time `--config` reported values unset, so that run used the
  official hook's env fallback.
- The single-rich-exporter guard experiment is superseded by a cleaner public
  surface: the direct Rust LangFuse writer flags and schema variant have been
  removed, so official-plugin traces are not duplicated by `itmux`.
- The Syntropic137 JSONL compatibility experiment proved current
  `AgentRunEvent` file JSONL is not directly consumed by Syntropic137's
  HookWatcher. `syntropic_jsonl` now provides a separate projection exporter
  and `--observability-syntropic-file` CLI flag that emits top-level
  `event_type`/`session_id`/`timestamp` records for Syntropic137 session/tool
  ingestion while preserving the canonical `file` exporter. Current
  Syntropic137 HookWatcher still skips `token_usage`; token/cost remains on its
  transcript/OTLP lane until that map is extended.
- The refreshed historical
  `experiments/2026-07-07--langfuse--otel-ingestion-smoke` protocol tested both
  minimal OTLP ingestion and the old direct writer path. Current evidence uses
  `scripts/langfuse-local.sh smoke` as a setup/readiness doctor and validates
  rich LangFuse behavior through official Claude/Codex plugin traces plus
  `itmux langfuse-*` query tools.
- `docs/guides/langfuse-observability-setup.md` documents the secret-safe setup
  path for MacBooks, Mac Minis, VPS hosts, and Docker workspaces, plus the real
  backend smoke criteria for `.9`.
- `experiments/2026-07-07--langfuse--otel-preflight-local-receiver` passed locally:
  endpoint/auth/header/attribute construction is proven against a local receiver,
  and the later real-backend smoke validated LangFuse ingestion.
- `experiments/2026-07-07--langfuse--exporter-config-failfast` passed for the
  historical direct writer path. That result remains design evidence, but the
  `ObservabilityExporter::LangFuseOtlp` variant and public schema entry are no
  longer active.
- `experiments/2026-07-07--langfuse--otlp-transport-local-receiver` passed:
  the actual Rust exporter sends OTLP HTTP/protobuf to a local receiver and
  reports `ok` on a 2xx response.
- `experiments/2026-07-07--langfuse--trace-link-reporting` passed:
  the LangFuse exporter accepts optional project id metadata and reports a
  human-facing `/project/<project_id>/traces/<32_hex_trace_id>` link after a
  successful local receiver export.
- `experiments/2026-07-07--langfuse--cli-setup-path` and
  `experiments/2026-07-07--langfuse--cli-runtime-failfast` passed for the
  historical direct writer path. Their acceptance criteria are superseded by
  ADR-039 and replaced by official-plugin setup, readiness doctor checks,
  local JSONL/Syntropic fanout, and `itmux langfuse-*` query tools.
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
  claimed. Recipe-driven Codex parity is available through
  `itmux run --codex-mode exec`.
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
2. Treat official LangFuse marketplace plugins as canonical for rich
   Claude/Codex traces:
   - Claude: `langfuse/Claude-Observability-Plugin`
   - Codex: `langfuse/codex-observability-plugin`
   - agentic-primitives owns setup, configuration, local/VPS/Docker docs,
     smoke tests, and learning-loop query tools around those plugins.
3. Use `experiments/2026-07-07--langfuse--otel-preflight-local-receiver` as local
   regression coverage for endpoint/auth/header/attribute construction.
4. Historical typed Rust OTLP exporter config: **superseded by ADR-039**.
   - This was useful evidence for endpoint/auth/fail-fast behavior.
   - The public `LangFuseOtlp` variant and direct writer flags are no longer
     active in the run contract.
5. Do not keep Rust OTLP in the public Claude/Codex rich-trace path:
   **current implementation removes it**. Official plugins own LangFuse rich
   traces; JSONL/Syntropic fanout remains local and backend-independent.
6. Keep Syntropic137 support on a separate local projection path:
   **done for `syntropic_jsonl` and `--observability-syntropic-file`**.
   This avoids using noisy LangFuse fallback traces as the Syntropic137
   integration point and avoids changing the canonical `AgentRunEvent` file.
7. Preserve historical OTLP experiments as rationale only:
   `experiments/2026-07-07--langfuse--otel-ingestion-smoke`,
   `experiments/2026-07-07--langfuse--trace-link-reporting`, and related
   direct-writer experiments are not current acceptance gates.
8. Validate the current setup path instead:
   **done locally** through official Claude/Codex plugin traces, the setup
   doctor, local JSONL/Syntropic fanout, and `itmux langfuse-*` query tools.
9. Expose setup through docs/scripts, not direct writer flags:
   **done** in `docs/guides/langfuse-observability-setup.md`,
   `docs/runbooks/langfuse-observability.md`, `scripts/langfuse-local.sh`, and
   `scripts/langfuse-observability-doctor.sh`.
10. Validate file/Syntropic exporter isolation:
   **done** for backend-independent local evidence paths.
11. Expose MCP trace tools for agent learning loops:
   **done through `plugins/observability/mcp/langfuse_server.py`; local
   LangFuse proof captured in `runs/langfuse-mcp-trace-query`**.
12. Run the official-plugin E2E experiment:
   **done through direct official hook invocation and through real marketplace
   installed Claude/Codex sessions against local LangFuse**. Follow-up is
   durability and agent-query polish, not proof of trace shape:
   - resolve/re-test the Claude stored-config caveat;
   - make setup repeatable across MacBook, VPS, and Docker workspace paths;
   - keep the removed direct Rust writer out of the public Claude/Codex rich
     trace path.

## `.9` Exit Criteria

- Official Claude and Codex LangFuse plugins create discoverable rich traces
  against a reachable LangFuse deployment:
  **satisfied for local direct-hook fixture validation and real local
  marketplace-installed sessions**.
- Rich traces include root input/output, generation observations,
  tool observations, usage/cost, real timings, environment, and session
  grouping:
  **satisfied for local real-session validation; direct Claude fixture has zero
  usage/cost because it carries no nonzero usage fields**.
- LangFuse dashboard links are available through the official plugin traces and
  agent query/discovery tooling.
- Missing or invalid credentials are caught by setup/readiness checks and final
  trace smoke, without printing secret values.
- Local JSONL/Syntropic fanout remains usable independently of LangFuse setup.
- Agents can pull compact trace summaries through both CLI and MCP, using the
  same LangFuse query implementation.
- Rust OTLP fallback does not create duplicate/noisy LangFuse traces for
  Claude/Codex official-plugin runs:
  **satisfied by removing the direct writer from the public run path**.
- Syntropic137 can consume local session/tool observability without enabling
  fallback LangFuse OTLP:
  **satisfied for `syntropic_jsonl` exporter shape by
  `experiments/2026-07-08--syntropic137--jsonl-fanout-compat`**.

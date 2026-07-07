---
title: "ADR-038: Modular Agent Observability"
status: proposed
created: 2026-07-07
updated: 2026-07-07
author: Neural
tags: [architecture, observability, workspaces, langfuse, otel, plugins]
---

# ADR-038: Modular Agent Observability

## Status

**Proposed**

- Created: 2026-07-07
- Updated: 2026-07-07
- Author(s): Neural
- Related: ADR-022, ADR-027, ADR-033, ADR-035, ADR-037
- OKRs: `okrs-51p.6` blocks `okrs-51p.9`

## Context

The workspace standard needs observability that works in all execution places:
developer Macs, a Mac Mini, VPS hosts, and isolated Docker workspaces. The first
Rust `itmux run` contract gives us a normalized run event stream and a final
`AgentRunResult`, but observability cannot be only an `itmux` stdout detail.
It needs to be a reusable agentic primitive that other workspace providers and
future harnesses can use.

The source data is not uniform across harnesses:

- Claude Code has plugin hooks and can be launched with `--plugin-dir`, so
  lifecycle/tool events can come from a Claude plugin.
- `interactive-tmux` already supports Claude plugin directories through
  `ITMUX_CLAUDE_PLUGIN_DIRS` and recipe `claude_plugin_dirs`.
- Claude token/cost data is not fully captured by hook events alone; transcript
  or native stream/OTEL data must be considered separately.
- Codex currently has no equivalent `--plugin-dir` path in the interactive
  tmux adapter, so Codex observability likely needs a watcher or adapter-owned
  log/transcript parser.
- Codex non-interactive execution has a stronger structured surface through
  `codex exec --json`, including usage on `turn.completed`; this should be a
  separate `codex_exec` observer from the `codex_tui` observer.
- Future harnesses will have their own hook, log, transcript, or native OTEL
  surfaces.

The destination side is also intentionally plural:

- Local JSONL artifacts are useful for debugging, tests, and offline replay.
- LangFuse is the primary observability backend for the learning loop, expected
  to be self-hosted on the Mac Mini eventually.
- Syntropic137 and other consumers may need their own collector or event store.
- OpenTelemetry gives a vendor-neutral path to backends that accept OTLP.

The key design pressure is keeping these two axes independent. Harness-specific
collection should not know about every backend. Backend exporters should not know
how each harness emits or stores its raw events.

## Decision

We will split agent observability into three layers:

1. **Harness observers** collect raw lifecycle/tool/transcript/token signals for
   one harness and normalize them into shared agent event types.
2. **The normalized event stream** is the workspace-owned contract. For `itmux
   run`, this starts with `AgentRunEvent` JSONL plus final
   `AgentRunResult.observability` exporter reports.
3. **Exporter fanout** sends normalized events to one or more destinations:
   file JSONL, LangFuse/OTEL, Syntropic137 collector, or future webhooks.

The architecture is:

```text
Claude hooks / transcript watcher ┐
Codex log or transcript watcher   ├─> normalized agent events ─> fanout exporters
Future harness observer           ┘                         ├─ file JSONL
                                                            ├─ LangFuse / OTEL
                                                            └─ syn137 collector
```

The `itmux` Rust driver owns the first reusable fanout primitive:

- `ObservabilityExporter` is a typed configuration enum.
- `ObservabilityFanout` receives the same normalized events that stdout sees.
- `ObservabilityBundle` reports exporter status, event counts, targets, and
  links for UI/navigation.
- The first exporter is `file`, which appends event JSONL to a configured path
  that can live on a Mac, VPS, or Docker-mounted filesystem.

LangFuse support will be added as a backend exporter after the fanout primitive
is stable. For Rust and cross-language compatibility, the preferred first
LangFuse path is OTLP/OpenTelemetry to LangFuse's OTEL endpoint rather than a
direct dependency on a Python or JS SDK. Direct SDK exporters can still be
implemented where the runtime makes that cheaper.

LangFuse's native OTEL integration accepts OTLP over HTTP/protobuf at
`/api/public/otel`; gRPC should not be assumed for the first implementation.
OTLP authentication uses Basic auth derived from
`LANGFUSE_PUBLIC_KEY:LANGFUSE_SECRET_KEY`. Useful resource and span attributes
to preserve for filtering and trace reconstruction include `session.id`,
`langfuse.session.id`, `langfuse.trace.name`, `langfuse.trace.metadata.*`,
`service.name`, `deployment.environment.name`, and `langfuse.environment`.

Harness observers should be named by their actual collection surface, not only
by vendor. The initial observer set is:

- `claude_hooks`: reads events emitted by the Claude observability plugin.
- `claude_stream_json`: normalizes Claude headless stream JSON where available.
- `codex_exec_json`: normalizes `codex exec --json` events, including usage.
- `codex_tui`: watches runtime outputs available inside the workspace container
  or host tmux adapter; parity is experimental until proven.

Secrets must not be embedded in specs, examples, CLI args, or committed files.
LangFuse credentials should come from environment injection, keychain-backed
env setup on Macs, or an external redacted config path:

- `LANGFUSE_BASE_URL`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

## Alternatives Considered

### Alternative 1: One LangFuse Plugin Per Harness

**Description**: Build a Claude LangFuse plugin, a Codex LangFuse plugin, and
future harness-specific LangFuse plugins.

**Pros**:

- Straightforward for Claude where plugin hooks already exist.
- Closely matches some existing LangFuse community patterns.
- Fast path for a single harness proof of concept.

**Cons**:

- Couples harness collection directly to one backend.
- Duplicates mapping logic across harnesses.
- Does not help local JSONL, Syntropic137 collector, or other backends.
- Codex currently lacks the same plugin loading model, so the pattern does not
  generalize cleanly.

**Reason for rejection**: LangFuse is the primary backend, but the primitive must
support multiple collectors and execution places.

### Alternative 2: Only Use OpenTelemetry Everywhere

**Description**: Require every harness observer to emit OTEL spans directly and
send them to LangFuse or another OTEL backend.

**Pros**:

- Vendor-neutral backend protocol.
- LangFuse accepts OTLP.
- Existing observability tools understand traces/spans.

**Cons**:

- Forces every harness adapter to understand OTEL and backend credentials.
- Makes local replay/debugging harder than JSONL.
- Does not naturally represent raw hook events before schema decisions settle.
- Adds complexity to simple tests and offline runs.

**Reason for rejection**: OTEL is a good exporter target, not the only internal
contract.

### Alternative 3: Parse Terminal Pane Output Only

**Description**: Treat tmux pane capture as the only source of truth and infer
events from visible terminal output.

**Pros**:

- Works for every interactive harness at the transport level.
- Does not require plugin support.
- Useful as a fallback for readiness and final transcript capture.

**Cons**:

- Loses structured tool inputs/results.
- Weak token/cost fidelity.
- Fragile across TUI changes.
- Hard to distinguish lifecycle, tool, and model events reliably.

**Reason for rejection**: Pane capture is useful evidence, but it is not a full
observability system.

## Consequences

### Positive Consequences

- **Reusable primitive**: Backends plug into one fanout interface instead of
  each harness.
- **Portable setup**: File JSONL works immediately on Macs, VPS hosts, and
  Docker-mounted paths.
- **Backend flexibility**: LangFuse, local replay, and Syntropic137 can coexist.
- **Testability**: File exporter and mock exporters make acceptance tests cheap.
- **Clear failure reporting**: Exporter failures can be surfaced in
  `AgentRunResult.observability` without corrupting stdout JSONL.

### Negative Consequences

- **More components**: Harness observers, normalized event vocabulary, and
  exporters are separate modules.
- **Codex uncertainty**: Codex token/cost and hook surfaces need empirical
  validation before parity can be promised.
- **Two data mechanisms**: Hooks provide lifecycle/tool events, while transcript
  or stream watchers may be needed for token/cost.
- **Version drift risk**: Harness observers must track CLI/hook format changes.

### Neutral Consequences

- Claude can use plugin hooks where available.
- Codex may use a watcher or adapter parser until its plugin story is clearer.
- LangFuse can be self-hosted later without changing the internal event stream.

## Implementation Notes

Current branch `feat/observability-exporter-primitive` starts this decision:

- `providers/workspaces/interactive-tmux/driver-rs/src/run/contract.rs`
  defines typed observability exporters and exporter reports.
- `providers/workspaces/interactive-tmux/driver-rs/src/run/harness_observer.rs`
  defines the first observer boundary and a `codex_exec_json` parser that maps
  `codex exec --json` lifecycle and `turn.completed.usage` events into
  normalized payloads.
- `itmux codex-exec` is the first runnable observer path: it runs
  `codex exec --json`, envelopes observed payloads as `AgentRunEvent`s, and
  feeds them through the same file exporter/final result reporting layer.
- `providers/workspaces/interactive-tmux/driver-rs/src/run/observability.rs`
  implements file fanout.
- `workspace_executor.rs` fans out `AgentRunEvent`s while preserving stdout
  purity.
- `itmux run --observability-file <path>` enables the portable file exporter.

## Experiment Results, 2026-07-07

The first hypothesis-first probes produced these architecture constraints:

- `experiments/2026-07-07--observability--claude-hook-file-fanout` validated
  the file exporter: stdout event count and exported event count matched
  exactly in baseline and treatment. It did not validate Claude hook-derived
  events because Claude launched and then failed with Anthropic `API Error:
  401`. The treatment did prove that recipe-driven `itmux run` can launch
  `claude --plugin-dir /workspace/plugins/observability`.
- `experiments/2026-07-07--observability--codex-token-cost-surface` showed
  that Codex TUI currently provides only coarse driver/pane observability in
  `itmux run`. A separate `codex exec --json` probe produced structured
  `thread.started`, `turn.started`, `item.completed`, and `turn.completed`
  events, with `turn.completed.usage` carrying token counts. Therefore
  `codex_exec_json` is the first viable Codex usage observer; `codex_tui`
  remains a coarse observer until another live source is proven.
- `experiments/2026-07-07--langfuse--otel-ingestion-smoke` generated the local
  synthetic root span plus three child spans, but did not export because no
  LangFuse base URL, credentials, or OTEL exporter env were present. `.9`
  should fail fast on missing config and should not proceed to run-event mapping
  until this smoke passes against LangFuse Cloud or the Mac Mini self-host.
- `experiments/2026-07-07--observability--langfuse-otel-export` confirmed the
  backend gap: the current completed substrate fans out to `file`, but LangFuse
  trace creation and trace links still require a `.9` exporter variant plus
  run-event span mapping.
- `experiments/2026-07-07--langfuse--otel-preflight-mock` validated the
  locally testable LangFuse exporter contract without a backend: derived
  `/api/public/otel/v1/traces`, `POST`, `application/x-protobuf`, Basic auth,
  non-empty body, required attributes, and redacted evidence. It does not prove
  real LangFuse ingestion or trace discoverability.
- `experiments/2026-07-07--langfuse--exporter-config-failfast` validated the
  first `.9` implementation slice: the Rust contract now accepts
  `kind = "langfuse_otlp"`, the generated schema includes that variant, endpoint
  and Basic auth derivation are unit-tested, and missing env is surfaced as a
  failed exporter report without leaking key values.
- `experiments/2026-07-07--observability--codex-exec-observer-wiring` passed:
  `itmux codex-exec` produced normalized lifecycle events, one `token_usage`
  event, exact stdout/exporter event parity, and a successful file exporter
  report from a real `codex exec --json` run.
- `experiments/2026-07-07--observability--claude-credential-health` classified
  the Claude 401 blocker. Host `claude -p` succeeds because
  `CLAUDE_CODE_OAUTH_TOKEN` is set, while the Docker workspace receives staged
  disk credentials whose access token is expired and whose refresh token is
  empty after Claude starts. Recipe-driven `itmux run` therefore fails on first
  prompt submission with `API Error: 401`.
- `experiments/2026-07-07--observability--claude-env-token-passthrough`
  validated the credential fix: pass `CLAUDE_CODE_OAUTH_TOKEN` through Docker
  by env var name (`-e NAME`, not `NAME=value`). The same recipe-driven Claude
  prompt exited 0, returned the expected text, and preserved 11/11
  stdout-to-file exporter parity.
- `experiments/2026-07-07--observability--claude-hook-fanout-after-auth`
  removed auth from the Claude hook question: the plugin recipe launched with
  `claude --plugin-dir /workspace/plugins/observability`, the prompt succeeded,
  and exporter parity held, but no raw hook `event_type` JSONL appeared in
  stdout, stderr, session log, or exporter output.
- `experiments/2026-07-07--observability--baked-claude-hook-runtime` isolated
  runtime packaging from capture semantics. A derived image containing
  `plugins/observability` and `agentic_events` could run `observe.py` directly
  and emit `event_type = session_started`, but `itmux run` still saw no hook
  JSONL through stdout, stderr, session log, or file exporter. Therefore
  Claude hook support needs an explicit sink/capture path.
- `experiments/2026-07-07--observability--claude-hook-sink-capture` validated
  that explicit path: `observe.py` tees hook JSONL to
  `AGENTIC_EVENTS_JSONL`, the driver drains the file before teardown, and
  stdout/file fanout receive normalized `hook_event` records. The live run
  emitted 3 hook events (`session_started`, `user_prompt_submitted`,
  `agent_stopped`) with `session_end` still last.
- `experiments/2026-07-07--observability--stock-itmux-hook-sink` then proved
  the same path on the stock interactive-tmux provider image after baking
  `plugins/observability` and the `agentic_events` wheel. The stock image run
  emitted the same 3 normalized hook events with 14/14 stdout-to-file parity.

These results preserve the original three-layer architecture and validate two
end-to-end paths: `codex_exec_json` observer -> normalized `AgentRunEvent` ->
file fanout -> `ObservabilityBundle`, and Claude hook sink -> normalized
`hook_event` -> file fanout -> `ObservabilityBundle`. `.9` now has typed
LangFuse exporter config and fail-fast reporting, but still waits on real OTLP
transport plus LangFuse connectivity before claiming ingestion or queryability.

Validated gates and follow-ups for `okrs-51p.6`:

1. Harness observer boundary and runnable `codex_exec_json` path are proven by
   `itmux codex-exec`.
2. Backend-independent file exporter fanout and `ObservabilityBundle` reporting
   are proven end to end.
3. Claude plugin launch, credential passthrough, explicit hook sink/drain, and
   stock provider packaging are empirically proven.
4. The observability plugin README now documents stderr plus
   `AGENTIC_EVENTS_JSONL` sink semantics, preserving `itmux run` stdout purity.
5. Remaining follow-ups are not `.6` blockers: Codex TUI token/cost parity,
   Claude full token/cost parity through transcript/native stream work, and
   richer backend exporters.
6. Preserve relative path behavior in reports, but document and test that only
   absolute file exporter paths can produce `file://` links.

Next steps for `okrs-51p.9`:

1. Add real LangFuse/OTLP transport on top of the typed `langfuse_otlp`
   exporter config.
2. Support self-hosted Mac Mini configuration through env/keychain-backed
   secrets.
3. Emit linkable LangFuse trace URLs in `ObservabilityBundle`.
4. Run hypothesis-first experiments before marking the backend complete.
5. Use `experiments/2026-07-07--langfuse--otel-preflight-mock` for local
   config/auth/header/attribute regression coverage.
6. Then run `experiments/2026-07-07--langfuse--otel-ingestion-smoke` against a
   reachable LangFuse deployment to validate real OTLP ingestion and trace
   visibility before richer run-event mapping work.
7. Treat missing LangFuse env as a first-class exporter configuration failure
   with a clear `ObservabilityExportReport.error` (**implemented for missing
   env config**).

## References

- ADR-022: Git Hook Observability Architecture
- ADR-027: Provider-Based Workspace Images
- ADR-033: Plugin-Native Workspace Images
- ADR-035: Workspace Injection Contract
- ADR-037: Release Integration Gate
- `docs/handoffs/20260707-handoff_langfuse-observability-exporters.md`
- `providers/workspaces/interactive-tmux/driver-rs/src/run/observability.rs`
- `plugins/observability/hooks/handlers/observe.py`
- `providers/workspaces/interactive-tmux/manifest.yaml`
- `providers/workspaces/claude-cli/manifest.yaml`
- LangFuse OpenTelemetry integration: https://langfuse.com/integrations/native/opentelemetry
- LangFuse SDK overview: https://langfuse.com/docs/observability/sdk/overview

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
- `providers/workspaces/interactive-tmux/driver-rs/src/run/observability.rs`
  implements file fanout.
- `workspace_executor.rs` fans out `AgentRunEvent`s while preserving stdout
  purity.
- `itmux run --observability-file <path>` enables the portable file exporter.

Next steps for `okrs-51p.6`:

1. Add an explicit harness observer trait/module boundary.
2. Prove Claude hook plugin loading for `interactive-tmux` using
   `ITMUX_CLAUDE_PLUGIN_DIRS` or recipe `claude_plugin_dirs` without assuming
   Codex has the same mechanism.
3. Define how hook JSONL and transcript/token events map into the shared event
   vocabulary.
4. Add acceptance tests proving configured observers/exporters produce events
   and report failures.
5. Keep `.6` open until at least one harness observer and one backend-independent
   exporter are proven end to end.
6. Resolve the observability plugin docs/code mismatch: the README says
   lifecycle hooks emit to stdout, while the handler currently writes through
   stderr. Stdout must remain reserved for `itmux run` contract JSONL.

Next steps for `okrs-51p.9`:

1. Add a LangFuse/OTEL exporter on top of the fanout layer.
2. Support self-hosted Mac Mini configuration through env/keychain-backed
   secrets.
3. Emit linkable LangFuse trace URLs in `ObservabilityBundle`.
4. Run hypothesis-first experiments before marking the backend complete.
5. Start with `experiments/2026-07-07--langfuse--otel-ingestion-smoke` to
   validate OTLP HTTP auth, endpoint shape, and trace visibility before richer
   run-event mapping work.

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

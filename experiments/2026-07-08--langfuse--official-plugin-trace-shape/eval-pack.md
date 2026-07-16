# Eval Pack

## Probe A: Official Claude Plugin Trace Contract

Inspect the official Claude plugin source and README.

Capture:

- `runs/official-claude-source-files.txt`
- `runs/official-claude-trace-contract.md`

Pass criteria:

- The plugin uses Claude Code `Stop` and `SessionEnd` hooks.
- The plugin reads transcript JSONL rather than only hook lifecycle payloads.
- The plugin emits a root turn/span observation with input/output.
- The plugin emits generation observations with model and token usage when
  present.
- The plugin emits tool observations with semantic tool names and input/output.

## Probe B: Official Codex Plugin Trace Contract

Inspect the official Codex plugin source and README. If dependencies are already
available or cheap to install, run its test suite; otherwise use source-level
evidence and record why runtime execution was skipped.

Capture:

- `runs/official-codex-source-files.txt`
- `runs/official-codex-trace-contract.md`
- optional `runs/official-codex-tests.txt`

Pass criteria:

- The plugin uses a Codex `Stop` hook.
- The plugin reads Codex rollout transcript JSONL.
- The plugin emits `Codex Turn` as an agent observation with input/output.
- The plugin emits generation observations with output, model, and usage.
- The plugin emits tool observations with tool names, input/output, error
  status, and real timings.
- The plugin has a deduplication sidecar for resumed sessions.

## Probe C: Current Rust OTLP Trace Contract

Inspect the current agentic-primitives Rust OTLP exporter and, if local
LangFuse is reachable, query the known weak trace.

Capture:

- `runs/current-rust-otlp-contract.md`
- optional `runs/current-rust-trace-summary.json`

Pass criteria:

- Identify whether root trace input/output is populated.
- Identify whether child observations are named semantically or by event type.
- Identify whether tool start/end are paired into one tool observation.
- Identify whether usage/cost is attached to generation observations or separate
  event spans.

## Probe D: Pivot And Noise-Control Decision

Write a decision note from Probes A-C.

Capture:

- `runs/pivot-decision.md`

Pass criteria:

- State the canonical rich LangFuse path for Claude and Codex.
- State what JSONL fanout owns.
- State what Rust OTLP owns.
- State what Syntropic137 owns or consumes.
- State the default enablement/noise-control rule.
- Name the next experiment required before closing `.9`.

## Scoring

Use verdict `go` if the evidence supports the pivot and defines a clear
noise-controlled architecture.

Use verdict `no-go` if official plugins cannot produce materially richer traces
than the current Rust OTLP exporter.

Use verdict `inconclusive` if source evidence is strong but runtime/test
validation is blocked by missing tooling or credentials.

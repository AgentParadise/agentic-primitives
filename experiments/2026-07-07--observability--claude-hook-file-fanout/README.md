# Experiment: Claude Hook Events to File Fanout

## Question

Can the interactive-tmux Claude harness emit plugin hook events that are captured
as normalized observability artifacts through the reusable `itmux run` file
exporter?

## Hypothesis

1. A Claude run launched with the observability plugin loaded will produce at
   least one session lifecycle event and at least one tool lifecycle event.
2. `itmux run --observability-file` will append every normalized
   `AgentRunEvent` line to the configured JSONL file while keeping stdout as
   valid `AgentRunEvent` JSONL.
3. The final `AgentRunResult.observability.exporters[0]` report will have
   `status = "ok"`, `events_exported >= 3`, and a `file://` link URI.

## Setup

- Branch: `feat/observability-exporter-primitive`
- Bead: `okrs-51p.6`
- Harness: Claude inside `interactive-tmux`
- Exporter under test: `file`
- Required preflight: commit this hypothesis before writing any files under
  `runs/`.

## Conditions

- **Baseline:** `itmux run` without the Claude observability plugin, file exporter enabled.
- **Treatment:** `itmux run` with the Claude observability plugin made available
  through the provider-supported plugin-dir path, file exporter enabled.

## Expected Signals

- `runs/baseline-events.jsonl`
- `runs/treatment-events.jsonl`
- `runs/treatment-result.json`
- A summary table in `results.md` with event counts by type and exporter status.

## Out of Scope

- LangFuse export.
- Codex parity.
- Token/cost parity.

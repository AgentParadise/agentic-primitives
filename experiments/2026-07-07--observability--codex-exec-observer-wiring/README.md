# Experiment: Codex Exec Observer Wiring

## Question

Does the new `itmux codex-exec` runnable observer path turn real
`codex exec --json` output into normalized `AgentRunEvent` JSONL and file
fanout with token usage?

## Hypothesis

1. A successful run emits normalized stdout events containing at least one
   `token_usage` event.
2. The file exporter writes the same number of events as stdout, excluding only
   the final `type:"result"` event when a result file is used.
3. `AgentRunResult.observability.exporters[0]` reports `status = "ok"` and
   `events_exported` equal to the exported file line count.

## Setup

- Branch: `feat/observability-exporter-primitive`
- Bead: `okrs-51p.6`
- Command under test: `itmux codex-exec`
- Codex CLI: host `codex`, using the account-compatible default model.

## Conditions

- Run one minimal prompt through `itmux codex-exec`.
- Capture normalized stdout, exporter JSONL, result JSON, and a summary.

## Expected Signals

- `runs/stdout.jsonl`
- `runs/events.jsonl`
- `runs/result.json`
- `runs/summary.json`

## Out of Scope

- Interactive Codex TUI token/cost parity.
- LangFuse export.
- Claude hook observability.

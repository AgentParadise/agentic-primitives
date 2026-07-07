# Verdict

**Go.**

`itmux codex-exec` is a working end-to-end harness observer path for Codex
non-interactive runs. It normalizes real `codex exec --json` output into
`AgentRunEvent` JSONL, includes token usage, writes the same event stream to the
file exporter, and reports exporter status/count in the final result.

## Hypothesis scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| Successful run emits at least one `token_usage` event | One `token_usage` event emitted with input/cached/output/reasoning token fields | correct | `runs/summary.json` |
| Exported file event count matches normalized stdout event count | 6 stdout events and 6 exported events; streams match exactly | correct | `runs/stdout.jsonl`, `runs/events.jsonl` |
| Result exporter report status/count matches exported file | status `ok`, `events_exported=6` | correct | `runs/result.json` |

## Design Impact

- `.6` now has one empirical end-to-end observer/exporter path:
  `codex_exec_json` -> normalized `AgentRunEvent` -> file fanout ->
  `ObservabilityBundle`.
- Codex token usage parity should remain scoped to `codex_exec_json`, not the
  interactive TUI.
- The next `.6` implementation risk is Claude interactive credential health and
  hook event ingestion, not the backend-independent fanout architecture.

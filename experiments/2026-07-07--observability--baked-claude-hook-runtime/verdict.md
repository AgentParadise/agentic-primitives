# Verdict

**No-go for implicit Claude TUI hook capture; go for explicit hook sink design.**

The derived image proves the plugin runtime itself is viable: `observe.py`
imports `agentic_events` and emits valid `event_type` JSONL when run directly.
But Claude TUI hook output still does not reach the `itmux run` stdout stream,
stderr capture, session log, or file exporter. `.6` needs a deliberate
container-side hook sink and driver collection path.

## Hypothesis scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| Derived image can run `observe.py` directly and emit `event_type` JSONL | Emitted one `session_started` JSONL line to stderr, stdout empty | correct | `runs/manual-hook-stderr.jsonl` |
| `itmux run` launches baked plugin path and prompt succeeds | Exit 0, result success true, expected text present, baked plugin path present | correct | `runs/result.json` |
| `itmux run` still exports only driver events, not hook JSONL | 11 driver stdout events / 11 exported events; no `event_type` in stdout/exporter/stderr/session | correct | `runs/summary.json` |

## Design Impact

- Baking the plugin/dependency is necessary but not sufficient.
- The Claude hook primitive should write hook events to an explicit sink that
  the driver can collect, not rely on Claude TUI surfacing hook stderr/stdout.
- The exporter fanout can remain stdout-pure by normalizing collected hook
  events into `AgentRunEvent` before writing stdout/exporter JSONL.

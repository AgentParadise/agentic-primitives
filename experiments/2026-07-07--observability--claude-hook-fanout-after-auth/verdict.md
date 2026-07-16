# Verdict

**No-go for Claude hook observability; go for auth and driver file fanout.**

The post-auth rerun removed the 401 blocker and proved the plugin launch string
is present, but it did not surface any hook `event_type` JSONL in stdout,
stderr, session log, or the file exporter. This means `.6` still lacks reusable
Claude hook ingestion.

## Hypothesis scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| Plugin recipe launches and prompt succeeds | Exit 0, result success true, session contained `CLAUDE_HOOK_AUTH_OK` and plugin launch | correct | `runs/result.json` |
| File exporter remains driver-event consistent | 11 stdout events, 11 exported events, exporter status `ok` | correct | `runs/summary.json` |
| Hook JSONL is not normalized into exporter events yet | No `event_type` found in stdout/exporter/stderr/session | correct | Current fanout only contains driver events. |

## Design Impact

- `.6` remains open and continues blocking `.9`.
- Auth is no longer the blocker; the blocker is real hook event capture.
- The observability plugin README/code mismatch remains relevant:
  README says Claude hooks emit stdout, while `observe.py` emits stderr.
- Stock interactive-tmux also needs a proven way to provide
  `plugins/observability` and `agentic_events` inside the container before hook
  ingestion can be claimed.

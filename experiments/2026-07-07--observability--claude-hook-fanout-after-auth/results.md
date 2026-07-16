# Results

| Probe | Evidence | Result |
|---|---|---|
| Claude plugin recipe run | `runs/stdout.jsonl`, `runs/result.json`, `runs/summary.json` | Passed for auth/launch: exit 0, result success true, session contained `CLAUDE_HOOK_AUTH_OK`, no `API Error: 401`, and launch contained `claude --plugin-dir /workspace/plugins/observability`. |
| Hook visibility | `runs/stdout.jsonl`, `runs/events.jsonl`, `runs/stderr.txt`, `runs/result.json`, `runs/summary.json` | No raw `event_type` hook JSONL appeared in stdout, file exporter, stderr, or session log. |
| File exporter | `runs/stdout.jsonl`, `runs/events.jsonl`, `runs/result.json` | Passed for driver events: 11 stdout events, 11 exported events, exporter status `ok`, `events_exported = 11`. |

## Key Data

| Field | Value |
|---|---|
| `itmux run` exit | 0 |
| Result success | true |
| Session contains `CLAUDE_HOOK_AUTH_OK` | true |
| Session contains plugin launch | true |
| Session contains `API Error: 401` | false |
| Stdout event lines | 11 |
| Exporter event lines | 11 |
| Hook `event_type` seen in stdout/exporter/stderr/session | false / false / false / false |

## Classification

Claude plugin launch and credential health are now proven for recipe-driven
Docker runs, but hook events are not visible to the current `itmux run` fanout.
The exporter is still exporting driver lifecycle events only.

The next implementation step is not LangFuse. `.6` needs either a baked/staged
observability plugin plus `agentic_events` dependency path that actually emits
hook JSONL, or a dedicated Claude hook observer that can capture and normalize
Claude hook responses without contaminating stdout contract JSONL.

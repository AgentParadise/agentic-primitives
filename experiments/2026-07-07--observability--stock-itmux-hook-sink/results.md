# Results

| Probe | Evidence | Result |
|---|---|---|
| Stock image runtime check | `runs/image-check-exit.txt`, `runs/image-check.txt` | Passed: exit 0, plugin handler was executable, and `agentic_events.__version__` printed `0.1.0`. |
| Stock image hook capture | `runs/stdout.jsonl`, `runs/events.jsonl`, `runs/result.json`, `runs/summary.json` | Passed: exit 0, result success true, 14 stdout events / 14 exported events, 3 hook events in each stream. |

## Key Data

| Field | Value |
|---|---|
| Image check exit | 0 |
| `agentic_events` version | `0.1.0` |
| `itmux run` exit | 0 |
| Result success | true |
| Stdout event lines | 14 |
| Exporter event lines | 14 |
| Stdout hook events | 3 |
| Exporter hook events | 3 |
| Hook event types | `session_started`, `user_prompt_submitted`, `agent_stopped` |
| Last stdout event type | `session_end` |
| Standalone raw hook JSONL lines on stdout | 0 |

## Classification

The stock interactive-tmux image now contains the observability plugin and
`agentic_events` runtime, and recipe-driven `itmux run` captures Claude hook
events as normalized `hook_event` records without a temporary derived image.
